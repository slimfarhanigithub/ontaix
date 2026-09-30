"""The teach bake-off: which model and reasoning effort turn text, speech and documents into
the most detailed ontology with the fewest mistakes.

Every case runs through the real teach pipeline (`POST /teach/parse` in process, a scratch
PostgreSQL, one tenant per case), with the model client swapped per configuration. The plan's
cost is estimated before anything runs, and the run stops cleanly when the budget is spent.

    uv run python -m evals.teach_bakeoff --budget-eur 150 --out results/bakeoff.json
    uv run python -m evals.teach_bakeoff --budget-eur 150 --estimate-only
    uv run python -m evals.teach_bakeoff --budget-eur 1 --dry-run

Run from apps/api; `.env` supplies ONTAIX_FOUNDRY_ENDPOINT for candidates without their own
endpoint in `candidates.yaml` (keyless: `az login`). Exit code 3
means the budget stopped the run; the report covers what ran.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.clients import db_client
from app.clients.anthropic_foundry_llm_client import (
    AnthropicFoundryLlmClient,
    foundry_messages_url,
)
from app.clients.foundry_llm_client import FoundryLlmClient
from app.clients.llm_client import LlmClient, set_llm_client
from app.config import ModelPrice, get_settings
from app.migrations.runner import upgrade_to_head
from evals.candidate import (
    CandidateFile,
    RunConfig,
    UnpricedCandidate,
    at_effort,
    baseline_config,
    candidates_named,
    load_candidates,
    run_configs,
)
from evals.case_sources import PairedFolder, benchmark_folders, discover
from evals.cost_estimate import CaseLoad, case_load, estimate
from evals.doc_formats.loaded_document import LoadedDocument
from evals.doc_formats.ocr_client import AzureMistralOcrClient, FakeOcrClient, OcrClient
from evals.dry_run_llm_client import DryRunLlmClient
from evals.input_modes import DocumentCache, modes_for
from evals.recording_llm_client import Budget, CallGate, RecordingLlmClient
from evals.report import RunRecord, write
from evals.review_pass import Reviewer
from evals.stages import (
    SCREENING_SHARE,
    StageResult,
    best_per_family,
    compare_with_baseline,
    finalists,
    merge,
    run_stage,
    stratified_subset,
)
from evals.teach_case import TeachCase

logger = logging.getLogger("evals.teach_bakeoff")

EVALS = Path(__file__).parent
API_ROOT = EVALS.parent
# Output tokens allowed for reasoning on top of the answer bound, per effort.
REASONING_ALLOWANCE = {
    "default": 2048,
    "none": 0,
    "minimal": 1024,
    "low": 4096,
    "medium": 8192,
    "high": 16384,
}
ZERO_PRICE = ModelPrice(inputEurPerMTok=0, outputEurPerMTok=0)
DRY_RUN_OCR_TEXT = "The scanned page describes the company and its processes."
SUBSET_SEED = "teach-bakeoff-v1"
SMART_FIRST = "medium"
SMART_EXTRA_EFFORTS = ("none", "high")
SMART_BEST_PER_FAMILY = 2
BUDGET_STOP_EXIT = 3


@dataclass
class _Database:
    url: str
    close: Callable[[], None]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    logger.setLevel(logging.INFO)
    if sys.platform == "win32":
        # psycopg's async driver needs a selector loop; Windows defaults to the proactor loop.
        return asyncio.run(_main(args), loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(_main(args))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m evals.teach_bakeoff")
    p.add_argument("--budget-eur", type=float, required=True, help="hard cap; stops cleanly")
    p.add_argument("--estimate-only", action="store_true", help="print the estimate and exit")
    p.add_argument("--dry-run", action="store_true", help="fake model and OCR clients")
    p.add_argument("--candidates", type=Path, default=EVALS / "candidates.yaml")
    p.add_argument("--deployments", help="comma-separated; default every candidate")
    p.add_argument("--efforts", help="comma-separated; models without efforts always run")
    p.add_argument("--stage", choices=("screening", "finals", "all"), default="all")
    p.add_argument(
        "--plan",
        choices=("smart", "grid"),
        default="smart",
        help="smart: every model at medium, then none and high for the best 2 of each family; "
        "grid: every model at every effort",
    )
    p.add_argument("--finalists", type=int, default=3, help="configurations kept for finals")
    p.add_argument("--finals", help="with --stage finals: deployment@effort keys")
    p.add_argument("--repeats", type=int, default=2, help="finals repeats")
    p.add_argument("--screening-share", type=float, default=SCREENING_SHARE)
    p.add_argument("--cases-dir", type=Path, action="append", help="YAML dataset folder(s)")
    p.add_argument("--origins", help="comma-separated: dataset,documents,benchmarks,private")
    p.add_argument("--only", help="comma-separated case ids")
    p.add_argument("--document-modes", default="sentences", help="comma-separated: sentences,whole")
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="cases at once; model calls at once start here and halve on each 429",
    )
    p.add_argument("--timeout-seconds", type=float, help="per call; default the API's")
    p.add_argument("--speech-timeout-seconds", type=float, help="default the API's")
    p.add_argument("--ocr-deployment", help="default from candidates.yaml")
    p.add_argument(
        "--allow-global-for-private",
        action="store_true",
        help="let global (non EU data zone) models read tests/private documents",
    )
    p.add_argument(
        "--review",
        help="a candidate deployment that reviews each scored speech case's drafts after the "
        "run's own model; its corrections are scored apart (default effort low)",
    )
    p.add_argument("--review-effort", default="low", help="the reviewer's reasoning effort")
    p.add_argument("--out", type=Path, default=Path("bakeoff-results.json"))
    p.add_argument("--verbose", action="store_true")
    return p


async def _main(args: argparse.Namespace) -> int:
    started = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    try:
        file = load_candidates(args.candidates)
    except UnpricedCandidate as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.plan == "smart":
        configs = [
            at_effort(c, SMART_FIRST) for c in candidates_named(file, _split(args.deployments))
        ]
    else:
        configs = run_configs(file, _split(args.deployments), _split(args.efforts))
    baseline = baseline_config(file)
    work = Path(tempfile.mkdtemp(prefix="ontaix-bakeoff-"))
    found = discover(
        args.cases_dir or [EVALS / "cases"],
        [
            PairedFolder(EVALS / "documents", "documents"),
            *benchmark_folders(EVALS / "benchmarks"),
            PairedFolder(API_ROOT / "tests" / "private", "private"),
        ],
        work / "derived",
    )
    cases = _filtered(found.cases, _split(args.origins), _split(args.only))
    if not cases:
        print("no cases found", file=sys.stderr)
        return 2
    modes = _split(args.document_modes) or ["sentences"]
    screening_cases = stratified_subset(cases, args.screening_share, SUBSET_SEED)
    finals_configs = _finals_configs(args, file, configs, baseline)

    sizing = DocumentCache(ocr=None)
    loads: dict[tuple[str, str], CaseLoad] = {}
    for c in cases:
        for m in modes_for(c, modes):
            loads[(c.id, m.name)] = await case_load(c, m.name, sizing)
    plan = _plan(args, file, configs, finals_configs, cases, screening_cases, modes, loads)
    print(json.dumps(plan, indent=2))
    if args.estimate_only:
        return 0
    if plan["totalEur"] > args.budget_eur:
        print(
            f"estimate {plan['totalEur']:.2f} EUR is above the {args.budget_eur:.2f} EUR budget: "
            "the run will stop when the budget is spent",
            file=sys.stderr,
        )

    database = _database()
    budget = Budget(args.budget_eur)
    stages: list[StageResult] = []
    try:
        app = _app(database.url, args)
        docs = DocumentCache(ocr=_ocr(args, file))
        install = _installer(args, budget)
        reviewer = _reviewer(args, file, budget)
        eligible = _eligibility(args.allow_global_for_private)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://bakeoff/api/v1", timeout=None
        ) as client:
            if args.stage in ("screening", "all"):

                async def screen(name: str, chosen: list[RunConfig]) -> StageResult:
                    return await run_stage(
                        name,
                        chosen,
                        screening_cases,
                        modes,
                        1,
                        client,
                        docs,
                        install,
                        budget,
                        args.concurrency,
                        eligible,
                        reviewer,
                    )

                screening = await screen("screening", configs)
                if args.plan == "smart" and not budget.exhausted:
                    extra = _smart_extra(file, screening, {c.key for c in configs})
                    screening = merge("screening", [screening, await screen("screening", extra)])
                stages.append(screening)
                finals_configs = finalists(screening, args.finalists, baseline)
            if args.stage in ("finals", "all") and not budget.exhausted:
                finals = await run_stage(
                    "finals",
                    finals_configs,
                    cases,
                    modes,
                    args.repeats,
                    client,
                    docs,
                    install,
                    budget,
                    args.concurrency,
                    eligible,
                    reviewer,
                )
                compare_with_baseline(finals, baseline)
                stages.append(finals)
        for loaded in docs.loaded():
            if loaded.ocr is not None:
                budget.charge(loaded.ocr.cost_eur)
        record = RunRecord(
            started_at=started,
            dry_run=args.dry_run,
            budget_eur=args.budget_eur,
            spent_eur=round(budget.spent_eur, 6),
            estimate=plan,
            cases=cases,
            notes=found.notes,
            documents=[_document_row(d) for d in docs.loaded()],
            stages=stages,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        report_path = args.out.with_suffix(".md")
        write(record, args.out, report_path)
    finally:
        set_llm_client(None)
        await db_client.dispose_engine()
        database.close()
    print(f"spent {budget.spent_eur:.4f} EUR; wrote {args.out} and {report_path}")
    return BUDGET_STOP_EXIT if any(s.stopped_by_budget for s in stages) else 0


def _app(database_url: str, args: argparse.Namespace):
    """The API application over the scratch database, with the bake-off's limits."""
    os.environ["ONTAIX_ENVIRONMENT"] = "dev"
    os.environ["ONTAIX_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    settings = get_settings()
    settings.llm_calls_per_hour = 1_000_000
    # No lesson is captured from, or added to, an evaluation input: the TEST split stays honest.
    settings.learning_enabled = False
    if args.timeout_seconds:
        settings.llm_timeout_seconds = args.timeout_seconds
    if args.speech_timeout_seconds:
        settings.llm_speech_timeout_seconds = args.speech_timeout_seconds
    upgrade_to_head(database_url)
    db_client.configure_engine(database_url)
    # Imported here: building the application reads the settings, which must point at the
    # scratch database first.
    from app.main import create_app

    return create_app()


def _reviewer(args: argparse.Namespace, file: CandidateFile, budget: Budget) -> Reviewer | None:
    """The deeper model that reviews each scored speech case, when `--review` names one."""
    if not args.review:
        return None
    (candidate,) = candidates_named(file, [args.review])
    config = at_effort(candidate, args.review_effort)
    return Reviewer(_inner_client(args, config), budget)


def _inner_client(args: argparse.Namespace, config: RunConfig) -> LlmClient:
    """The provider client of one configuration, or the dry-run client."""
    price = config.price or ZERO_PRICE
    endpoint = config.endpoint or get_settings().foundry_endpoint
    if args.dry_run:
        return DryRunLlmClient(config.deployment, price)
    if not endpoint:
        raise SystemExit(
            f"{config.deployment}: no endpoint in candidates.yaml and ONTAIX_FOUNDRY_ENDPOINT "
            "is not set; use --dry-run"
        )
    if config.provider == "anthropic_foundry":
        return AnthropicFoundryLlmClient(
            foundry_messages_url(endpoint), config.deployment, price, config.reasoning_effort
        )
    return FoundryLlmClient(
        endpoint, config.deployment, config.deployment, price, config.reasoning_effort
    )


def _installer(
    args: argparse.Namespace, budget: Budget
) -> Callable[[RunConfig], Callable[[], dict[str, object]]]:
    """Installs a configuration's model client; returns a probe of what the model accepted."""

    def install(config: RunConfig) -> Callable[[], dict[str, object]]:
        get_settings().llm_reasoning_allowance_tokens = REASONING_ALLOWANCE[config.effort]
        inner = _inner_client(args, config)
        set_llm_client(RecordingLlmClient(inner, budget, CallGate(args.concurrency)))

        def probe() -> dict[str, object]:
            if args.dry_run:
                return {"outputMode": "dry-run"}
            capabilities = getattr(inner, "capabilities", None)
            if capabilities:
                return dict(capabilities)
            return {"outputMode": "json_schema", "reasoningEffort": config.reasoning_effort}

        return probe

    return install


def _eligibility(allow_global_for_private: bool) -> Callable[[RunConfig, TeachCase], bool]:
    """The data residency rule: the owner's private documents reach only EU data zone models,
    unless the run explicitly allows global ones."""

    def eligible(config: RunConfig, case: TeachCase) -> bool:
        return (
            case.origin != "private"
            or config.residency == "eu_data_zone"
            or allow_global_for_private
        )

    return eligible


def _ocr(args: argparse.Namespace, file: CandidateFile) -> OcrClient | None:
    if args.dry_run:
        return FakeOcrClient(DRY_RUN_OCR_TEXT)
    endpoint = get_settings().foundry_endpoint
    if file.ocr is None or not endpoint:
        return None
    return AzureMistralOcrClient.from_foundry_endpoint(
        endpoint,
        deployment=args.ocr_deployment or file.ocr.deployment,
        price_eur_per_1000_pages=file.ocr.eur_per_1000_pages,
    )


def _plan(
    args: argparse.Namespace,
    file: CandidateFile,
    configs: list[RunConfig],
    finals_configs: list[RunConfig],
    cases: list[TeachCase],
    screening_cases: list[TeachCase],
    modes: list[str],
    loads: dict[tuple[str, str], CaseLoad],
) -> dict[str, Any]:
    """The estimate of both stages. Before screening the finalists are unknown, so the finals
    are priced with the most expensive configurations (plus the baseline): an upper bound."""

    def loads_of(selected: list[TeachCase]) -> list[CaseLoad]:
        return [loads[(c.id, m.name)] for c in selected for m in modes_for(c, modes)]

    screening = estimate([(cfg, load, 1) for cfg in configs for load in loads_of(screening_cases)])
    candidates_for_finals = configs
    if args.plan == "smart":
        # The second pass is unknown until the first ranks the models: priced with the two most
        # expensive candidates of each family, an upper bound.
        subset = loads_of(screening_cases)
        extra: dict[str, RunConfig] = {}
        families: dict[str, list] = {}
        for c in candidates_named(file, _split(args.deployments)):
            options = [at_effort(c, e) for e in SMART_EXTRA_EFFORTS]
            options = [o for o in options if o.key not in {x.key for x in configs}]
            cost = estimate([(o, load, 1) for o in options for load in subset]).cost_eur
            families.setdefault(c.family, []).append((cost, options))
        for members in families.values():
            for _, options in sorted(members, key=lambda m: -m[0])[:SMART_BEST_PER_FAMILY]:
                extra.update({o.key: o for o in options})
        second = estimate([(o, load, 1) for o in extra.values() for load in subset])
        stages_extra = _estimate_row(second, len(extra), len(screening_cases), 1)
        candidates_for_finals = [*configs, *extra.values()]
    if args.stage == "all":
        full = loads_of(cases)
        per_config = {
            c.key: estimate([(c, load, 1) for load in full]).cost_eur for c in candidates_for_finals
        }
        ranked = sorted(candidates_for_finals, key=lambda c: -per_config[c.key])
        finals_configs = ranked[: args.finalists]
        base = baseline_config(file)
        if base.key not in {c.key for c in finals_configs}:
            finals_configs.append(base)
    finals = estimate(
        [(cfg, load, args.repeats) for cfg in finals_configs for load in loads_of(cases)]
    )
    ocr_pages = sum({load.case_id: load.ocr_pages for load in loads.values()}.values())
    ocr_eur = ocr_pages * (file.ocr.eur_per_1000_pages if file.ocr else 0.0) / 1000
    stages: dict[str, Any] = {}
    total = ocr_eur
    if args.stage in ("screening", "all"):
        stages["screening"] = _estimate_row(screening, len(configs), len(screening_cases), 1)
        total += screening.cost_eur
        if args.plan == "smart":
            stages["screeningSecondPass"] = stages_extra
            total += second.cost_eur
    if args.stage in ("finals", "all"):
        stages["finals"] = _estimate_row(finals, len(finals_configs), len(cases), args.repeats)
        total += finals.cost_eur
    return {
        "cases": len(cases),
        "screeningCases": len(screening_cases),
        "configurations": [c.key for c in configs],
        "stages": stages,
        "ocrPages": ocr_pages,
        "ocrEur": round(ocr_eur, 4),
        "totalEur": round(total, 2),
        "budgetEur": args.budget_eur,
        "unpriced": sorted(set(screening.unpriced) | set(finals.unpriced)),
    }


def _smart_extra(file: CandidateFile, first: StageResult, done: set[str]) -> list[RunConfig]:
    """Efforts `none` and `high` (or the closest each model takes) for the best candidates of
    each family after the medium pass, without repeating a configuration already run."""
    by_name = {c.deployment: c for c in file.candidates}
    extra: dict[str, RunConfig] = {}
    for deployments in best_per_family(first, SMART_BEST_PER_FAMILY).values():
        for deployment in deployments:
            for effort in SMART_EXTRA_EFFORTS:
                config = at_effort(by_name[deployment], effort)
                if config.key not in done:
                    extra[config.key] = config
    return list(extra.values())


def _estimate_row(e, configs: int, cases: int, repeats: int) -> dict[str, Any]:
    return {
        "configurations": configs,
        "cases": cases,
        "repeats": repeats,
        "calls": e.calls,
        "inputTokens": e.input_tokens,
        "outputTokens": e.output_tokens,
        "eur": round(e.cost_eur, 2),
        "eurByConfiguration": {k: round(v, 2) for k, v in sorted(e.by_config.items())},
    }


def _finals_configs(
    args: argparse.Namespace, file: CandidateFile, configs: list[RunConfig], baseline: RunConfig
) -> list[RunConfig]:
    if args.stage != "finals":
        return []
    keys = _split(args.finals)
    if not keys:
        raise SystemExit("--stage finals needs --finals deployment@effort,...")
    everything = {c.key: c for c in run_configs(file, None, None)}
    unknown = [k for k in keys if k not in everything]
    if unknown:
        raise SystemExit(f"unknown configurations: {', '.join(unknown)}")
    chosen = [everything[k] for k in keys]
    if baseline.key not in keys:
        chosen.append(baseline)
    return chosen


def _database() -> _Database:
    """ONTAIX_EVAL_DATABASE_URL when set (it is migrated, never dropped), else an embedded
    PostgreSQL in a temporary directory, deleted afterwards."""
    configured = os.environ.get("ONTAIX_EVAL_DATABASE_URL")
    if configured:
        return _Database(configured, lambda: None)
    import pgserver

    pgdata = Path(tempfile.mkdtemp(prefix="ontaix-bakeoff-pg-")) / "pgdata"
    server = pgserver.get_server(pgdata, cleanup_mode="delete")
    return _Database(server.get_uri(), server.cleanup)


def _filtered(
    cases: list[TeachCase], origins: list[str] | None, only: list[str] | None
) -> list[TeachCase]:
    return [c for c in cases if (not origins or c.origin in origins) and (not only or c.id in only)]


def _document_row(d: LoadedDocument) -> dict[str, Any]:
    ocr = d.ocr
    return {
        "path": str(d.path),
        "format": d.format,
        "words": d.words,
        "pages": d.pages,
        "ocr": None
        if ocr is None
        else {
            "deployment": ocr.deployment,
            "pages": ocr.pages,
            "latency_ms": ocr.latency_ms,
            "cost_eur": ocr.cost_eur,
        },
    }


def _split(value: str | None) -> list[str] | None:
    items = [v.strip() for v in (value or "").split(",") if v.strip()]
    return items or None


if __name__ == "__main__":
    sys.exit(main())

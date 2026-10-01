"""Time to the first cell and total time of a teach parse, plain and streamed, on the live model.

Each sentence is parsed twice through the API's own services, over a scratch PostgreSQL: once as
`POST /teach/parse` does (the first cell can only appear with the whole result) and once as
`POST /teach/parse/stream` does (the first cell appears with the first `draft` line). The order
of the two alternates from sentence to sentence, so the provider's prompt cache favours neither.
The run stops before a call that could take the model spend past `--budget-eur`.

Run from apps/api, signed in with `az login`, with `.env` configuring the provider:

    uv run python -m evals.stream_latency --budget-eur 0.5 --out results/stream_latency.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text
from starlette.requests import Request

from app.auth import get_caller
from app.clients import db_client
from app.config import get_settings
from app.migrations.runner import upgrade_to_head
from app.models.api.teach import TeachRequest
from app.services import teach_service, teach_stream_service
from evals.teach_bakeoff import _database
from evals.teach_case import TeachCase
from evals.workspace import Workspace

logger = logging.getLogger(__name__)

TYPED = [
    "Insight sells managed services and advisory to banks and insurers",
    "Our plants in Lyon and Porto produce valves, pumps and filters",
    "The quality team audits every supplier twice a year",
    "Customers place orders that are shipped from three warehouses",
    "Maintenance has two kinds of work orders, preventive and corrective",
]
SPOKEN = [
    "so um Insight sells financial services to its customers",
    "the services are split in advisory and uh managed services",
    "ADNOC is a client of Insight that has subsidiaries like XRG and Drilling",
    "we have engineers and consultants and the consultants work on projects",
    "the finance team handles invoices and uh the invoices are billed monthly",
]


async def run(budget_eur: float, out: Path) -> int:
    database = _database()
    try:
        os.environ["ONTAIX_ENVIRONMENT"] = "dev"
        os.environ["ONTAIX_DATABASE_URL"] = database.url
        get_settings.cache_clear()
        get_settings().llm_calls_per_hour = 1_000_000
        upgrade_to_head(database.url)
        db_client.configure_engine(database.url)
        case = TeachCase(id="stream-latency", kind="text", company="Insight", input=["x"])
        workspace = Workspace(None, case)  # type: ignore[arg-type]
        await workspace.open()
        headers = workspace._builder
        rows: list[dict[str, Any]] = []
        sentences = [(s, "text") for s in TYPED] + [(s, "speech") for s in SPOKEN]
        for i, (sentence, origin) in enumerate(sentences):
            spent = await _spent(workspace)
            if spent + 0.03 > budget_eur:
                print(f"stopping: {spent:.4f} EUR spent", file=sys.stderr)
                break
            request = TeachRequest(company_id=workspace.company_id, text=sentence, origin=origin)
            order = ("plain", "streamed") if i % 2 == 0 else ("streamed", "plain")
            row: dict[str, Any] = {"sentence": sentence, "origin": origin}
            for mode in order:
                measure = _plain if mode == "plain" else _streamed
                row[mode] = await measure(headers, request)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))
        summary = _summary(rows, await _spent(workspace))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"rows": rows, "summary": summary}, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        await db_client.dispose_engine()
        database.close()


async def _caller(session, headers: dict[str, str]):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return await get_caller(Request(scope), session)


async def _plain(headers: dict[str, str], request: TeachRequest) -> dict[str, Any]:
    started = time.monotonic()
    async with db_client.get_session_factory()() as session:
        caller = await _caller(session, headers)
        result = await teach_service.parse(session, caller, request)
        await session.commit()
    total = _ms(started)
    # Cells appear only when the whole result has arrived.
    return {
        "firstCellMs": total if result.drafts else None,
        "totalMs": total,
        "drafts": len(result.drafts),
        "llmOutcome": result.llm_outcome,
    }


async def _streamed(headers: dict[str, str], request: TeachRequest) -> dict[str, Any]:
    started = time.monotonic()
    async with db_client.get_session_factory()() as session:
        caller = await _caller(session, headers)
        prepared = await teach_service.prepare(session, caller, request)
        await session.commit()
    first: int | None = None
    early = retracted = 0
    result: dict[str, Any] = {}
    async for line in teach_stream_service.events(prepared):
        event = json.loads(line)
        if event["type"] == "draft":
            early += 1
            first = first if first is not None else _ms(started)
        elif event["type"] == "retract":
            retracted = len(event["indexes"])
        elif event["type"] == "result":
            result = event["result"]
    total = _ms(started)
    drafts = len(result.get("drafts", []))
    return {
        "firstCellMs": first if first is not None else (total if drafts else None),
        "totalMs": total,
        "drafts": drafts,
        "streamedDrafts": early,
        "retracted": retracted,
        "llmOutcome": result.get("llmOutcome"),
    }


async def _spent(workspace: Workspace) -> float:
    async with db_client.get_session_factory()() as session:
        spent = await session.scalar(
            text("SELECT COALESCE(SUM(cost_eur), 0) FROM ontaix.llm_call WHERE tenant_id = :t"),
            {"t": workspace.tenant_id},
        )
    return float(spent or 0)


def _summary(rows: list[dict[str, Any]], spent: float) -> dict[str, Any]:
    out: dict[str, Any] = {"spentEur": round(spent, 4), "sentences": len(rows)}
    for origin in ("text", "speech", None):
        chosen = [r for r in rows if origin is None or r["origin"] == origin]
        key = origin or "all"
        for mode in ("plain", "streamed"):
            firsts = [r[mode]["firstCellMs"] for r in chosen if r[mode]["firstCellMs"] is not None]
            totals = [r[mode]["totalMs"] for r in chosen]
            out[f"{key}.{mode}"] = {
                "firstCellMedianMs": int(statistics.median(firsts)) if firsts else None,
                "firstCellMeanMs": int(statistics.mean(firsts)) if firsts else None,
                "totalMedianMs": int(statistics.median(totals)) if totals else None,
                "totalMeanMs": int(statistics.mean(totals)) if totals else None,
            }
    return out


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--budget-eur", type=float, default=0.5)
    parser.add_argument("--out", type=Path, default=Path("results/stream_latency.json"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.budget_eur, args.out))


if __name__ == "__main__":
    raise SystemExit(main())

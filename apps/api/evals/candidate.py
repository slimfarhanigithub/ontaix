"""The bake-off's candidate models, their reasoning efforts and prices, from `candidates.yaml`.

A run configuration is one deployment at one effort. The effort `default` sends no
`reasoning_effort` at all, for models that take none.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.config import ModelPrice

DEFAULT_EFFORT = "default"

Effort = Literal["default", "none", "minimal", "low", "medium", "high"]
# Where a model processes prompts: inside the EU data zone, or anywhere (global deployments).
Residency = Literal["eu_data_zone", "global"]
# Which API serves the deployment, named as the API's ONTAIX_LLM_PROVIDER values: the Foundry
# OpenAI v1 endpoint, or Claude's Messages endpoint on a Foundry resource.
Provider = Literal["azure_foundry", "anthropic_foundry"]
# Efforts from least to most reasoning; `default` sits in the middle for closest-effort lookups.
EFFORT_ORDER: tuple[str, ...] = ("none", "minimal", "low", "default", "medium", "high")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Candidate(_Model):
    deployment: str
    efforts: list[Effort] = Field(min_length=1)
    price: ModelPrice | None = None
    provider: Provider = "azure_foundry"
    # The Foundry resource; None is ONTAIX_FOUNDRY_ENDPOINT.
    endpoint: str | None = None
    residency: Residency = "eu_data_zone"
    family: str = "other"

    def at(self, effort: Effort) -> RunConfig:
        return RunConfig(
            self.deployment,
            effort,
            self.price,
            self.provider,
            self.residency,
            self.family,
            self.endpoint,
        )


class Baseline(_Model):
    deployment: str
    effort: Effort


class OcrPrice(_Model):
    deployment: str
    eur_per_1000_pages: float = Field(alias="eurPer1000Pages", ge=0)


class CandidateFile(_Model):
    baseline: Baseline
    candidates: list[Candidate]
    ocr: OcrPrice | None = None


@dataclass(frozen=True)
class RunConfig:
    deployment: str
    effort: Effort
    price: ModelPrice | None
    provider: Provider = "azure_foundry"
    residency: Residency = "eu_data_zone"
    family: str = "other"
    endpoint: str | None = None

    @property
    def key(self) -> str:
        return f"{self.deployment}@{self.effort}"

    @property
    def reasoning_effort(self) -> str | None:
        return None if self.effort == DEFAULT_EFFORT else self.effort


class UnpricedCandidate(ValueError):
    """A candidate has no price, so its spend could not count against the budget cap."""


def load_candidates(path: Path) -> CandidateFile:
    """The candidates file; refused when any candidate has no price."""
    file = CandidateFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    unpriced = [c.deployment for c in file.candidates if c.price is None]
    if unpriced:
        raise UnpricedCandidate(
            f"{path.name}: no price for {', '.join(unpriced)}; every candidate needs a price "
            "(use a conservative one and mark it as an assumption) so the budget cap holds"
        )
    return file


def run_configs(
    file: CandidateFile, deployments: list[str] | None, efforts: list[str] | None
) -> list[RunConfig]:
    """Every deployment at every effort it accepts, narrowed to the given deployments and
    efforts; a model that takes no effort always runs once, at `default`. An unknown
    deployment is an error."""
    known = {c.deployment: c for c in file.candidates}
    unknown = sorted(set(deployments or []) - set(known))
    if unknown:
        raise ValueError(f"not in candidates.yaml: {', '.join(unknown)}")
    chosen = [known[d] for d in deployments] if deployments else file.candidates
    return [
        c.at(e)
        for c in chosen
        for e in c.efforts
        if not efforts or e in efforts or e == DEFAULT_EFFORT
    ]


def baseline_config(file: CandidateFile) -> RunConfig:
    c = {c.deployment: c for c in file.candidates}[file.baseline.deployment]
    return c.at(file.baseline.effort)


def at_effort(candidate: Candidate, wanted: str) -> RunConfig:
    """The candidate at `wanted`, or at the supported effort closest to it (ties go to the
    lower effort)."""
    target = EFFORT_ORDER.index(wanted)
    effort = min(
        candidate.efforts,
        key=lambda e: (abs(EFFORT_ORDER.index(e) - target), EFFORT_ORDER.index(e)),
    )
    return candidate.at(effort)


def candidates_named(file: CandidateFile, deployments: list[str] | None) -> list[Candidate]:
    known = {c.deployment: c for c in file.candidates}
    unknown = sorted(set(deployments or []) - set(known))
    if unknown:
        raise ValueError(f"not in candidates.yaml: {', '.join(unknown)}")
    return [known[d] for d in deployments] if deployments else list(file.candidates)

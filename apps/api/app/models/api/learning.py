"""DTOs of the usage learning endpoints under `/companies/{companyId}/learning`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.api.base import ApiModel

LessonSignal = Literal["approve", "reject", "correct"]
LessonTask = Literal["teach", "expand", "extraction"]
LessonOrigin = Literal["text", "speech", "document", "suggestion"]
RetiredReason = Literal["contradicted", "superseded", "cap"]


class LearningVerb(ApiModel):
    action: str
    count: int = Field(ge=1)


class LearningHabits(ApiModel):
    """Derived on read from the company's approved relations and concepts, never stored."""

    verbs: list[LearningVerb] = Field(max_length=20)
    naming: list[str] = Field(max_length=5)


class Lesson(ApiModel):
    id: uuid.UUID
    signal: LessonSignal
    task: LessonTask
    origin: LessonOrigin
    source_text: str = Field(max_length=4000)
    model_output: dict[str, Any] | None = None
    final_structure: dict[str, Any] | None = None
    corrects_id: uuid.UUID | None = None
    bulk: bool
    proposal_ids: list[uuid.UUID]
    created_at: datetime
    retired_at: datetime | None
    retired_reason: RetiredReason | None


class CompanyAlias(ApiModel):
    id: uuid.UUID
    heard: str = Field(max_length=120)
    meant: str = Field(max_length=120)
    concept_id: uuid.UUID | None
    hits: int = Field(ge=0)
    created_at: datetime
    retired_at: datetime | None


class CompanyLearning(ApiModel):
    company_id: uuid.UUID
    enabled: bool
    page: int
    page_size: int
    total: int
    lessons: list[Lesson]
    aliases: list[CompanyAlias] = Field(max_length=1000)
    habits: LearningHabits


class LearningSwitch(ApiModel):
    enabled: bool


class LearningSwitched(ApiModel):
    company_id: uuid.UUID
    enabled: bool


class LearningReset(ApiModel):
    """`confirm` must read `reset`; the service answers `422` with the reason otherwise."""

    confirm: str | None = None


class LearningResetResult(ApiModel):
    lessons: int = Field(ge=0)
    aliases: int = Field(ge=0)

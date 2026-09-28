"""Typed proposal drafts accepted by `POST /proposals`, the batch and the resource endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.models.api.base import ApiModel

DEFAULT_ACTION = "relates to"

Seed = Annotated[float, Field(ge=0, lt=1)]


class ConceptDraft(ApiModel):
    type: Literal["concept"] = "concept"
    company_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    parent_label: str | None = Field(default=None, max_length=120)
    label: str = Field(min_length=1, max_length=120)
    domain_key: str
    action: str = Field(default=DEFAULT_ACTION, min_length=1, max_length=60)
    reverse: bool = False
    caption: str | None = Field(default=None, max_length=300)
    seed: Seed | None = None

    @model_validator(mode="after")
    def _parent_present(self) -> ConceptDraft:
        if (self.parent_id is None) == (not self.parent_label):
            raise ValueError("exactly one of parentId or parentLabel is required")
        return self


class SpecDraft(ApiModel):
    type: Literal["spec"] = "spec"
    company_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    parent_label: str | None = Field(default=None, max_length=120)
    label: str = Field(min_length=1, max_length=120)
    rule: str | None = Field(default=None, max_length=200)
    domain_key: str
    caption: str | None = Field(default=None, max_length=300)
    seed: Seed | None = None

    @model_validator(mode="after")
    def _parent_present(self) -> SpecDraft:
        if (self.parent_id is None) == (not self.parent_label):
            raise ValueError("exactly one of parentId or parentLabel is required")
        return self


class RelationDraft(ApiModel):
    type: Literal["relation"] = "relation"
    a_id: uuid.UUID | None = None
    b_id: uuid.UUID | None = None
    a_label: str | None = Field(default=None, max_length=120)
    b_label: str | None = Field(default=None, max_length=120)
    company_id: uuid.UUID | None = None
    action: str = Field(min_length=1, max_length=60)
    caption: str | None = Field(default=None, max_length=300)
    seed: Seed | None = None

    @model_validator(mode="after")
    def _ends_present(self) -> RelationDraft:
        for end_id, label, name in ((self.a_id, self.a_label, "a"), (self.b_id, self.b_label, "b")):
            if (end_id is None) == (not label):
                raise ValueError(f"exactly one of {name}Id or {name}Label is required")
            if end_id is None and self.company_id is None:
                raise ValueError(f"companyId is required when {name}Label is used")
        return self


class SourceDraft(ApiModel):
    type: Literal["source"] = "source"
    company_id: uuid.UUID
    label: str = Field(min_length=1, max_length=120)
    kind_text: str = Field(max_length=60)
    connector_code: str | None = Field(default=None, max_length=10)
    host: str | None = Field(default=None, max_length=300)
    scope: str | None = Field(default=None, max_length=500)
    auth: (
        Literal[
            "service_principal",
            "oauth2_client_credentials",
            "managed_identity",
            "key_vault_api_key",
        ]
        | None
    ) = None
    credential_ref: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,127}$")
    refresh: Literal["5 min", "15 min", "1 h", "daily"] | None = None
    caption: str | None = Field(default=None, max_length=300)


class BindingDraft(ApiModel):
    type: Literal["bind"] = "bind"
    source_id: uuid.UUID
    concept_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    caption: str | None = Field(default=None, max_length=300)
    seed: Seed | None = None


class AttributeDraft(ApiModel):
    type: Literal["attr"] = "attr"
    concept_id: uuid.UUID
    source_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    attribute_type: Literal["id", "text", "number", "ref", "date"]
    col: str = Field(max_length=200)
    fill: int = Field(ge=0, le=100)


class ChangePayload(ApiModel):
    concept_id: uuid.UUID | None = None
    new_label: str | None = Field(default=None, min_length=1, max_length=120)
    relation_id: uuid.UUID | None = None
    action: str | None = Field(default=None, min_length=1, max_length=60)
    reverse: bool | None = None
    binding_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    conflict_concept_ids: list[uuid.UUID] | None = Field(default=None, min_length=2, max_length=2)


class ChangeDraft(ApiModel):
    type: Literal["change"] = "change"
    change_kind: Literal[
        "rename",
        "delete_concept",
        "edit_relation",
        "remove_relation",
        "unbind",
        "rename_source",
        "remove_source",
        "remove_company",
        "resolve_conflict",
    ]
    payload: ChangePayload
    caption: str | None = Field(default=None, max_length=300)


ProposalDraft = Annotated[
    ConceptDraft
    | SpecDraft
    | RelationDraft
    | SourceDraft
    | BindingDraft
    | AttributeDraft
    | ChangeDraft,
    Field(discriminator="type"),
]

ConceptOrSpecDraft = Annotated[ConceptDraft | SpecDraft, Field(discriminator="type")]


class ProposalBatch(ApiModel):
    drafts: list[ProposalDraft] = Field(min_length=1, max_length=200)

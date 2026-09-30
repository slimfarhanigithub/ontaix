"""Typed proposal drafts accepted by `POST /proposals`, the batch and the resource endpoints.

Every draft may declare its `origin` (`text` or `speech`, `text` when unset) and cite a stored
import sentence through `import_ref`; only the generic endpoints accept `import_ref`.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.models.api.base import ApiModel
from app.models.api.origin import ImportRef, InputOrigin

DEFAULT_ACTION = "relates to"
DOMAIN_KEY_PATTERN = r"^[a-z][a-z0-9_]{1,39}$"
HEX_PATTERN = r"^#[0-9a-f]{6}$"

Seed = Annotated[float, Field(ge=0, lt=1)]


class ConceptDraft(ApiModel):
    type: Literal["concept"] = "concept"
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
    company_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    parent_label: str | None = Field(default=None, max_length=120)
    label: str = Field(min_length=1, max_length=120)
    domain_key: str = Field(pattern=DOMAIN_KEY_PATTERN)
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
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
    company_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    parent_label: str | None = Field(default=None, max_length=120)
    label: str = Field(min_length=1, max_length=120)
    rule: str | None = Field(default=None, max_length=200)
    domain_key: str = Field(pattern=DOMAIN_KEY_PATTERN)
    caption: str | None = Field(default=None, max_length=300)
    seed: Seed | None = None

    @model_validator(mode="after")
    def _parent_present(self) -> SpecDraft:
        if (self.parent_id is None) == (not self.parent_label):
            raise ValueError("exactly one of parentId or parentLabel is required")
        return self


class RelationDraft(ApiModel):
    type: Literal["relation"] = "relation"
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
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
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
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
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
    source_id: uuid.UUID
    concept_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    caption: str | None = Field(default=None, max_length=300)
    seed: Seed | None = None


TAUGHT_ATTRIBUTE_TYPES = frozenset({"text", "number", "date"})


class AttributeDraft(ApiModel):
    """An attribute read from a bound source (`col` and `fill`), or taught (`value`). The concept
    is given by id, or by label and company when an earlier draft of the same batch introduces
    it."""

    type: Literal["attr"] = "attr"
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
    concept_id: uuid.UUID | None = None
    concept_label: str | None = Field(default=None, min_length=1, max_length=120)
    company_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    attribute_type: Literal["id", "text", "number", "ref", "date"]
    col: str | None = Field(default=None, max_length=200)
    fill: int | None = Field(default=None, ge=0, le=100)
    value: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _one_concept_and_one_kind(self) -> AttributeDraft:
        by_label = self.concept_label is not None or self.company_id is not None
        if (self.concept_id is None) == (not by_label):
            raise ValueError("exactly one of conceptId or conceptLabel with companyId is required")
        if by_label and (self.concept_label is None or self.company_id is None):
            raise ValueError("conceptLabel and companyId go together")
        if self.value is None:
            if self.col is None or self.fill is None:
                raise ValueError("an attribute has col and fill, or a value")
        elif self.col is not None or self.fill is not None or self.source_id is not None:
            raise ValueError("a taught attribute has a value and no col, fill or sourceId")
        elif self.attribute_type not in TAUGHT_ATTRIBUTE_TYPES:
            raise ValueError("a taught attribute is text, number or date")
        return self

    @property
    def taught(self) -> bool:
        return self.value is not None


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
    domain_key: str | None = Field(default=None, pattern=DOMAIN_KEY_PATTERN)
    domain_product_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, pattern=HEX_PATTERN)
    owner: str | None = Field(default=None, max_length=60)
    concept_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)
    domain_product_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


class ChangeDraft(ApiModel):
    type: Literal["change"] = "change"
    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
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
        "create_domain",
        "edit_domain",
        "delete_domain",
        "move_concept_domain",
        "delete_bulk",
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
    """`origin` and `import_ref` apply to every draft that sets none of its own. `parse_id` is
    the `TeachResult.parseId` the drafts came from: advisory, it only links the created
    proposals to the stored parse for usage learning and never changes what is created."""

    origin: InputOrigin | None = None
    import_ref: ImportRef | None = None
    parse_id: uuid.UUID | None = None
    drafts: list[ProposalDraft] = Field(min_length=1, max_length=200)

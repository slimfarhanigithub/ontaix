"""Declarative base and the enumerations of the `ontaix` schema.

The tables are created by the Alembic migration from `contracts/schema.sql`; these mappings
only describe the existing DDL to the ORM and never create types or tables themselves.
"""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import Enum, MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "ontaix"


class NodeKind(enum.StrEnum):
    ROOT = "root"
    CONCEPT = "concept"


class RelationKind(enum.StrEnum):
    REL = "rel"
    ISA = "isa"
    SAME = "same"
    CLASH = "clash"


class ProposalType(enum.StrEnum):
    CONCEPT = "concept"
    SPEC = "spec"
    RELATION = "relation"
    SOURCE = "source"
    BIND = "bind"
    ATTR = "attr"
    CHANGE = "change"


class ProposalState(enum.StrEnum):
    PENDING = "pending"
    HALF_APPROVED = "half_approved"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProposalOrigin(enum.StrEnum):
    TEXT = "text"
    SPEECH = "speech"
    DOCUMENT = "document"
    SUGGESTION = "suggestion"
    ONTOLOGY_IMPORT = "ontology_import"


class ChangeKind(enum.StrEnum):
    RENAME = "rename"
    DELETE_CONCEPT = "delete_concept"
    EDIT_RELATION = "edit_relation"
    REMOVE_RELATION = "remove_relation"
    UNBIND = "unbind"
    RENAME_SOURCE = "rename_source"
    REMOVE_SOURCE = "remove_source"
    REMOVE_COMPANY = "remove_company"
    RESOLVE_CONFLICT = "resolve_conflict"
    REMOVE_CROSS_COMPANY_LINKS = "remove_cross_company_links"


class AttributeType(enum.StrEnum):
    ID = "id"
    TEXT = "text"
    NUMBER = "number"
    REF = "ref"
    DATE = "date"


class AttributeState(enum.StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"


class RoleName(enum.StrEnum):
    OWNER = "owner"
    BUILDER = "builder"
    GOVERNOR = "governor"
    MEMBER = "member"
    ADMINISTRATOR = "administrator"
    AUDITOR = "auditor"
    AGENT = "agent"


class ScopeKind(enum.StrEnum):
    TENANT = "tenant"
    COMPANY = "company"
    DOMAIN = "domain"


class ActorKind(enum.StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    PLATFORM = "platform"


class CompanyMode(enum.StrEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"


class PlatformRoleName(enum.StrEnum):
    SUPER_ADMIN = "super_admin"


class PasswordSetReason(enum.StrEnum):
    BOOTSTRAP = "bootstrap"
    INITIAL = "initial"
    RESET = "reset"
    CHANGE = "change"


class SessionEndReason(enum.StrEnum):
    SIGN_OUT = "sign_out"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET = "password_reset"
    ACCOUNT_DISABLED = "account_disabled"
    ORGANIZATION_DISABLED = "organization_disabled"
    SESSION_LIMIT = "session_limit"
    SUPPORT_CHANGED = "support_changed"


class ThrottleKeyKind(enum.StrEnum):
    EMAIL = "email"
    IP = "ip"


class SourceAuth(enum.StrEnum):
    SERVICE_PRINCIPAL = "service_principal"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"
    MANAGED_IDENTITY = "managed_identity"
    KEY_VAULT_API_KEY = "key_vault_api_key"


class RefreshInterval(enum.StrEnum):
    FIVE_MIN = "5 min"
    FIFTEEN_MIN = "15 min"
    ONE_HOUR = "1 h"
    DAILY = "daily"


class ThemeName(enum.StrEnum):
    DARK = "dark"
    LIGHT = "light"


class BindingFreshness(enum.StrEnum):
    TWO_MIN = "2 min"
    FOUR_MIN = "4 min"
    ELEVEN_MIN = "11 min"
    ONE_HOUR = "1 h"
    PAUSED = "paused"
    JUST_NOW = "just now"


def pg_enum(py_enum: type[enum.StrEnum], name: str) -> Enum:
    """Map a Python StrEnum onto an existing PostgreSQL enum type of the `ontaix` schema."""
    return Enum(
        py_enum,
        name=name,
        schema=SCHEMA,
        create_type=False,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


class Base(DeclarativeBase):
    """Base for every mapped table; server-generated ids and timestamps are fetched on flush."""

    metadata = MetaData(schema=SCHEMA)
    __mapper_args__: dict[str, Any] = {"eager_defaults": True}

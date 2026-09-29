"""Resolves the caller of a request and carries its native role grants.

Authentication: only when the environment is exactly `dev` does the header `X-Ontaix-User` name
a user of the native directory by its `dev` issuer subject. In every other environment, including
an unset one, no credential is accepted until OIDC bearer tokens are wired in. Authorisation never
looks at the credential: it reads the tenant's own groups and role assignments.

The request session commits when the endpoint function returns, before the response is sent, so
a failed commit answers 5xx and never a 2xx for a change that did not land.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.db_client import session_dependency
from app.config import get_settings
from app.models.api.actor import Actor
from app.models.storage.base import ActorKind
from app.repositories import app_user_repository, group_role_repository, tenant_settings_repository
from app.utilities.clock import get_clock
from app.utilities.permissions import Grant
from app.utilities.problems import unauthorized

logger = logging.getLogger(__name__)

DEV_USER_HEADER = "X-Ontaix-User"
DEV_ISSUER = "dev"


@dataclass(frozen=True)
class Caller:
    """The authenticated user with every role grant it holds in its tenant."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    grants: tuple[Grant, ...]
    everyone_teaches: bool

    @property
    def actor(self) -> Actor:
        return Actor(kind="user", id=self.user_id, name=self.name)

    @property
    def actor_kind(self) -> ActorKind:
        return ActorKind.USER


SessionDependency = Annotated[AsyncSession, Depends(session_dependency, scope="function")]


async def get_caller(request: Request, session: SessionDependency) -> Caller:
    """FastAPI dependency: the caller, or 401 when no accepted credential identifies a user."""
    settings = get_settings()
    if not settings.is_dev:
        raise unauthorized("Bearer authentication is not configured")
    subject = request.headers.get(DEV_USER_HEADER)
    if not subject:
        raise unauthorized(f"Missing {DEV_USER_HEADER} header")
    user = await app_user_repository.get_by_identity(session, DEV_ISSUER, subject)
    if user is None:
        raise unauthorized("Unknown user")
    assignments = await group_role_repository.list_for_user(
        session, user.tenant_id, user.id, get_clock().now()
    )
    tenant_settings = await tenant_settings_repository.get(session, user.tenant_id)
    grants = tuple(
        Grant(
            role=a.role,
            scope_kind=a.scope_kind,
            company_id=a.scope_company_id,
            domain_key=a.scope_domain_key,
        )
        for a in assignments
    )
    return Caller(
        tenant_id=user.tenant_id,
        user_id=user.id,
        name=user.name,
        grants=grants,
        everyone_teaches=bool(tenant_settings and tenant_settings.everyone_teaches),
    )


CallerDependency = Annotated[Caller, Depends(get_caller)]

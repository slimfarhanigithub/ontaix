"""The authentication boundary: who is calling, and the organization the request is bound to.

Authentication: a browser presents the `__Host-ontaix_session` cookie issued by
`POST /auth/sign-in`; its SHA-256 is resolved by the database function `resolve_session()`,
which the application role may call although it can read no session table. Only in dev or test
with `ONTAIX_DEV_IDENTITY_HEADER` on does the header `X-Ontaix-User` name a seeded `dev` user
instead; a live cookie takes precedence. Nothing else authenticates a user.

Isolation: once the caller is known, its organization is bound to the request's database
session (`ontaix.tenant_id` for every transaction), and row-level security hides every other
organization's rows beneath the repositories' own filters. Until then the session sees no row.

CSRF: a cookie-authenticated POST, PUT, PATCH or DELETE must carry `X-CSRF-Token` equal to the
session's token and an allowed `Origin`; header callers skip it, since no cross-site form can
set that header.

Authorisation never looks at the credential: members get the roles of their organization's own
groups; a super admin gets nothing inside an organization except, during a support session,
read-only `model.read`, `directory.read` and `audit.read`, or, after entering an organization
(`acting_tenant_id` on the session), every tenant role through the directory user the entry
created for him, every action then audited as platform access.

The request session commits when the endpoint function returns, before the response is sent, so
a failed commit answers 5xx and never a 2xx for a change that did not land.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import db_client
from app.clients.db_client import platform_session_dependency, session_dependency
from app.config import get_settings
from app.models.api.actor import Actor
from app.models.storage.base import ActorKind, PlatformRoleName, RoleName, ScopeKind
from app.repositories import (
    app_user_repository,
    auth_session_repository,
    group_role_repository,
    platform_role_repository,
    tenant_settings_repository,
)
from app.repositories.auth_session_repository import ResolvedSession
from app.services import session_service
from app.services.session_service import LiveSession
from app.utilities.client_ip import FORWARDED_FOR, client_ip
from app.utilities.clock import get_clock
from app.utilities.permissions import Grant
from app.utilities.problems import ProblemError, forbidden, unauthorized
from app.utilities.session_tokens import is_well_formed, token_digest, tokens_equal

logger = logging.getLogger(__name__)

SESSION_COOKIE = "__Host-ontaix_session"
DEV_USER_HEADER = "X-Ontaix-User"
CSRF_HEADER = "X-CSRF-Token"
DEV_ISSUER = "dev"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SUPPORT_ACTOR_NAME = "Ontaix support"
# Auditor at tenant scope reads the model, the directory and the audit log, and nothing else.
SUPPORT_GRANTS = (Grant(role=RoleName.AUDITOR, scope_kind=ScopeKind.TENANT),)

SIGN_IN_REQUIRED = "Sign in to continue"
CSRF_DETAIL = "The request did not come from the Studio; reload the page and try again"
PASSWORD_CHANGE_DETAIL = "Choose a new password to continue"
SUPPORT_ONLY_DETAIL = (
    "A super admin enters an organization, or opens it through a read-only support session"
)
ENTER_AGAIN_DETAIL = "The organization no longer knows this platform access; enter it again"
# A super admin inside an organization holds every tenant role at tenant scope.
ACTING_GRANTS = tuple(
    Grant(role=role, scope_kind=ScopeKind.TENANT)
    for role in (RoleName.ADMINISTRATOR, RoleName.BUILDER, RoleName.GOVERNOR, RoleName.AUDITOR)
)
# The directory user a super admin acts through inside an organization he entered.
PLATFORM_ISSUER = "platform"
SUPPORT_READ_ONLY_DETAIL = "A support session is read-only"
SUPER_ADMIN_ONLY_DETAIL = "Only a super admin can do this"


@dataclass(frozen=True)
class Caller:
    """The authenticated caller of an organization request with every role grant it holds."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    grants: tuple[Grant, ...]
    everyone_teaches: bool
    kind: Literal["user", "platform"] = "user"
    read_only: bool = False
    # The super admin's platform account when the caller is him acting inside the organization.
    platform_account_id: uuid.UUID | None = None

    @property
    def actor(self) -> Actor:
        return Actor(
            kind=self.kind,
            id=self.user_id,
            name=self.name,
            platform_account_id=self.platform_account_id,
        )

    @property
    def actor_kind(self) -> ActorKind:
        return ActorKind(self.kind)


@dataclass(frozen=True)
class PlatformAdmin:
    """A signed-in super admin on a `/admin` request."""

    live: LiveSession
    client_ip: str | None

    @property
    def account_id(self) -> uuid.UUID:
        return self.live.account.id

    @property
    def name(self) -> str:
        return self.live.account.name

    @property
    def actor(self) -> Actor:
        return Actor(kind="platform", id=self.account_id, name=self.name)


SessionDependency = Annotated[AsyncSession, Depends(session_dependency, scope="function")]
PlatformSessionDependency = Annotated[
    AsyncSession, Depends(platform_session_dependency, scope="function")
]


async def get_caller(request: Request, session: SessionDependency) -> Caller:
    """FastAPI dependency: the caller, with its organization bound to the request session;
    401 when no accepted credential identifies one."""
    token = request.cookies.get(SESSION_COOKIE)
    if is_well_formed(token):
        assert token is not None
        resolved = await _resolve(token)
        if resolved is not None:
            return await _session_caller(request, session, resolved)
    subject = request.headers.get(DEV_USER_HEADER)
    if subject and get_settings().accepts_dev_identity_header:
        return await _dev_caller(session, subject)
    raise unauthorized(SIGN_IN_REQUIRED)


async def get_platform_admin(request: Request, session: PlatformSessionDependency) -> PlatformAdmin:
    """FastAPI dependency for `/admin`: a live session of an account holding `super_admin`."""
    live = await session_service.find_live(session, request.cookies.get(SESSION_COOKIE))
    if live is None:
        raise unauthorized(SIGN_IN_REQUIRED)
    if request.method not in SAFE_METHODS:
        require_csrf(request, live.row.csrf_token)
    if live.resolved.must_change_password:
        raise ProblemError(403, "password_change_required", PASSWORD_CHANGE_DETAIL)
    roles = await platform_role_repository.roles_of(session, live.account.id)
    if not live.account.is_platform or PlatformRoleName.SUPER_ADMIN not in roles:
        raise forbidden(SUPER_ADMIN_ONLY_DETAIL)
    return PlatformAdmin(live=live, client_ip=request_client_ip(request))


def platform_user_subject(account_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    """The subject of a super admin's directory user in an organization. Subjects are unique
    across every issuer, so the organization is part of it."""
    return f"{account_id}:{tenant_id}"


def require_csrf(request: Request, expected: str) -> None:
    """403 `csrf_failed` unless the `Origin` is allowed and `X-CSRF-Token` matches."""
    if not origin_allowed(request) or not tokens_equal(request.headers.get(CSRF_HEADER), expected):
        raise ProblemError(403, "csrf_failed", CSRF_DETAIL)


def origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    return origin is not None and origin in get_settings().allowed_origins


def request_client_ip(request: Request) -> str | None:
    return client_ip(
        request.headers.get(FORWARDED_FOR),
        request.client.host if request.client else None,
        get_settings().trusted_proxy_hops,
    )


def set_session_cookie(response: Response, token: str) -> None:
    """The session cookie: host-only, HTTPS-only, invisible to scripts, no persistent expiry."""
    response.set_cookie(SESSION_COOKIE, token, path="/", secure=True, httponly=True, samesite="lax")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


async def _resolve(token: str) -> ResolvedSession | None:
    """Resolve the cookie in its own short transaction, so the session row's lock is released
    before the request's work starts and parallel calls of one browser never queue on it."""
    async with db_client.get_session_factory()() as lookup:
        resolved = await auth_session_repository.resolve(lookup, token_digest(token))
        await lookup.commit()
    return resolved


async def _session_caller(
    request: Request, session: AsyncSession, resolved: ResolvedSession
) -> Caller:
    if request.method not in SAFE_METHODS:
        require_csrf(request, resolved.csrf_token)
    if resolved.must_change_password:
        raise ProblemError(403, "password_change_required", PASSWORD_CHANGE_DETAIL)
    if not resolved.is_platform:
        assert resolved.tenant_id is not None and resolved.user_id is not None
        return await _member_caller(session, resolved.tenant_id, resolved.user_id)
    if resolved.acting_tenant_id is not None:
        return await _acting_caller(session, resolved.acting_tenant_id, resolved.account_id)
    if resolved.support_tenant_id is None:
        raise forbidden(SUPPORT_ONLY_DETAIL)
    if request.method not in SAFE_METHODS:
        raise forbidden(SUPPORT_READ_ONLY_DETAIL)
    await db_client.bind_tenant(session, resolved.support_tenant_id)
    return Caller(
        tenant_id=resolved.support_tenant_id,
        user_id=resolved.account_id,
        name=SUPPORT_ACTOR_NAME,
        grants=SUPPORT_GRANTS,
        everyone_teaches=False,
        kind="platform",
        read_only=True,
    )


async def _acting_caller(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> Caller:
    """The super admin inside the organization he entered: its directory user of issuer
    `platform` (created at the entry), every tenant role, and the platform account as the
    audit marker. The organization is bound first, so the lookup runs under its RLS."""
    await db_client.bind_tenant(session, tenant_id)
    user = await app_user_repository.get_by_identity(
        session, PLATFORM_ISSUER, platform_user_subject(account_id, tenant_id)
    )
    if user is None or user.tenant_id != tenant_id:
        raise forbidden(ENTER_AGAIN_DETAIL)
    tenant_settings = await tenant_settings_repository.get(session, tenant_id)
    return Caller(
        tenant_id=tenant_id,
        user_id=user.id,
        name=user.name,
        grants=ACTING_GRANTS,
        everyone_teaches=bool(tenant_settings and tenant_settings.everyone_teaches),
        platform_account_id=account_id,
    )


async def _dev_caller(session: AsyncSession, subject: str) -> Caller:
    """The seeded `dev` user named by the header. Users of every organization are searched,
    so the lookup runs on the platform role; the request itself stays on the application role."""
    async with db_client.platform_session() as lookup:
        user = await app_user_repository.get_by_identity(lookup, DEV_ISSUER, subject)
    if user is None:
        raise unauthorized("Unknown user")
    return await _member_caller(session, user.tenant_id, user.id)


async def _member_caller(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Caller:
    await db_client.bind_tenant(session, tenant_id)
    user = await app_user_repository.get(session, tenant_id, user_id)
    if user is None:
        raise unauthorized("Unknown user")
    assignments = await group_role_repository.list_for_user(
        session, tenant_id, user.id, get_clock().now()
    )
    tenant_settings = await tenant_settings_repository.get(session, tenant_id)
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
        tenant_id=tenant_id,
        user_id=user.id,
        name=user.name,
        grants=grants,
        everyone_teaches=bool(tenant_settings and tenant_settings.everyone_teaches),
    )


CallerDependency = Annotated[Caller, Depends(get_caller)]
PlatformAdminDependency = Annotated[PlatformAdmin, Depends(get_platform_admin)]

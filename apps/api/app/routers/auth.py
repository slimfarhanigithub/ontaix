"""`/auth`: sign-in, sign-out, the current session and password change. No sign-up exists."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from app.auth import (
    SESSION_COOKIE,
    SIGN_IN_REQUIRED,
    PlatformSessionDependency,
    clear_session_cookie,
    origin_allowed,
    request_client_ip,
    require_csrf,
    set_session_cookie,
)
from app.models.api.session import PasswordChange, Session, SignInRequest
from app.services import auth_service, session_service
from app.services.auth_service import Attempt
from app.utilities.problems import ProblemError, unauthorized

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

LOGIN_CSRF_DETAIL = "Sign in from the Studio"


@router.post("/sign-in", response_model=Session)
async def sign_in(
    body: SignInRequest, request: Request, response: Response, session: PlatformSessionDependency
) -> Session:
    if not origin_allowed(request):
        raise ProblemError(403, "csrf_failed", LOGIN_CSRF_DETAIL)
    issued = await auth_service.sign_in(
        session, body.email, body.password, _attempt(request), request.cookies.get(SESSION_COOKIE)
    )
    set_session_cookie(response, issued.token)
    return issued.session


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(request: Request, session: PlatformSessionDependency) -> Response:
    live = await session_service.find_live(session, request.cookies.get(SESSION_COOKIE))
    if live is not None:
        require_csrf(request, live.row.csrf_token)
    await auth_service.sign_out(session, live, _attempt(request))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response


@router.get("/session", response_model=Session)
async def get_session(request: Request, session: PlatformSessionDependency) -> Session:
    token = request.cookies.get(SESSION_COOKIE)
    live = await session_service.find_live(session, token)
    if live is None:
        expired = await auth_service.record_expired(session, token, _attempt(request))
        await session.commit()
        raise _session_ended(clear_cookie=expired or token is not None)
    return await auth_service.current(session, live)


@router.put("/password", response_model=Session)
async def change_password(
    body: PasswordChange, request: Request, response: Response, session: PlatformSessionDependency
) -> Session:
    live = await session_service.find_live(session, request.cookies.get(SESSION_COOKIE))
    if live is None:
        raise unauthorized(SIGN_IN_REQUIRED)
    require_csrf(request, live.row.csrf_token)
    issued = await auth_service.change_password(
        session, live, body.current_password, body.new_password, _attempt(request)
    )
    set_session_cookie(response, issued.token)
    return issued.session


def _attempt(request: Request) -> Attempt:
    return Attempt(
        client_ip=request_client_ip(request), user_agent=request.headers.get("user-agent")
    )


def _session_ended(*, clear_cookie: bool) -> ProblemError:
    """401 for no live session; a dead cookie is cleared so the browser stops presenting it."""
    problem = unauthorized(SIGN_IN_REQUIRED)
    if clear_cookie:
        problem.headers = {
            "Set-Cookie": (
                f'{SESSION_COOKIE}=""; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=lax; '
                "expires=Thu, 01 Jan 1970 00:00:00 GMT"
            )
        }
    return problem

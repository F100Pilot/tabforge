"""US-07 login (ADR-0006): magic link by email, opaque session cookie, CSRF synchronizer token.

env=desktop (ADR-0008) swaps the magic link for the launcher's per-launch token
(`POST /v1/auth/desktop`); both open the same session with the same cookie and CSRF token.
"""

import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tabforge_api.auth import (
    MAX_TOKEN_LENGTH,
    SESSION_COOKIE,
    hash_token,
    magic_link_message,
    magic_link_url,
    new_token,
    normalize_email,
)
from tabforge_api.deps import (
    MailerDep,
    PrincipalDep,
    SessionDep,
    SettingsDep,
    find_auth_session,
    require_csrf,
    require_desktop,
    require_online,
)
from tabforge_api.limits import SlidingWindowLimiter
from tabforge_api.models import AuthSession, LoginToken, User
from tabforge_api.problems import ProblemError
from tabforge_api.settings import Settings

log = logging.getLogger("tabforge_api.auth")
router = APIRouter(prefix="/v1/auth", tags=["auth"])

# Login-link abuse limits (threat model T3): per address and per client IP, 15-minute window.
MAGIC_LINK_WINDOW_S = 15 * 60
MAGIC_LINK_PER_EMAIL = 5
MAGIC_LINK_PER_IP = 20
# Desktop launch-token login (ADR-0008): one local user, brute force capped per client IP.
DESKTOP_USER_EMAIL = "local@tabforge.desktop"
DESKTOP_LOGIN_PER_IP = 10
DESKTOP_LOGIN_WINDOW_S = 60


class MagicLinkIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        email = normalize_email(value)
        if email is None:
            raise ValueError("invalid email address")
        return email


class VerifyIn(BaseModel):
    token: str


class DesktopLoginIn(BaseModel):
    token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str | None


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email)


def _hit(limiter: SlidingWindowLimiter, key: str) -> None:
    retry_after = limiter.hit(key)
    if retry_after is not None:
        raise ProblemError(
            429,
            "rate_limited",
            "too many login requests; try again later",
            headers={"Retry-After": str(retry_after)},
        )


def set_session_cookie(response: Response, value: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        value,
        max_age=settings.session_ttl_days * 86400,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _get_or_create_user(session: Session, email: str) -> User:
    """`email` must already be normalized (lowercase)."""
    session.execute(
        insert(User)
        .values(email=email)
        .on_conflict_do_nothing(index_elements=[func.lower(User.email)])
    )
    return session.execute(select(User).where(func.lower(User.email) == email)).scalar_one()


def _open_session(
    request: Request, response: Response, session: Session, settings: Settings, user: User
) -> SessionOut:
    """New session + CSRF token for `user`, cookie set on `response` (commits)."""
    previous = find_auth_session(request, session)
    if previous is not None:  # no session fixation: a login always replaces the old session
        session.delete(previous)
    cookie, csrf = new_token(), new_token()
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(cookie),
            csrf_token=csrf,
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_ttl_days),
        )
    )
    session.commit()  # before the cookie leaves (yield dependencies exit after the response)
    set_session_cookie(response, cookie, settings)
    return SessionOut(user=_user_out(user), csrf_token=csrf)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/magic-link", status_code=202, dependencies=[Depends(require_online)])
def request_magic_link(
    body: MagicLinkIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    mailer: MailerDep,
) -> dict[str, str]:
    """Always 202 for a valid address: the answer never depends on whether an account exists."""
    _hit(request.app.state.magic_link_ip_limiter, _client_ip(request))
    _hit(request.app.state.magic_link_email_limiter, hash_token(body.email))

    token = new_token()
    session.add(
        LoginToken(
            email=body.email,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.login_token_ttl_s),
        )
    )
    session.commit()  # the link must be valid by the time the email arrives

    link = magic_link_url(str(settings.web_base_url), token)
    subject, text = magic_link_message(link, settings.login_token_ttl_s)
    try:
        mailer.send(body.email, subject, text)
    except Exception as exc:
        # No address or exception text in the log (it may carry the recipient).
        log.warning('{"event": "magic_link_send_failed", "error": "%s"}', type(exc).__name__)
        raise ProblemError(
            503, "mail_unavailable", "could not send the email; try again later"
        ) from exc
    return {}


@router.post("/verify", dependencies=[Depends(require_online)])
def verify(
    body: VerifyIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> SessionOut:
    """Consume the link (single use, atomic) and open a session."""
    invalid = ProblemError(400, "invalid_token", "the link is invalid, expired or already used")
    if not body.token or len(body.token) > MAX_TOKEN_LENGTH:
        raise invalid
    email = session.execute(
        update(LoginToken)
        .where(
            LoginToken.token_hash == hash_token(body.token),
            LoginToken.used_at.is_(None),
            LoginToken.expires_at > func.now(),
        )
        .values(used_at=func.now())
        .returning(LoginToken.email)
    ).scalar_one_or_none()
    if email is None:
        raise invalid
    user = _get_or_create_user(session, email)
    return _open_session(request, response, session, settings, user)


@router.post("/desktop", dependencies=[Depends(require_desktop)])
def desktop_login(
    body: DesktopLoginIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> SessionOut:
    """Exchange the launcher's per-launch token for the local user's session (ADR-0008)."""
    _hit(request.app.state.desktop_login_limiter, _client_ip(request))
    expected = settings.desktop_launch_token
    if expected is None or not hmac.compare_digest(
        body.token.encode(), expected.get_secret_value().encode()
    ):
        raise ProblemError(403, "invalid_launch_token", "invalid launch token")
    user = _get_or_create_user(session, DESKTOP_USER_EMAIL)
    return _open_session(request, response, session, settings, user)


@router.get("/session")
def current_session(principal: PrincipalDep) -> SessionOut:
    csrf = principal.auth_session.csrf_token if principal.auth_session else None
    return SessionOut(user=_user_out(principal.user), csrf_token=csrf)


@router.post("/logout", status_code=204)
def logout(
    request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> None:
    """Idempotent: 204 with or without a session. With one, the CSRF token is required."""
    auth_session = find_auth_session(request, session)
    if auth_session is not None:
        require_csrf(request, auth_session)
        session.delete(auth_session)
        session.commit()
    clear_session_cookie(response, settings)

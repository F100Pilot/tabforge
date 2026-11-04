"""Request-scoped dependencies: settings, DB session, object store, mailer, current user."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tabforge_api.auth import (
    CSRF_HEADER,
    SESSION_COOKIE,
    csrf_matches,
    hash_token,
    is_unsafe_method,
)
from tabforge_api.db import session_scope
from tabforge_api.mailer import Mailer
from tabforge_api.models import AuthSession, User
from tabforge_api.problems import ProblemError
from tabforge_api.settings import Settings
from tabforge_api.storage import ObjectStore

DEV_USER_EMAIL = "dev@tabforge.local"


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.session_factory)


def get_store(request: Request) -> ObjectStore:
    store: ObjectStore = request.app.state.store
    return store


def get_mailer(request: Request) -> Mailer:
    mailer: Mailer = request.app.state.mailer
    return mailer


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
StoreDep = Annotated[ObjectStore, Depends(get_store)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is calling. `auth_session` is None on the dev_auth fallback (no cookie, no CSRF)."""

    user: User
    auth_session: AuthSession | None


def find_auth_session(request: Request, session: Session) -> AuthSession | None:
    """The unexpired session named by the cookie, if any."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    return session.execute(
        select(AuthSession).where(
            AuthSession.token_hash == hash_token(cookie), AuthSession.expires_at > func.now()
        )
    ).scalar_one_or_none()


def require_csrf(request: Request, auth_session: AuthSession) -> None:
    """Synchronizer token (threat model T4): unsafe methods must echo the session's token."""
    if is_unsafe_method(request.method) and not csrf_matches(
        auth_session.csrf_token, request.headers.get(CSRF_HEADER)
    ):
        raise ProblemError(403, "csrf_failed", "missing or invalid CSRF token")


def _dev_user(session: Session) -> User:
    session.execute(
        insert(User)
        .values(email=DEV_USER_EMAIL)
        .on_conflict_do_nothing(index_elements=[func.lower(User.email)])
    )
    return session.execute(
        select(User).where(func.lower(User.email) == DEV_USER_EMAIL)
    ).scalar_one()


def get_principal(request: Request, session: SessionDep, settings: SettingsDep) -> Principal:
    """Session cookie first; else the dev_auth fallback (env=dev only); else 401."""
    auth_session = find_auth_session(request, session)
    if auth_session is not None:
        require_csrf(request, auth_session)
        user = session.get(User, auth_session.user_id)
        if user is not None:
            return Principal(user, auth_session)
    if settings.dev_auth:
        return Principal(_dev_user(session), None)
    raise ProblemError(401, "unauthenticated", "authentication required")


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def get_current_user(principal: PrincipalDep) -> User:
    """Routes depend only on this (or CurrentUser)."""
    return principal.user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_online(settings: SettingsDep) -> None:
    """Routes that do not exist in env=desktop (email login, ADR-0008)."""
    if settings.env == "desktop":
        raise ProblemError(404, "not_found", "Not Found")


def require_desktop(settings: SettingsDep) -> None:
    """Routes that exist only in env=desktop (launch-token login, ADR-0008)."""
    if settings.env != "desktop":
        raise ProblemError(404, "not_found", "Not Found")


def limit_writes(request: Request, user: CurrentUser) -> None:
    """Per-user rate limit for state-changing routes (threat model T3)."""
    retry_after = request.app.state.write_limiter.hit(str(user.id))
    if retry_after is not None:
        raise ProblemError(
            429,
            "rate_limited",
            "too many requests; try again shortly",
            headers={"Retry-After": str(retry_after)},
        )

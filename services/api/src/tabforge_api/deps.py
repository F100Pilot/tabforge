"""Request-scoped dependencies: settings, DB session, object store, current user."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tabforge_api.db import session_scope
from tabforge_api.models import User
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


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
StoreDep = Annotated[ObjectStore, Depends(get_store)]


def get_current_user(session: SessionDep, settings: SettingsDep) -> User:
    """M1 stub: the fixed dev user when dev_auth is on; otherwise nobody (401).

    US-07 (M2) replaces this with session-cookie auth; routes depend only on this function.
    """
    if not settings.dev_auth:
        raise ProblemError(401, "unauthenticated", "authentication required")
    session.execute(
        insert(User)
        .values(email=DEV_USER_EMAIL)
        .on_conflict_do_nothing(index_elements=[func.lower(User.email)])
    )
    return session.execute(
        select(User).where(func.lower(User.email) == DEV_USER_EMAIL)
    ).scalar_one()


CurrentUser = Annotated[User, Depends(get_current_user)]

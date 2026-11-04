"""US-07 account deletion (RGPD art. 17): audio objects, then every row of the user."""

import logging

from fastapi import APIRouter, Response
from sqlalchemy import delete, select

from tabforge_api.deps import CurrentUser, SessionDep, SettingsDep, StoreDep
from tabforge_api.models import AudioAsset, LoginToken, User
from tabforge_api.problems import ProblemError
from tabforge_api.routes.auth import clear_session_cookie

log = logging.getLogger("tabforge_api.me")
router = APIRouter(prefix="/v1/me", tags=["account"])


@router.delete("", status_code=204)
def delete_account(
    user: CurrentUser,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
) -> None:
    """Storage first: if it fails nothing is deleted from the database and the user can retry.

    S3 deletes are idempotent, so a retry after a partial failure is safe. Rows go in one
    statement: users cascades to audio_assets, jobs, tabs, tab_revisions and sessions.
    """
    keys = (
        session.execute(
            select(AudioAsset.storage_key).where(
                AudioAsset.user_id == user.id, AudioAsset.status != "expired"
            )
        )
        .scalars()
        .all()
    )
    try:
        for key in keys:
            store.delete(key)
    except Exception as exc:
        log.warning('{"event": "account_delete_storage_failed", "user": "%s"}', user.id)
        raise ProblemError(
            503, "storage_unavailable", "could not delete stored audio; try again later"
        ) from exc
    session.execute(delete(LoginToken).where(LoginToken.email == user.email.lower()))
    session.execute(delete(User).where(User.id == user.id))
    session.commit()
    log.info('{"event": "account_deleted", "user": "%s"}', user.id)
    clear_session_cookie(response, settings)

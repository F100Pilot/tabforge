"""Relational model (docs/architecture.md). Schema changes go through Alembic migrations."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

AUDIO_STATUSES = ("pending_upload", "uploaded", "rejected", "expired")
AUDIO_SOURCE_KINDS = ("mix", "guitar_stem")
JOB_STATUSES = ("queued", "running", "done", "failed")
JOB_STAGES = ("normalizing", "separating", "transcribing", "arranging")
TAB_VISIBILITIES = ("private", "unlisted", "public")
REVISION_SOURCES = ("ai", "user", "learned")  # learned: ADR-0016
PROFILE_STATUSES = ("stale", "ready", "insufficient")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("uq_users_email_lower", func.lower(email), unique=True),)


class LoginToken(Base):
    """Single-use magic-link token (US-07). Only the SHA-256 of the token is stored."""

    __tablename__ = "login_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False)  # lowercased
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    """Opaque server-side session (ADR-0006). The cookie value is stored only as SHA-256."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AudioAsset(Base):
    __tablename__ = "audio_assets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending_upload")
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    sha256: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in("status", AUDIO_STATUSES), name="status"),
        CheckConstraint(_in("source_kind", AUDIO_SOURCE_KINDS), name="source_kind"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
    )


class Tab(Base):
    __tablename__ = "tabs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    tuning: Mapped[str] = mapped_column(Text, nullable=False, server_default="E standard")
    visibility: Mapped[str] = mapped_column(Text, nullable=False, server_default="private")
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tab_revisions.id", use_alter=True, ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint(_in("visibility", TAB_VISIBILITIES), name="visibility"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="title_length"),
    )


class TabRevision(Base):
    """Immutable: never updated after insert (US-04)."""

    __tablename__ = "tab_revisions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tab_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tabs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (CheckConstraint(_in("source", REVISION_SOURCES), name="source"),)


class TabReference(Base):
    """The correct tab of the same song, reduced to note events (ADR-0009).

    One per tab and track of the tab (ADR-0010); `track` is the name of the track it was read
    from in the Guitar Pro file, `track_index` the tab's own track it is compared with.
    """

    __tablename__ = "tab_references"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tab_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tabs.id", ondelete="CASCADE"), nullable=False
    )
    track_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    track: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        UniqueConstraint("tab_id", "track_index", name="uq_tab_references_tab_id_track_index"),
        CheckConstraint("track_index >= 0", name="track_index_non_negative"),
    )


class FrettingProfile(Base):
    """String/fret weights learnt from the user's correct tabs (ADR-0011); one per user.

    The API marks it `stale` (with `requested_at`) when the training data changes; the worker
    refreshes it to `ready` (tuned, `weights` set only if they beat the default) or
    `insufficient` (too few notes or tabs).
    """

    __tablename__ = "fretting_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    weights: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    default_accuracy: Mapped[float | None] = mapped_column(Float)
    tuned_accuracy: Mapped[float | None] = mapped_column(Float)
    tabs: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="stale")
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint(_in("status", PROFILE_STATUSES), name="status"),)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    audio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    stage: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tab_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tabs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES), name="status"),
        CheckConstraint(f"stage IS NULL OR {_in('stage', JOB_STAGES)}", name="stage"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        # Queue scan: oldest queued first (worker uses FOR UPDATE SKIP LOCKED).
        Index("ix_jobs_queued", "created_at", postgresql_where=text("status = 'queued'")),
    )

"""Relational model (docs/architecture.md). Schema changes go through Alembic migrations."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
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
REVISION_SOURCES = ("ai", "user")


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

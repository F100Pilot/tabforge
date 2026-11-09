from datetime import timedelta
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_PRESIGN_TTL_S = 300  # threat model T6: pre-signed URLs expire within 5 minutes
MIN_SECRET_LENGTH = 32  # desktop launch token and upload HMAC key (the launcher generates 43)
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


class Settings(BaseSettings):
    """Runtime configuration from environment variables (12-factor)."""

    model_config = SettingsConfigDict(env_prefix="TABFORGE_", extra="ignore")

    # desktop: single-user Windows app on loopback (ADR-0008); see _desktop_is_local_only.
    env: Literal["dev", "test", "prod", "desktop"] = "dev"
    database_url: PostgresDsn
    cors_origins: list[str] = []

    # Dev fallback: requests without a session cookie act as one fixed dev user.
    # Refused outside env=dev, so prod fails closed (401). Real auth: US-07, ADR-0006.
    dev_auth: bool = False

    # US-07 auth (ADR-0006): magic link by email + opaque session cookie.
    web_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")  # where the link points
    login_token_ttl_s: int = Field(default=900, gt=0, le=3600)
    session_ttl_days: int = Field(default=30, gt=0, le=365)
    # Threat model T4. Only dev over plain http turns this off.
    session_cookie_secure: bool = True

    # Generic SMTP (Mailpit in dev). Unset: env=dev logs the link; other envs refuse to start.
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, gt=0, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    mail_from: str = "TabForge <no-reply@tabforge.local>"

    # Object storage (S3 API). Endpoints unset = AWS defaults.
    s3_endpoint_url: AnyHttpUrl | None = None
    # Host the browser uses for pre-signed URLs (differs from the in-cluster endpoint in dev).
    s3_public_endpoint_url: AnyHttpUrl | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "tabforge-audio"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None

    # Desktop (ADR-0008): files in a folder instead of S3, uploaded with a signed PUT to the API.
    storage_backend: Literal["s3", "local"] = "s3"
    local_storage_dir: Path | None = None
    local_upload_secret: SecretStr | None = None  # HMAC-SHA256 key for the upload URLs
    # Base of the signed upload URLs the browser PUTs to (the API's own loopback address).
    api_public_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:47801")
    # Per-launch secret the launcher exchanges for a session at POST /v1/auth/desktop.
    desktop_launch_token: SecretStr | None = None
    # YouTube import (ADR-0014, desktop only): the bundle's ffmpeg (MP3) and Node (yt-dlp's
    # JavaScript runtime for YouTube), and the folder that keeps a copy of each MP3.
    ffmpeg: Path | None = None
    node: Path | None = None
    music_dir: Path | None = None
    max_audio_duration_s: float = Field(default=600.0, gt=0)  # the worker's US-01 limit

    # US-01 limits and privacy (PRD §5).
    upload_max_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    presign_ttl_s: int = Field(default=MAX_PRESIGN_TTL_S, gt=0, le=MAX_PRESIGN_TTL_S)
    audio_retention_days: int = Field(default=30, gt=0)

    # Abuse limits (threat model T3).
    write_rate_per_minute: int = Field(default=30, gt=0)
    daily_upload_limit: int = Field(default=20, gt=0)

    @model_validator(mode="after")
    def _dev_auth_only_in_dev(self) -> Self:
        if self.dev_auth and self.env != "dev":
            raise ValueError("dev_auth is only allowed with env=dev")
        return self

    @model_validator(mode="after")
    def _desktop_is_local_only(self) -> Self:
        """Fail closed: desktop needs every local secret; local storage never runs online."""
        if self.env == "desktop":
            if self.storage_backend != "local":
                raise ValueError("env=desktop requires storage_backend=local")
            if self.desktop_launch_token is None:
                raise ValueError("env=desktop requires desktop_launch_token")
            if self.api_public_url.host not in LOOPBACK_HOSTS:
                raise ValueError("env=desktop requires a loopback api_public_url")
        if self.storage_backend == "local":
            if self.env not in {"desktop", "test"}:
                raise ValueError("storage_backend=local is only allowed with env=desktop or test")
            if self.local_storage_dir is None or self.local_upload_secret is None:
                raise ValueError(
                    "storage_backend=local requires local_storage_dir and local_upload_secret"
                )
        for name in ("desktop_launch_token", "local_upload_secret"):
            secret: SecretStr | None = getattr(self, name)
            if secret is not None and len(secret.get_secret_value()) < MIN_SECRET_LENGTH:
                raise ValueError(f"{name} must have at least {MIN_SECRET_LENGTH} characters")
        return self

    @property
    def daily_upload_quota(self) -> int | None:
        """Uploads per user per 24 h; None = no quota (desktop: one local user, ADR-0008)."""
        return None if self.env == "desktop" else self.daily_upload_limit

    @property
    def audio_retention(self) -> timedelta | None:
        """How long original audio is kept; None = kept until the user deletes it (desktop)."""
        return None if self.env == "desktop" else timedelta(days=self.audio_retention_days)

    @property
    def sqlalchemy_url(self) -> str:
        """`database_url` with the psycopg 3 driver selected."""
        url = str(self.database_url)
        scheme, sep, rest = url.partition("://")
        if scheme in {"postgres", "postgresql"}:
            return f"postgresql+psycopg{sep}{rest}"
        return url

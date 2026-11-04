from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_PRESIGN_TTL_S = 300  # threat model T6: pre-signed URLs expire within 5 minutes


class Settings(BaseSettings):
    """Runtime configuration from environment variables (12-factor)."""

    model_config = SettingsConfigDict(env_prefix="TABFORGE_", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
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

    @property
    def sqlalchemy_url(self) -> str:
        """`database_url` with the psycopg 3 driver selected."""
        url = str(self.database_url)
        scheme, sep, rest = url.partition("://")
        if scheme in {"postgres", "postgresql"}:
            return f"postgresql+psycopg{sep}{rest}"
        return url

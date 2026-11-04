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

    # Walking-skeleton auth (M1): every request acts as one fixed dev user.
    # Real auth is US-07 (M2). Refused outside env=dev, so prod fails closed (401).
    dev_auth: bool = False

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

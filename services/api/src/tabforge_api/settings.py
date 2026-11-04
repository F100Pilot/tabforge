from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration from environment variables (12-factor)."""

    model_config = SettingsConfigDict(env_prefix="TABFORGE_", extra="ignore")

    env: str = "dev"
    database_url: PostgresDsn
    cors_origins: list[str] = []

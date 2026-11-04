"""Alembic environment: online migrations only, URL from Settings (env vars)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from tabforge_api.models import Base
from tabforge_api.settings import Settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = config.attributes.get("database_url") or Settings().sqlalchemy_url  # type: ignore[call-arg]

engine = create_engine(url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()

"""Alembic environment configuration — reads DATABASE_URL from pydantic-settings."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings
from app.db.models import Base  # noqa: F401 — imports all models

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from environment
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_async_engine(settings.DATABASE_URL)

    import asyncio

    async def _run() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(_do_run_migrations)
        await connectable.dispose()

    def _do_run_migrations(sync_conn: object) -> None:
        context.configure(connection=sync_conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    asyncio.run(_run())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

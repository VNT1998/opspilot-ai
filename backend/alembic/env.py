import asyncio
from logging.config import fileConfig
import os
from pathlib import Path
import sys

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings
from app.db.base import Base

# Import all models to ensure metadata registration
import app.models.audit  # noqa
import app.models.document  # noqa
import app.models.erp  # noqa
import app.models.extraction  # noqa
import app.models.knowledge  # noqa
import app.models.outbox  # noqa
import app.models.review  # noqa
import app.models.tenant  # noqa
import app.models.user  # noqa
import app.models.workflow  # noqa

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = get_settings()
    url = os.getenv("DATABASE_URL") or settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    settings = get_settings()
    url = os.getenv("DATABASE_URL") or settings.DATABASE_URL
    connectable = create_async_engine(url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

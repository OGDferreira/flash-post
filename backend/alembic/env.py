import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = get_settings().database_url_value()

config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata
_migration_lock_id = 647219084113


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


_LOCK_TIMEOUT = "15s"
_ATTEMPTS = 8


def _release_stuck_sessions(connection) -> None:
    """End sessions of this database left "idle in transaction", or inside one
    transaction for minutes (e.g. a hung worker of the previous release); they
    hold locks that would block the DDL forever."""
    try:
        ended = connection.execute(
            text(
                "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                "AND ((state LIKE 'idle in transaction%' AND state_change < now() - interval '30 seconds') "
                "OR xact_start < now() - interval '3 minutes')"
            )
        ).scalar()
        connection.commit()
        if ended:
            print(f"[migrations] ended {ended} stuck session(s)", flush=True)
    except Exception as exc:  # no permission on a pooled/managed database: keep going
        connection.rollback()
        print(f"[migrations] could not end stuck sessions: {type(exc).__name__}", flush=True)


def do_run_migrations(connection) -> None:
    lock_acquired = connection.dialect.name == "postgresql"
    if lock_acquired:
        connection.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": _migration_lock_id})
        connection.commit()
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        if not lock_acquired:
            with context.begin_transaction():
                context.run_migrations()
            return
        # Never wait forever for a table lock: fail the attempt, free stuck
        # sessions and retry, so a deploy either finishes or fails with a reason.
        for attempt in range(1, _ATTEMPTS + 1):
            _release_stuck_sessions(connection)
            try:
                with context.begin_transaction():
                    connection.execute(text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'"))
                    context.run_migrations()
                print("[migrations] up to date", flush=True)
                return
            except Exception as exc:
                if connection.in_transaction():
                    connection.rollback()
                if "lock timeout" not in str(exc).lower() or attempt == _ATTEMPTS:
                    raise
                print(f"[migrations] table busy, retrying ({attempt}/{_ATTEMPTS})", flush=True)
    finally:
        if lock_acquired:
            if connection.in_transaction():
                connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _migration_lock_id},
            )


async def run_migrations_online() -> None:
    connect_args = {"ssl": "require"} if database_url.startswith("postgresql+asyncpg://") else {}
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

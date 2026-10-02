import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_nickname_migration_backfills_existing_users(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-users.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "ENVIRONMENT": "test",
            "SESSION_SECRET": "migration-test-session-secret",
        }
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "20261002_01",
        ],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database_path) as connection:
        for username, email in (
            ("GuiOps", "first@example.com"),
            (None, "guiops@example.com"),
            (None, "legacy.user@example.com"),
        ):
            connection.execute(
                """
                INSERT INTO users (id, email, username, password_hash, full_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), email, username, "test-hash", "Legacy User"),
            )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "head",
        ],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database_path) as connection:
        nicknames = [
            row[0]
            for row in connection.execute(
                "SELECT nickname FROM users ORDER BY created_at, id"
            )
        ]
        index = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            ("uq_users_nickname_lower",),
        ).fetchone()

    assert len(nicknames) == 3
    assert {nickname.casefold() for nickname in nicknames} == {
        "guiops",
        "guiops1",
        "legacy.user",
    }
    assert index is not None and "UNIQUE" in index[0].upper()

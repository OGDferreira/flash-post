import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_public_nickname_migration_preserves_and_normalizes_existing_users(
    tmp_path: Path,
) -> None:
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
            "20261002_02",
        ],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database_path) as connection:
        users = connection.execute(
            "SELECT id FROM users ORDER BY created_at, id"
        ).fetchall()
        for user, nickname in zip(
            users,
            ("   Gui   Ferreira  ", "00 do Site", "Guilherme 🚀"),
            strict=True,
        ):
            connection.execute(
                "UPDATE users SET nickname = ? WHERE id = ?",
                (nickname, user[0]),
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
        nicknames = connection.execute(
            "SELECT nickname, nickname_normalized FROM users ORDER BY created_at, id"
        ).fetchall()
        index = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            ("uq_users_nickname_normalized",),
        ).fetchone()

    assert len(nicknames) == 3
    assert nicknames == [
        ("Gui Ferreira", "gui ferreira"),
        ("00 do Site", "00 do site"),
        ("Guilherme 🚀", "guilherme 🚀"),
    ]
    assert index is not None and "UNIQUE" in index[0].upper()

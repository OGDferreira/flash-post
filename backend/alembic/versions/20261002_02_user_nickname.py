"""Add normalized, unique user nicknames.

Revision ID: 20261002_02
Revises: 20261002_01
Create Date: 2026-10-02
"""

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_02"
down_revision: Union[str, None] = "20261002_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_nicknames() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, username, email FROM users ORDER BY created_at, id")
    ).mappings()
    used: set[str] = set()
    for row in rows:
        source = row["username"] or row["email"].split("@", 1)[0]
        nickname = re.sub(r"[^A-Za-z0-9_.]", "_", source).casefold()
        if len(nickname) < 3:
            nickname = f"user{str(row['id']).replace('-', '')[:8]}"
        nickname = nickname[:30]
        base = nickname
        suffix = 1
        while nickname in used:
            suffix_text = str(suffix)
            nickname = f"{base[:30 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        used.add(nickname)
        connection.execute(
            sa.text("UPDATE users SET nickname = :nickname WHERE id = :user_id"),
            {"nickname": nickname, "user_id": row["id"]},
        )


def upgrade() -> None:
    op.add_column("users", sa.Column("nickname", sa.String(length=30), nullable=True))
    _backfill_nicknames()
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("nickname", existing_type=sa.String(length=30), nullable=False)
    else:
        op.alter_column("users", "nickname", existing_type=sa.String(length=30), nullable=False)
    op.create_index(
        "uq_users_nickname_lower",
        "users",
        [sa.text("lower(nickname)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_nickname_lower", table_name="users")
    op.drop_column("users", "nickname")

"""Store public nicknames separately from their comparison key.

Revision ID: 20261002_03
Revises: 20261002_02
Create Date: 2026-10-02
"""

import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_03"
down_revision: Union[str, None] = "20261002_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_display(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split()))


def upgrade() -> None:
    op.drop_index("uq_users_nickname_lower", table_name="users")
    op.add_column(
        "users",
        sa.Column("nickname_normalized", sa.String(length=160), nullable=True),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, nickname FROM users ORDER BY created_at, id")
    ).mappings()
    for row in rows:
        display = _normalize_display(row["nickname"])
        connection.execute(
            sa.text(
                "UPDATE users SET nickname = :display, nickname_normalized = :normalized "
                "WHERE id = :user_id"
            ),
            {
                "display": display,
                "normalized": display.casefold(),
                "user_id": row["id"],
            },
        )

    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "nickname",
                existing_type=sa.String(length=30),
                type_=sa.String(length=40),
                existing_nullable=False,
            )
            batch_op.alter_column(
                "nickname_normalized",
                existing_type=sa.String(length=160),
                nullable=False,
            )
    else:
        op.alter_column(
            "users",
            "nickname",
            existing_type=sa.String(length=30),
            type_=sa.String(length=40),
            existing_nullable=False,
        )
        op.alter_column(
            "users",
            "nickname_normalized",
            existing_type=sa.String(length=160),
            nullable=False,
        )
    op.create_index(
        "uq_users_nickname_normalized",
        "users",
        ["nickname_normalized"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_nickname_normalized", table_name="users")
    op.drop_column("users", "nickname_normalized")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "nickname",
                existing_type=sa.String(length=40),
                type_=sa.String(length=30),
                existing_nullable=False,
            )
    else:
        op.alter_column(
            "users",
            "nickname",
            existing_type=sa.String(length=40),
            type_=sa.String(length=30),
            existing_nullable=False,
        )
    op.create_index(
        "uq_users_nickname_lower",
        "users",
        [sa.text("lower(nickname)")],
        unique=True,
    )

"""User CPF column + partial unique index.

Additive only: a nullable 11-digit ``cpf`` on ``users``. Existing accounts keep
NULL (incomplete profile) until they fill it in. The unique index ignores NULLs,
so many incomplete accounts coexist while each real CPF stays unique.

Revision ID: 20261114_79
Revises: 20261113_78
Create Date: 2026-11-14 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261114_79"
down_revision: Union[str, None] = "20261113_78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("cpf", sa.String(length=11), nullable=True))
    op.create_index(
        "uq_users_cpf",
        "users",
        ["cpf"],
        unique=True,
        postgresql_where=sa.text("cpf IS NOT NULL"),
        sqlite_where=sa.text("cpf IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_cpf", table_name="users")
    op.drop_column("users", "cpf")

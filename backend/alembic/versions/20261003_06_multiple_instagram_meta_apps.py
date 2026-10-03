"""Allow multiple named Instagram Meta apps per workspace.

Revision ID: 20261003_06
Revises: 20261003_05
Create Date: 2026-10-03
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_06"
down_revision: Union[str, None] = "20261003_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instagram_meta_apps",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("meta_app_name", sa.String(length=160), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("app_link", sa.String(length=2048), nullable=True),
        sa.Column("encrypted_app_secret", sa.String(length=2048), nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("revision", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "app_id",
            name="uq_instagram_meta_apps_workspace_app",
        ),
    )
    op.create_index(
        "ix_instagram_meta_apps_workspace_id",
        "instagram_meta_apps",
        ["workspace_id"],
    )
    op.create_index(
        "uq_instagram_meta_apps_selected_workspace",
        "instagram_meta_apps",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("is_selected = true"),
        sqlite_where=sa.text("is_selected = 1"),
    )

    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.add_column(
            sa.Column("app_credential_id", sa.Uuid(as_uuid=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_instagram_accounts_app_credential_id",
            "instagram_meta_apps",
            ["app_credential_id"],
            ["id"],
            ondelete="SET NULL",
        )

    connection = op.get_bind()
    legacy_apps = sa.table(
        "instagram_app_credentials",
        sa.column("workspace_id", sa.Uuid(as_uuid=True)),
        sa.column("app_id", sa.String(length=64)),
        sa.column("encrypted_app_secret", sa.String(length=2048)),
        sa.column("revision", sa.Uuid(as_uuid=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    meta_apps = sa.table(
        "instagram_meta_apps",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("workspace_id", sa.Uuid(as_uuid=True)),
        sa.column("display_name", sa.String(length=120)),
        sa.column("meta_app_name", sa.String(length=160)),
        sa.column("app_id", sa.String(length=64)),
        sa.column("category", sa.String(length=120)),
        sa.column("app_link", sa.String(length=2048)),
        sa.column("encrypted_app_secret", sa.String(length=2048)),
        sa.column("is_selected", sa.Boolean()),
        sa.column("revision", sa.Uuid(as_uuid=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    accounts = sa.table(
        "instagram_accounts",
        sa.column("workspace_id", sa.Uuid(as_uuid=True)),
        sa.column("app_credential_id", sa.Uuid(as_uuid=True)),
    )
    for legacy in connection.execute(sa.select(legacy_apps)).mappings():
        app_id = legacy["app_id"]
        meta_app_id = uuid.uuid4()
        connection.execute(
            meta_apps.insert().values(
                id=meta_app_id,
                workspace_id=legacy["workspace_id"],
                display_name=f"Aplicativo Meta {app_id}"[:120],
                meta_app_name=f"Aplicativo Meta {app_id}"[:160],
                app_id=app_id,
                category=None,
                app_link=None,
                encrypted_app_secret=legacy["encrypted_app_secret"],
                is_selected=True,
                revision=legacy["revision"],
                updated_at=legacy["updated_at"],
            )
        )
        connection.execute(
            accounts.update()
            .where(accounts.c.workspace_id == legacy["workspace_id"])
            .values(app_credential_id=meta_app_id)
        )

    op.drop_table("instagram_app_credentials")


def downgrade() -> None:
    op.create_table(
        "instagram_app_credentials",
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("encrypted_app_secret", sa.String(length=2048), nullable=False),
        sa.Column("revision", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    connection = op.get_bind()
    meta_apps = sa.table(
        "instagram_meta_apps",
        sa.column("workspace_id", sa.Uuid(as_uuid=True)),
        sa.column("app_id", sa.String(length=64)),
        sa.column("encrypted_app_secret", sa.String(length=2048)),
        sa.column("revision", sa.Uuid(as_uuid=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("is_selected", sa.Boolean()),
    )
    legacy_apps = sa.table(
        "instagram_app_credentials",
        sa.column("workspace_id", sa.Uuid(as_uuid=True)),
        sa.column("app_id", sa.String(length=64)),
        sa.column("encrypted_app_secret", sa.String(length=2048)),
        sa.column("revision", sa.Uuid(as_uuid=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for selected in connection.execute(
        sa.select(meta_apps).where(meta_apps.c.is_selected.is_(True))
    ).mappings():
        connection.execute(
            legacy_apps.insert().values(
                workspace_id=selected["workspace_id"],
                app_id=selected["app_id"],
                encrypted_app_secret=selected["encrypted_app_secret"],
                revision=selected["revision"],
                updated_at=selected["updated_at"],
            )
        )

    with op.batch_alter_table("instagram_accounts") as batch_op:
        batch_op.drop_constraint(
            "fk_instagram_accounts_app_credential_id",
            type_="foreignkey",
        )
        batch_op.drop_column("app_credential_id")
    op.drop_index(
        "uq_instagram_meta_apps_selected_workspace",
        table_name="instagram_meta_apps",
    )
    op.drop_index("ix_instagram_meta_apps_workspace_id", table_name="instagram_meta_apps")
    op.drop_table("instagram_meta_apps")

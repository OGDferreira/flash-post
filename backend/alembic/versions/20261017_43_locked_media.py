"""Media copied from a chief's shared loop/funnel is locked for the partner.

Additive; backfills the copies made before this change.

Revision ID: 20261017_43
Revises: 20261017_42
Create Date: 2026-10-17 18:00:00
"""
import json
import re
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261017_43"
down_revision: Union[str, None] = "20261017_42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def upgrade() -> None:
    for table in ("instagram_media", "tg_media"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()))

    bind = op.get_bind()
    loops = sa.table("instagram_loops", sa.column("id", sa.Uuid()), sa.column("workspace_id", sa.Uuid()),
                     sa.column("template_loop_id", sa.Uuid()))
    loop_media = sa.table("instagram_loop_media", sa.column("loop_id", sa.Uuid()), sa.column("media_id", sa.Uuid()))
    ig_media = sa.table("instagram_media", sa.column("id", sa.Uuid()), sa.column("locked", sa.Boolean()))
    template = loops.alias("template")
    ids = list(bind.execute(
        sa.select(loop_media.c.media_id)
        .join(loops, loops.c.id == loop_media.c.loop_id)
        .join(template, template.c.id == loops.c.template_loop_id)
        .where(template.c.workspace_id != loops.c.workspace_id)
    ).scalars())
    if ids:
        bind.execute(ig_media.update().where(ig_media.c.id.in_(ids)).values(locked=True))

    flows = sa.table("tg_flows", sa.column("id", sa.Uuid()), sa.column("workspace_id", sa.Uuid()),
                     sa.column("template_flow_id", sa.Uuid()), sa.column("definition", sa.JSON()))
    tg_media = sa.table("tg_media", sa.column("id", sa.Uuid()), sa.column("workspace_id", sa.Uuid()),
                        sa.column("locked", sa.Boolean()))
    ftemplate = flows.alias("ftemplate")
    for workspace_id, definition in bind.execute(
        sa.select(flows.c.workspace_id, flows.c.definition)
        .join(ftemplate, ftemplate.c.id == flows.c.template_flow_id)
        .where(ftemplate.c.workspace_id != flows.c.workspace_id)
    ).all():
        text = definition if isinstance(definition, str) else json.dumps(definition)
        found = {uuid.UUID(v) for v in UUID_RE.findall(text)}
        if found:
            bind.execute(tg_media.update().where(tg_media.c.id.in_(found), tg_media.c.workspace_id == workspace_id).values(locked=True))


def downgrade() -> None:
    for table in ("tg_media", "instagram_media"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("locked")

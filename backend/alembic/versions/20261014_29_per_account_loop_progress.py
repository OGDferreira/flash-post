"""Per-account loop progress, safe publication reconciliation, one active job.

- instagram_loop_account_states keeps each account's position in the loop.
- Publication jobs record container_id / publish_requested_at / published_at.
- Duplicate unfinished jobs for the same (loop, account) are retired and a
  partial unique index prevents them from being created again.
- The daily limit was ignored by the old scheduler; existing loops are set to
  Instagram's 100/day cap so nothing is throttled until the owner chooses.

Revision ID: 20261014_29
Revises: 20261014_28
Create Date: 2026-10-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_29"
down_revision: Union[str, None] = "20261014_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = "status IN ('waiting_for_media', 'queued', 'publishing')"


def upgrade() -> None:
    op.add_column("instagram_publication_jobs", sa.Column("container_id", sa.String(128), nullable=True))
    op.add_column(
        "instagram_publication_jobs",
        sa.Column("publish_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instagram_publication_jobs",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instagram_publication_jobs",
        sa.Column("reconcile_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "instagram_loop_account_states",
        sa.Column(
            "loop_id", sa.Uuid(), sa.ForeignKey("instagram_loops.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("next_position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_media_id", sa.Uuid(), sa.ForeignKey("instagram_media.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("cycles_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_reason", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_instagram_loop_account_states_account", "instagram_loop_account_states", ["account_id"]
    )

    bind = op.get_bind()
    jobs = sa.table(
        "instagram_publication_jobs",
        sa.column("id", sa.Uuid()),
        sa.column("loop_id", sa.Uuid()),
        sa.column("account_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("scheduled_for", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("last_error", sa.String()),
    )
    # Best available publication time for history.
    bind.execute(
        jobs.update().where(jobs.c.status == "published").values(published_at=jobs.c.updated_at)
    )
    # Keep one unfinished job per (loop, account): a job already publishing
    # wins, otherwise the oldest. The rest never started, so retiring them
    # cannot lose a publication.
    rows = bind.execute(
        sa.select(jobs.c.id, jobs.c.loop_id, jobs.c.account_id, jobs.c.status)
        .where(jobs.c.status.in_(("waiting_for_media", "queued", "publishing")))
        .order_by(
            jobs.c.loop_id,
            jobs.c.account_id,
            sa.case((jobs.c.status == "publishing", 0), else_=1),
            jobs.c.scheduled_for,
            jobs.c.created_at,
        )
    ).all()
    seen: set[tuple] = set()
    retired: list = []
    for job_id, loop_id, account_id, _status in rows:
        key = (loop_id, account_id)
        if key in seen:
            retired.append(job_id)
        else:
            seen.add(key)
    for start in range(0, len(retired), 500):
        bind.execute(
            jobs.update()
            .where(jobs.c.id.in_(retired[start : start + 500]))
            .values(
                status="failed",
                last_error="Fila duplicada removida: cada conta mantém apenas um envio pendente por loop.",
            )
        )
    op.create_index(
        "uq_instagram_publication_jobs_active_loop_account",
        "instagram_publication_jobs",
        ["loop_id", "account_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE),
        sqlite_where=sa.text(_ACTIVE),
    )
    op.create_index(
        "ix_instagram_publication_jobs_published_at",
        "instagram_publication_jobs",
        ["account_id", "published_at"],
    )
    loops = sa.table("instagram_loops", sa.column("daily_limit_per_account", sa.Integer()))
    bind.execute(loops.update().values(daily_limit_per_account=100))


def downgrade() -> None:
    op.drop_index("ix_instagram_publication_jobs_published_at", table_name="instagram_publication_jobs")
    op.drop_index(
        "uq_instagram_publication_jobs_active_loop_account", table_name="instagram_publication_jobs"
    )
    op.drop_index("ix_instagram_loop_account_states_account", table_name="instagram_loop_account_states")
    op.drop_table("instagram_loop_account_states")
    op.drop_column("instagram_publication_jobs", "reconcile_attempts")
    op.drop_column("instagram_publication_jobs", "published_at")
    op.drop_column("instagram_publication_jobs", "publish_requested_at")
    op.drop_column("instagram_publication_jobs", "container_id")

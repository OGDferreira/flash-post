"""Store encrypted per-workspace SnakePay credentials and per-order snapshots."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261021_55"
down_revision: Union[str, None] = "20261020_54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.add_column(sa.Column("snakepay_api_key_encrypted", sa.String(1024), nullable=True))
        batch.add_column(sa.Column("snakepay_webhook_secret_encrypted", sa.String(1024), nullable=True))
    with op.batch_alter_table("tg_orders") as batch:
        batch.add_column(sa.Column("snakepay_api_key_encrypted", sa.String(1024), nullable=True))
        batch.add_column(sa.Column("snakepay_webhook_secret_encrypted", sa.String(1024), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tg_orders") as batch:
        batch.drop_column("snakepay_webhook_secret_encrypted")
        batch.drop_column("snakepay_api_key_encrypted")
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("snakepay_webhook_secret_encrypted")
        batch.drop_column("snakepay_api_key_encrypted")

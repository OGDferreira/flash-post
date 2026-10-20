"""Persist each user's preferred home panel (NULL prompts existing users)."""
from alembic import op
import sqlalchemy as sa

revision = "20261020_54"
down_revision = "20261020_53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("home_panel", sa.String(16), nullable=True))
        batch.create_check_constraint("ck_users_home_panel", "home_panel IS NULL OR home_panel IN ('flashpost', 'flashbot')")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_home_panel", type_="check")
        batch.drop_column("home_panel")

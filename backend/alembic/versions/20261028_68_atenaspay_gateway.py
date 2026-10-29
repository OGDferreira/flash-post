"""Allow Atenas Pay in gateway selection and shared-funnel rules."""

from typing import Sequence, Union

from alembic import op


revision: str = "20261028_68"
down_revision: Union[str, None] = "20261025_67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table, constraint in (
        ("tg_flow_shares", "ck_tg_flow_shares_gateway"),
        ("tg_gateway_settings", "ck_tg_gateway_settings_gateway"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="check")
            batch.create_check_constraint(
                constraint,
                "gateway IN ('smokepay', 'snakepay', 'atenaspay')",
            )


def downgrade() -> None:
    for table, constraint in (
        ("tg_gateway_settings", "ck_tg_gateway_settings_gateway"),
        ("tg_flow_shares", "ck_tg_flow_shares_gateway"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="check")
            batch.create_check_constraint(constraint, "gateway IN ('smokepay', 'snakepay')")

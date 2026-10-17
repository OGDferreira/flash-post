"""Close Supabase's public REST API over our tables.

The app talks to Postgres directly as the table owner (``postgres``), which RLS does
not restrict. Supabase's ``anon``/``authenticated`` roles had full privileges on every
table and RLS was off, so anyone with the project's public key could read or change
data through the REST API. Enable RLS (no policies = no access for those roles), revoke
their privileges, and stop granting them on tables created later.

Postgres only; a no-op elsewhere (tests run on SQLite).

Revision ID: 20261017_44
Revises: 20261017_43
Create Date: 2026-10-17 20:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20261017_44"
down_revision: Union[str, None] = "20261017_43"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LOCK = """
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM authenticated;
  END IF;
END $$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_LOCK)


def downgrade() -> None:
    # Re-opening the public API is never done automatically.
    pass

#!/bin/sh
# During a deploy the old instance still holds database connections and Supabase's session
# pooler caps clients at 15: a migration that cannot connect retries for a few minutes
# instead of failing the whole deploy.
attempt=1
until alembic upgrade head; do
  if [ "$attempt" -ge 20 ]; then
    echo "Migrations failed after $attempt attempts." >&2
    exit 1
  fi
  echo "Migration attempt $attempt failed; retrying in 10s." >&2
  attempt=$((attempt + 1))
  sleep 10
done
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"

#!/bin/sh
# During a deploy the old instance still holds database connections and Supabase's session
# pooler caps clients at 15. Migrations retry for a minute; if the pooler is still full the
# server starts anyway (Render needs the port open within a few minutes, and the old instance
# only lets its connections go once the new one is live). A deploy that really changes the
# schema then gets its migration applied on the next start, so keep schema changes additive.
attempt=1
until alembic upgrade head; do
  if [ "$attempt" -ge 6 ]; then
    echo "Migrations could not run (database busy); starting the server anyway." >&2
    break
  fi
  echo "Migration attempt $attempt failed; retrying in 10s." >&2
  attempt=$((attempt + 1))
  sleep 10
done
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"

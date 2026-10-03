# FlashPost

FlashPost is a new application built independently from the legacy Auto-Insta
codebase. The legacy repository is a functional reference for business rules
and integrations, not a source of frontend or backend architecture.

## Deployment

The initial release uses one Docker Web Service. Vite builds React and FastAPI
serves the frontend and API from the same origin. This keeps the first
production setup simple while preserving separate `frontend/` and `backend/`
applications for future service separation.

The Render service uses the repository root, `./Dockerfile`, the `main` branch,
automatic deploys, and `/health` for its liveness check. Docker builds both
applications and starts Uvicorn on the `PORT` provided by Render.

### Production environment

Configure these environment variables directly in Render:

- `ENVIRONMENT=production`
- `PUBLIC_BASE_URL=https://flashpost.onrender.com`
- `ALLOWED_HOSTS=flashpost.onrender.com`
- `DATABASE_URL`: the FlashPost Supabase PostgreSQL Session Pooler URL
- `SESSION_SECRET`: session signing secret
- `MASTER_ENCRYPTION_KEY`: Fernet-compatible encryption key
- `SUPABASE_URL`: the Supabase Project URL, such as
  `https://your-project.supabase.co` (not a publishable key)
- `SUPABASE_SERVICE_ROLE_KEY`: the server-only service-role secret, stored as a
  Render secret and never sent to the browser
- `INSTAGRAM_PUBLISHING_ENABLED=false`: leave disabled until the storage setup,
  migration, Meta permissions, and a test account have all been verified

Secret values must remain in Render and must never be copied into this
repository. PostgreSQL URLs are normalized for `asyncpg`; PostgreSQL
connections require TLS. The application does not print credentials or
connection strings. Production startup requires `SESSION_SECRET`, and Docker
startup requires `DATABASE_URL`. `MASTER_ENCRYPTION_KEY` is checked when
encryption is used. Instagram App IDs and App Secrets are configured by each
workspace OWNER in the Contas page and encrypted before database storage.
The Storage integration uses the private `instagram-media` bucket through the
backend only; do not add the service-role key or a Supabase publishable key to
frontend configuration. If a service-role key is ever shown in a screenshot,
rotate it in Supabase and replace the Render secret before enabling uploads.

Set up these values in the Render web service under **Environment**:

1. Set `SUPABASE_URL` to the Project URL shown under Supabase **Project
   Settings > API**, for example `https://your-project.supabase.co`. This value
   is a URL, not an API key.
2. In Supabase **Project Settings > API Keys**, rotate the exposed legacy
   `service_role` key (or create a replacement secret key if using the new key
   format). Update `SUPABASE_SERVICE_ROLE_KEY` in Render with the new secret.
   If another service uses the old key, update it there too. Never paste the
   key into this repository, the browser, or chat.
3. Keep `INSTAGRAM_PUBLISHING_ENABLED=false` until the deployment, private
   bucket upload, and a test-account reconnection have been verified.

To run the periodic token-refresh and publication worker, create a separate
Render **Cron Job** using this repository, branch `main`, and the same
`Dockerfile` as the web service. Set its command to
`python -m app.workers.loop_scheduler` and its schedule to `* * * * *` (once
per minute). Add the worker's required environment variables in the Cron Job:
`DATABASE_URL`, `MASTER_ENCRYPTION_KEY`, `SUPABASE_URL`, and
`SUPABASE_SERVICE_ROLE_KEY`. Keep the publish flag disabled while testing;
turn it on only when intentional Instagram publishing is ready. The Cron Job
does not run the website: it is a separate scheduled worker, and it does not
need `SESSION_SECRET` or `PUBLIC_BASE_URL`.

### Account creation

The public `/register` page creates a customer `OWNER`, a workspace, and its
active owner membership, then signs the user in. Nicknames are public display
names: Unicode text is preserved, whitespace is collapsed, and a separate
case-folded key enforces platform-wide uniqueness.

Only a platform administrator is created through the administrative CLI:

```powershell
python -m app.cli create-super-admin
```

The CLI prompts for a name, email, nickname, and password; passwords are typed
without echo and are never printed. It requests confirmation before creating
an additional `SUPER_ADMIN`. This administrative operation is not a public
HTTP endpoint.

## Database and migrations

The dedicated FlashPost Supabase PostgreSQL project is the production source
of truth. SQLAlchemy uses async sessions and a small connection pool for the
Supabase Session Pooler. The initial models use UUID keys, timezone-aware
timestamps, foreign keys, role/status constraints, and case-insensitive unique
indexes for email and workspace slugs.

Alembic exclusively owns production schema changes; the application never
calls `create_all()`. Docker runs `alembic upgrade head` before Uvicorn starts.
A PostgreSQL advisory lock serializes concurrent startup migrations. This
single-service strategy can be moved to a dedicated release/pre-deploy command
before adding workers; background workers must never run migrations.
The nickname migrations backfill existing users before enforcing the
non-null, case-insensitive unique index on `nickname_normalized`.
Migration `20261003_04` adds Instagram accounts scoped to workspaces. OAuth
access tokens are encrypted with `MASTER_ENCRYPTION_KEY`; API responses never
include them. Migration `20261003_05` adds encrypted Meta app credentials and
`20261003_06` allows multiple named apps per workspace while preserving
existing app/account associations. The shared `MASTER_ENCRYPTION_KEY` remains
a server-side infrastructure secret; each customer registers their own Meta
apps in the authenticated FlashPost workspace.
Migration `20261003_07` retains disconnected account rows without retaining
their tokens and adds loop configurations, account selections, and a durable
publication-intent queue. Existing accounts are marked connected during the
migration; expiry is evaluated from `token_expires_at`.
Migration `20261003_08` adds workspace-scoped media metadata, private Storage
object paths, loop-to-media selections, and publication result fields. Render
applies this migration at startup through the existing Alembic flow.

## Instagram accounts

The **Contas** workspace page supports connecting multiple Instagram
professional (Business and Creator) accounts using Instagram Login. Workspace
members can view account names and token expiration dates; only the workspace
OWNER can connect or disconnect accounts. Expired and disconnected accounts
remain visible in the hub; disconnecting erases the saved token, records the
account as disconnected, and attempts to revoke the Meta authorization. If
Meta does not confirm revocation, the interface tells the OWNER how to finish
revoking it in Instagram settings.

Create a Business-type Meta app, add the Instagram product, configure
Instagram Business Login, and register this exact OAuth redirect URI in Meta:

```text
https://flashpost.onrender.com/api/instagram/callback
```

For local testing, use the local backend URL configured through
`PUBLIC_BASE_URL`, for example `http://localhost:8000/api/instagram/callback`.
The URI in Meta must exactly match `PUBLIC_BASE_URL` plus
`/api/instagram/callback`. In FlashPost, each workspace OWNER registers one or more Meta App IDs and
App Secrets in the **Aplicativos Meta** area on the Contas page, gives each
app an internal name, and selects which one to use for new connections. The
FlashPost server validates the credentials with Meta and retrieves the app's
available public details. The App Secret is encrypted server-side and is
never returned to the browser after saving. Existing Instagram accounts remain
associated with the app that authorized them.
Never put a customer's App Secret in frontend environment configuration,
Render environment variables, Git, or chat.

The Instagram Login flow requests both `instagram_business_basic` and
`instagram_business_content_publish`. Existing accounts must reconnect and
grant the new permission before publishing. In development, invited app
testers must accept the invitation and grant consent. Meta may also require
Advanced Access and App Review outside the tester setup. Instagram media
publishing uses a private Storage object and a signed URL that expires after
four hours; the backend creates the media container, waits for video
processing when needed, and publishes the container. Uploads currently accept
JPEG images and MP4 videos up to 50 MiB. Meta can still reject media that does
not meet its current dimensions, duration, encoding, or account requirements.
Meta documents long-lived Instagram access tokens as expiring after 60 days.
The worker refreshes valid tokens when they are within ten days of expiration,
extending them for another 60 days without another Instagram authorization.
Meta requires a long-lived token to be at least 24 hours old and still valid
for refresh; an expired or revoked token must be reconnected. The periodic
worker must remain scheduled for token refresh to happen.

The **Loops** page stores per-workspace publishing intervals, account
selections, daily limits, media-reuse preference, post type, and selected
media. The page uploads media to the private `instagram-media` bucket through
the authenticated backend. The periodic worker can be run with
`python -m app.workers.loop_scheduler`, for example once per minute from a
Render Cron Job or another managed scheduler. With
`INSTAGRAM_PUBLISHING_ENABLED=false`, it only creates queued intents and does
not send posts. Enable publishing only after rotating any exposed key,
verifying the Project URL, confirming migration `20261003_08` was applied,
uploading test media, and reconnecting a test account with the publishing
permission. Once enabled, only queued items with compatible media are sent.
Failed jobs are not automatically retried because a network failure can happen
after Instagram has accepted a post. Verify Instagram before uploading the
same media again; media from an ambiguous, started attempt is not reused
automatically.

Meta webhooks are not configured in this phase. A webhook is a separate HTTPS
receiver for asynchronous Instagram events such as comments, mentions, story
expiration, and incoming messages; it is not the OAuth redirect callback.
FlashPost does not yet implement Meta's webhook verification or event receiver,
so do not reuse another product's callback URL or verification token here.

Public information pages for Meta app settings:

- Privacy policy: `https://flashpost.onrender.com/privacidade`
- Terms of service: `https://flashpost.onrender.com/termosdeuso`
- Data deletion instructions: `https://flashpost.onrender.com/deletar`

These pages are served as HTML directly by FastAPI, so Meta can read their
contents without running the React application. The data deletion page
currently gives instructions to contact support; account deletion is not
automated in the product yet. Review the legal text and published support
contact for your business before submitting the Meta app for review.

Backend tests apply those same Alembic migrations to an isolated temporary
SQLite database. Tests never connect to or modify Supabase.

## Authentication and API

- Sessions use a signed, HttpOnly, SameSite=Lax cookie; it is Secure in
  production and expires after eight hours. Cookie contents contain identity
  references only.
- State-changing requests require a session-bound `X-CSRF-Token`. Obtain one
  from `GET /api/auth/csrf`; login and logout rotate the token.
- Passwords use Argon2id. Login failures do not disclose whether an account
  exists. Registration and nickname availability have process-local rate
  limits; replace these with a shared store before horizontal scaling.
- Workspace access is checked against active membership for each request. An
  optional `X-Workspace-ID` is accepted only after that check.
- Only a global `SUPER_ADMIN` can access `/api/admin/*`. Frontend guards
  complement, but never replace, backend authorization.

Initial endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Process liveness, independent of the database |
| `GET` | `/readiness` | Database readiness check |
| `GET` | `/api/auth/csrf` | Obtain a CSRF token for the current session |
| `GET` | `/api/auth/nickname-availability` | Check whether a nickname can be registered |
| `POST` | `/api/auth/register` | Create an OWNER, workspace, membership, and signed-in session |
| `POST` | `/api/auth/login` | Sign in |
| `POST` | `/api/auth/logout` | Sign out and rotate the CSRF token |
| `GET` | `/api/auth/me` | Current authenticated user |
| `GET`, `PATCH` | `/api/profile` | Read/update profile name, nickname, and avatar URL |
| `GET` | `/api/workspace` | Current active workspace membership |
| `GET` | `/api/instagram/accounts` | List Instagram accounts for the active workspace |
| `GET`, `POST` | `/api/instagram/apps` | List registered Meta apps or add a validated app (OWNER only) |
| `PUT` | `/api/instagram/apps/{app_id}/select` | Select the Meta app for new Instagram connections (OWNER only) |
| `DELETE` | `/api/instagram/apps/{app_id}` | Remove an app that has no linked Instagram accounts (OWNER only) |
| `POST` | `/api/instagram/connect` | Start Instagram Login (OWNER only; requires CSRF) |
| `GET` | `/api/instagram/callback` | Complete Instagram Login and store an encrypted token |
| `DELETE` | `/api/instagram/accounts/{id}` | Disconnect an account (OWNER only; requires CSRF) |
| `GET` | `/api/loops` | List workspace loops and active, eligible Instagram accounts |
| `POST` | `/api/loops` | Create a loop with interval, daily cap, media mode, and accounts (OWNER only) |
| `PUT` | `/api/loops/{id}` | Update a loop (OWNER only) |
| `PATCH` | `/api/loops/{id}/status` | Pause or resume a loop (OWNER only) |
| `DELETE` | `/api/loops/{id}` | Delete a loop and its queued intents (OWNER only) |
| `GET` | `/api/admin/summary` | Real user/workspace totals |
| `GET` | `/api/admin/users` | Searchable, paginated user list |
| `GET` | `/api/admin/workspaces` | Searchable, paginated workspace list |
| `GET` | `/api/admin/system/settings` | Non-secret system settings |

## Local development

Requirements: Python 3.12+, Node.js 22+, and npm.

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload
```

Database-backed local routes need a development `DATABASE_URL` and
`SESSION_SECRET` provided through environment variables or an untracked local
`.env` file. Never use the production Supabase database for tests.

Frontend, in a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

The Vite development server proxies `/health` and `/api` to FastAPI at
`http://127.0.0.1:8000`.

## Validation

Run from the repository root:

```powershell
Push-Location frontend
npm ci
npm run build
npx tsc --noEmit
Pop-Location
Push-Location backend
python -m pytest
python -m compileall -q app alembic tests
Pop-Location
```

Build the production container from the repository root:

```powershell
docker build -t flashpost .
```

## Project structure

```text
backend/app/       FastAPI API, authentication/RBAC, persistence, domain packages
backend/alembic/   Versioned PostgreSQL schema migrations
backend/tests/     Isolated migration-backed API and security tests
frontend/src/      React application, layouts, pages, auth, and API client
```

Instagram account connection is implemented behind Meta app configuration.
Publishing, Loops, analytics, Shark, finance, ranking, Redis, workers, and
other product modules remain out of scope until their requirements are
defined.

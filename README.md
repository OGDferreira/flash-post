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
workspace OWNER in Configurações and encrypted before database storage.
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

The web application starts its own APScheduler background task on startup,
following the working pattern used by Auto-Insta. It checks the loop queue and
refreshes Instagram tokens once per minute, using the same database and
environment variables as the web service; no separate Render Cron Job or
duplicate worker environment configuration is required. A PostgreSQL advisory
lock prevents two FlashPost instances from processing the same tick at once.
On Render plans that suspend an idle web service, the in-process scheduler is
also suspended until the web service wakes up; dependable unattended execution
therefore requires the web service to remain running.

### Account creation

The public `/register` page creates a customer `OWNER`, a workspace, and its
owner membership. New users remain pending and cannot sign in until a platform
administrator approves them in the Admin area. The approval migration keeps
existing users approved. Nicknames are public display names: Unicode text is
preserved, whitespace is collapsed, and a separate case-folded key enforces
platform-wide uniqueness.

Only a platform administrator is created through the administrative CLI:

```powershell
python -m app.cli create-super-admin
```

The CLI prompts for a name, email, nickname, and password; passwords are typed
without echo and are never printed. It requests confirmation before creating
an additional `SUPER_ADMIN`. This administrative operation is not a public
HTTP endpoint.
To grant `SUPER_ADMIN` to an existing user without changing their password,
workspace, or related records, use
`python -m app.cli promote-super-admin <existing-email>`.
If the Render plan does not include a service Shell, the same single-column
change can be made in the Supabase Dashboard's **SQL Editor**. First verify the
existing account:

```sql
SELECT id, email, platform_role, is_approved
FROM public.users
WHERE lower(email) = lower('existing-email');
```

After confirming this returns exactly the intended existing account, promote
it and verify the result:

```sql
UPDATE public.users
SET platform_role = 'SUPER_ADMIN'
WHERE lower(email) = lower('existing-email')
RETURNING id, email, platform_role;
```

This updates only the role; do not replace or recreate the user. Render
environment variables configure the application but do not change database
account roles. A `SUPER_ADMIN` who also has an active OWNER membership sees
the regular workspace dashboard, accounts, loops, metrics, and a separate
administration section in the same navigation. Only accounts with the
`SUPER_ADMIN` platform role can see or open that section; approving a new
customer OWNER does not grant platform-admin access.

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
Migration `20261003_09` stores the Instagram profile picture URL and the
followers/media-count snapshots returned during OAuth, for account cards and
account-level summaries.
Migration `20261003_10` records the user and timestamp for each account's first
connection to a workspace, adds collaborator connection rates and goals, and
creates the monthly payment ledger. Existing accounts are not credited
retroactively; reconnecting an existing account does not count as a new
connection.
Migration `20261003_11` adds account health errors, workspace-specific
Sharkbot webhook URLs, and timestamped, deduplicated Sharkbot events.
Migration `20261003_12` adds colored profile folders for organizing Instagram
accounts. Migration `20261004_13` snapshots the collaborator connection rate
for each Instagram account. Migration `20261005_14` adds manual user approval;
existing accounts remain approved by default, while new public registrations
require approval before login.
The Loops page displays each loop's connected accounts and current media pool;
owners can inspect detailed publication errors in its separate Errors tab.
Accounts marked with errors are detached from loops and queued jobs, and can
be removed from the Hub. Removing an errored account permanently deletes its
associated publication-job history, so review its entries in the Errors tab
first.
The owner-only **Feed** page lists workspace profiles, loads up to 25 recent
Instagram media items per selected profile, and shows profile snapshots and
media engagement returned by Instagram. The **Colaboradores** navigation and
management page are also owner-only.
The workspace **E-mails** page manages supplier, login, password, responsible
person, status, notes, 2FA code, and private error-image attachments. Passwords
and 2FA values are encrypted at rest; authenticated workspace members can view
and copy them, while only the OWNER can create, edit, or delete rows.
COLLABORATORs can advance statuses, update notes, and upload JPEG, PNG, or WebP
error images. The page uses the existing private Supabase Storage bucket and
requires the standard `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` settings
for image uploads. Migration `20261006_17` creates the workspace-scoped
`email_accounts` table.
Each loop keeps its own media selection, with signed previews and
per-loop removal in the Loops page. The first eligible publication is queued
immediately when a loop is created or activated; later publications follow its
configured interval. The configurable per-account daily limit is removed, but
the scheduler retains Instagram's 100-publications-per-24-hours safety guard.

## Instagram accounts

The **Contas** workspace page supports connecting multiple Instagram
professional (Business and Creator) accounts using Instagram Login. Workspace
members can view account names and token expiration dates. Workspace
COLLABORATORs can start an Instagram connection; only the workspace OWNER can
disconnect accounts or manage Meta app credentials. Expired and disconnected accounts
remain visible in the hub; disconnecting erases the saved token, records the
account as disconnected, and attempts to revoke the Meta authorization. If
Meta does not confirm revocation, the interface tells the OWNER how to finish
revoking it in Instagram settings.
The Hub displays each account's profile thumbnail. The workspace **Configurações**
page is where an OWNER registers, edits, selects, and removes Meta apps. The
dashboard refreshes follower and media counts from the connected Instagram
profile and uses the last saved OAuth snapshot if Meta cannot refresh them.
Analytics also requests the account-level `views` metric (falling back to
`content_views` when Meta does not support `views` for that account) when the
app has the `instagram_business_manage_insights` permission; the interface
identifies this permission when Meta denies access.

Create a **Business-type** Meta app, configure **Instagram API with Instagram
Login**, and register this exact OAuth redirect URI in the app's **Business
login settings**:

```text
https://flashpost.onrender.com/api/instagram/callback
```

For local testing, use the local backend URL configured through
`PUBLIC_BASE_URL`, for example `http://localhost:8000/api/instagram/callback`.
The URI in Meta must exactly match `PUBLIC_BASE_URL` plus
`/api/instagram/callback`. In FlashPost, each workspace OWNER registers one or
more credentials in **Aplicativos Meta** in Configurações, gives each
configuration an internal name, and selects the app to use for new connections.
Use the **Instagram App ID** and **Instagram App Secret** displayed at **App
Dashboard > Instagram > API setup with Instagram login > Set up Instagram
business login > Business login settings**. Do not use the general App ID or
App Secret from **Basic Settings**. FlashPost sends this Instagram App ID as
OAuth `client_id` and uses the matching Instagram App Secret for the token
exchange. The secret is encrypted server-side and never returned to the
browser. Existing connected accounts and their tokens remain associated with
the app that authorized them; add the correct Instagram Login credentials as
a separate app instead of replacing credentials for an app that already has
connected accounts. Never put an App Secret in frontend environment
configuration, Render environment variables, Git, or chat.

The Instagram Login flow requests `instagram_business_basic`,
`instagram_business_content_publish`, and `instagram_business_manage_insights`.
Existing accounts must reconnect to grant newly requested permissions; app
approval alone does not add a permission to tokens issued before consent. The
notification bell reports a missing Insights permission only when Meta's API
error explicitly identifies that permission; other Insights failures are
reported without guessing their cause. In development, invited app
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
the authenticated backend; one selection can upload several compatible
files, and a loop accepts a pool with no fixed media-count limit. Each scheduled
execution publishes one item from that pool. Only an OWNER can create or
configure a loop, select its media, pause it, or delete it. A COLLABORATOR can
associate connected accounts with an existing loop, but cannot change its
publishing settings or media pool. An APScheduler task starts with the FastAPI
web process and checks the queue and token refreshes once per minute. With
`INSTAGRAM_PUBLISHING_ENABLED=false`, it only creates queued intents and does
not send posts. Enable publishing only after rotating any exposed key,
verifying the Project URL, confirming migration `20261003_12` was applied,
uploading test media, and reconnecting a test account with the publishing
permission. Once enabled, only queued items with compatible media are sent.
Failed jobs are not automatically retried because a network failure can happen
after Instagram has accepted a post. Verify Instagram before uploading the
same media again; media from an ambiguous, started attempt is not reused
automatically. A suspended Render web service cannot run its in-process
scheduler until the service wakes.
An active loop queues its first selected media immediately for each eligible
account instead of waiting for the first random interval. Accounts added later
join the current playlist item immediately (or the next item after the last
completed item), and each account advances independently through the same
ordered media pool.

## Collaborators and installable app

Workspace OWNERs manage collaborator logins, connection rates, daily and monthly
connection goals, bonuses, team production, and manual monthly payments. A
COLLABORATOR can open a personal production dashboard, edit their profile, start
Instagram account connections, and associate connected accounts with existing
loops. Financial analytics, collaborator management, Meta app settings, loop
configuration, and account disconnection remain OWNER-only and are checked by
the API as well as the frontend.

A connection is credited only once, when an Instagram account is first added
to the workspace after migration `20261003_10`. Reconnecting an account does
not create another credit. The monthly bonus is included when the collaborator
reaches the configured monthly goal; an OWNER records payment manually, and
the payment reduces the outstanding amount for that month.

The frontend includes a web app manifest and service worker for installation
from supported browsers. The worker can serve the app shell while offline and
caches built static assets; `/api/` requests always go to the server and are
never cached.

An Instagram account moves out of the active status when its token expires or a
publishing failure confirms an authorization/checkpoint problem. Other
publication failures are counted consecutively; after more than five attempted
posts fail without a successful post in between, the account is marked with an
error. A successful OAuth reconnection restores its active status. The
workspace OWNER can copy the workspace's individual Sharkbot webhook URL from
Configurações and register it in Sharkbot; rotating the URL invalidates the old
one. The receiver accepts the `payment_created`, `payment_approved`, and
`user_joined` events used by Auto-Insta-1, including its nested `data` payload,
and ignores duplicate event deliveries.

The Instagram webhook callback is
`https://flashpost.onrender.com/api/instagram/webhook`. Configure
`INSTAGRAM_WEBHOOK_VERIFY_TOKEN` as a secret environment variable on the Render
Web Service, then enter that same value in Meta's Verify Token field. The POST
receiver validates `X-Hub-Signature-256` against the stored App Secrets for
configured Meta apps and acknowledges valid Instagram event payloads. It
logs event counts, not message or comment contents. This endpoint is separate
from the OAuth redirect callback and the workspace-specific Sharkbot webhook.
Receiving webhook events does not provide Instagram Insights; those metrics
are queried from Meta's Insights API using each account's authorization and
the `instagram_business_manage_insights` permission.

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
| `POST` | `/api/auth/register` | Create a pending OWNER, workspace, and membership |
| `POST` | `/api/auth/login` | Sign in (approved users only) |
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
| `POST` | `/api/admin/users/{user_id}/approve` | Approve a pending user |
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

Instagram account connection, automated Loops and publishing, Dashboard,
Analytics, and platform administration are implemented behind the configured
workspace and Meta permissions. Sharkbot integrations are available per
workspace. Finance, ranking, Redis, and distributed workers remain outside
this release.

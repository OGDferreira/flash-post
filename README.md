# FlashPost

FlashPost is a new application built independently from the legacy Auto-Insta
codebase. The legacy repository is a functional reference for business rules
and integrations, not a source of frontend or backend architecture.

## First deployment

The first release uses one Docker Web Service: Vite builds the React application
and FastAPI serves its static files together with the API. This is the smallest
reliable deployment path for validating GitHub, Render, Docker, FastAPI, and the
frontend end to end. The frontend and backend remain in separate directories
and can be deployed as separate services later without changing the product
architecture.

### Render settings

- Runtime: Docker
- Root directory: repository root
- Dockerfile path: `./Dockerfile`
- Build command: leave blank (the Dockerfile builds both applications)
- Start command: leave blank (the Docker image starts Uvicorn)
- Health check path: `/health`
- Branch: `main`
- Auto-deploy: enabled
- Port: use the `PORT` value provided by Render; the container has a local
  fallback of `10000` for development.

No database or integration credentials are required for this initial health
check deployment.

### Environment variables to set now

These are public application settings, not secrets:

| Name | Value |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `PUBLIC_BASE_URL` | `https://flashpost.onrender.com` |
| `ALLOWED_HOSTS` | `flashpost.onrender.com` |

The application also has safe defaults for local development. Setting these
values explicitly in Render makes the intended deployment configuration clear.

### Add later, with their respective feature

Do not add placeholders or invent values for these settings. They are not read
or required by the initial application:

- PostgreSQL: `DATABASE_URL`
- Session signing: `SESSION_SECRET` (**GERAR ESTA CHAVE**)
- Application encryption: `MASTER_ENCRYPTION_KEY` (**GERAR ESTA CHAVE**)
- Supabase Storage credentials and bucket
- Meta OAuth credentials and callback settings
- Google OAuth credentials
- Shark webhook configuration
- VAPID push-notification keys
- Redis connection URL

Generate a session secret when authentication is implemented:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Generate a Fernet-compatible encryption key when the encryption module is
implemented:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep generated values only in Render's environment settings or a local,
untracked `.env` file. Never put them in frontend code or commit them.

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

Frontend, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

The Vite development server proxies `/health` to FastAPI at `http://127.0.0.1:8000`.
The initial health endpoint is also available at `http://127.0.0.1:8000/health`.

## Validation

```powershell
cd frontend
npm run build
npx tsc --noEmit
cd ..\backend
python -m pytest
python -m compileall -q app
```

Build the production container from the repository root:

```powershell
docker build -t flashpost .
```

## Project structure

```text
backend/   FastAPI application, domain modules, Alembic, and tests
frontend/  React, TypeScript, Vite, and feature-oriented UI
```

PostgreSQL will be the production database when the database phase is started.
SQLAlchemy Async and Alembic are included in the backend foundation, but no
connection or schema changes run at startup. The app does not use SQLite or
`create_all()` for production schema management.

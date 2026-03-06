# StainlessMax System

## Quickstart (Production Run)

1. Install runtime dependencies:

```bash
pip install -r requirements.txt
```

2. Configure environment variables as needed (minimum example):

```bash
set FLASK_SECRET_KEY=your-strong-secret
set DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

Linux/macOS example:

```bash
export FLASK_SECRET_KEY=your-strong-secret
export DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
python app.py
```

3. Run the application from `StainlessMax/System`:

```bash
python app.py
```

## Development & Test Install

Install dev/test dependencies (includes runtime + test tools):

```bash
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes test tooling such as:
- `pytest`
- `hypothesis`
- `pytest-cov`

## PostgreSQL Test Instructions

Some DB-backed tests require PostgreSQL and read `DATABASE_URL`.

Expected format:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

Example (Windows cmd):

```cmd
set DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/stainlessmax_test
pytest -q
```

Notes:
- If `DATABASE_URL` is missing, tests that require it are skipped.
- If `DATABASE_URL` is present but not PostgreSQL (`postgresql...`), those tests are skipped.

## Auth Configuration (Multi-tenant Hardening)

For production mode, configure either:
- `JWT_SECRET`, or
- `FLASK_SECRET_KEY`

Production mode markers:
- `FLASK_ENV=production`, or
- `APP_ENV=production`, or
- `ENV=production`, or
- `SAAS_MODE=1` (also accepts `true/yes/on`)

If any production marker is set and neither `JWT_SECRET` nor `FLASK_SECRET_KEY` is provided, auth endpoints are disabled (503).

Behavior in production mode when no auth secret is configured:
- `/api/auth/*` endpoints return `503` with the existing JSON error shape.
- JWT decode path is blocked from using insecure fallback secret.

In local/dev (no production marker), a fallback secret is kept for backward-compatible startup behavior.

This keeps response schemas unchanged while preventing insecure auth secret fallback in production.

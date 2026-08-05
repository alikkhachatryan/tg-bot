# Telegram Job Match Bot

Production-oriented MVP of a Telegram-first personal job search assistant. A user consents
to personal-data processing, uploads a PDF or DOCX resume, confirms an AI-created profile,
answers one onboarding question at a time, and receives explainable vacancy matches.

The first release is a closed beta. There is no website, Mini App, payment flow,
automatic job application, userbot, restricted-channel access, or prohibited scraping.

## Current status

Stage 1 establishes the deployable foundation: FastAPI, aiogram, async SQLAlchemy,
PostgreSQL, Redis, Alembic, arq, structured logging, health endpoints, Docker Compose,
CI, and quality tooling. Product flows are implemented incrementally in later stages.

See [architecture.md](docs/architecture.md) for decisions, the MVP data model, project
layout, and implementation roadmap.

## Requirements

- Python 3.12+
- Docker Engine with Docker Compose v2
- An OpenAI API account for real AI calls; ChatGPT Plus does not include API usage
- A Telegram bot token for Telegram integration

## Local Python setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
copy .env.example .env     # Linux/macOS: cp .env.example .env
uvicorn app.main:app --reload
```

The default `AI_PROVIDER=fake` makes local development and ordinary tests free of real
AI requests. Do not put real keys in `.env.example` or source control.

## Docker development

```bash
docker compose up --build postgres redis app worker scheduler
docker compose --profile proxy up nginx
docker compose --profile polling up bot-polling
docker compose --profile storage up minio
```

The production path uses Telegram webhook delivery through the FastAPI app. The polling
service is only for local development and must not run alongside the webhook consumer.

## Database and migrations

```bash
alembic upgrade head
alembic check
```

New domain tables are introduced with their owning implementation stage. The initial
migration verifies the migration pipeline without prematurely creating unused tables.

## Quality checks

```bash
ruff check .
ruff format --check .
mypy app
pytest --cov=app --cov-report=term-missing
alembic check
docker compose config
```

## Environment and deployment notes

- Put the application, PostgreSQL, Redis, and object storage in the same region; an EU
  region is the current recommendation until a hosting provider is chosen.
- Use S3-compatible private storage in production and local storage only in development.
- Terminate HTTPS at the reverse proxy and validate `TELEGRAM_WEBHOOK_SECRET`.
- Set `BETA_MODE=true` and allow Telegram IDs through `BETA_TELEGRAM_IDS` for the beta.
- Use `AI_PROVIDER=openai`, a separately billed API key, and a project spending limit
  only when real resume parsing is enabled.
- Replace every example secret before production; production configuration validation
  intentionally rejects unsafe defaults.

## Operational endpoints

- `GET /health` — process liveness; does not query dependencies.
- `GET /ready` — PostgreSQL and Redis readiness.
- `GET /metrics` — Prometheus metrics when enabled.

Backup, restore, privacy deletion, webhook setup, source configuration, demo seed,
admin operation, and full production checklist documentation will be completed with the
stages that implement those capabilities.


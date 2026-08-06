# Telegram Job Match Bot

Production-oriented MVP of a Telegram-first personal job search assistant. A user consents
to personal-data processing, uploads a PDF or DOCX resume, confirms an AI-created profile,
answers one onboarding question at a time, and receives explainable vacancy matches.

The first release is a closed beta. There is no website, Mini App, payment flow,
automatic job application, userbot, restricted-channel access, or prohibited scraping.

## Current status

Stages 1 through 5 establish the deployable foundation, Telegram identity layer, secure
resume ingestion, a reviewable AI-created candidate profile, and restart-safe search
onboarding: FastAPI,
aiogram, async SQLAlchemy, PostgreSQL, Redis, Alembic, arq, structured logging, health
endpoints, Docker Compose, CI, closed-beta access, versioned consent, durable conversation
state, protected webhook delivery, update deduplication, local polling, private PDF/DOCX
storage, background text extraction, DeepSeek/fake AI providers, strict Pydantic output,
Telegram confirmation/editing, and one-question-at-a-time search preferences.

See [architecture.md](docs/architecture.md) for decisions, the MVP data model, project
layout, and implementation roadmap.

## Requirements

- Python 3.12+
- Docker Engine with Docker Compose v2
- A DeepSeek API account for real AI calls; the fake provider needs no external account
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
AI requests. For real parsing set `AI_PROVIDER=deepseek`, put the separately issued key
in `AI_API_KEY`, and keep `AI_MODEL=deepseek-v4-flash`. Do not put real keys in
`.env.example`, chat messages, logs, or source control.

## Docker development

```bash
docker compose up --build postgres redis app worker scheduler
docker compose --profile proxy up nginx
docker compose --profile polling up bot-polling
docker compose --profile storage up minio
```

The production path uses Telegram webhook delivery through the FastAPI app. The polling
service is only for local development and must not run alongside the webhook consumer.

## Telegram development

1. Create a bot with BotFather and put its token in `TELEGRAM_BOT_TOKEN`.
2. Put your numeric Telegram user ID in `BETA_TELEGRAM_IDS` while `BETA_MODE=true`.
3. Apply migrations with `alembic upgrade head`.
4. Start local polling:

```bash
python -m app.bot.polling
```

Production sends updates to `POST /telegram/webhook` and must include the configured
`X-Telegram-Bot-Api-Secret-Token` value. Repeated update IDs are ignored, failed handler
claims are released for retry, and stale processing claims can be recovered. Resume
documents are rejected until the current privacy/AI-processing consent is accepted.

After profile confirmation, onboarding asks one question at a time and persists every
answer. `/onboarding` resumes or restarts the flow. Back and skip controls are durable
across process restarts. The initial market strategy prioritizes Armenia and jobs in
Yerevan, then international remote roles available from Armenia, followed by suitable
regional roles. Relocation is never assumed.

Accepted resumes must have matching PDF or DOCX extension, MIME type, size, and file
signature. The server generates the private storage key; the original name is retained
only as metadata. arq changes the status from `queued` to `processing`, then to
`processed` or `failed`, and sends a user-safe Telegram result. Image-only PDFs are
reported as lacking a text layer; OCR is intentionally not enabled in the MVP.

Local files are written below `LOCAL_STORAGE_PATH`. Production requires
`STORAGE_DRIVER=s3`; configure the private bucket with `S3_ENDPOINT`, `S3_BUCKET`,
`S3_ACCESS_KEY`, and `S3_SECRET_KEY`. Resume objects are never exposed through a public
HTTP route.

## Database and migrations

```bash
alembic upgrade head
alembic check
```

Migration `20260806_0003` creates `resume_documents`, including owner, private object key,
content hash, processing status, extracted text, and a safe error code.

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
- Use `AI_PROVIDER=deepseek`, a separately issued API key, and an account spending limit
  only when real resume parsing is enabled. The integration uses DeepSeek JSON Output
  and still validates the response locally; see the
  [official JSON guide](https://api-docs.deepseek.com/guides/json_mode).
- Changing the external AI processor changes `PRIVACY_POLICY_VERSION`, so existing users
  must explicitly grant the current consent before uploading another resume.
- Replace every example secret before production; production configuration validation
  intentionally rejects unsafe defaults.

## Operational endpoints

- `GET /health` — process liveness; does not query dependencies.
- `GET /ready` — PostgreSQL and Redis readiness.
- `GET /metrics` — Prometheus metrics when enabled.

Backup, restore, privacy deletion, webhook setup, source configuration, demo seed,
admin operation, and full production checklist documentation will be completed with the
stages that implement those capabilities.

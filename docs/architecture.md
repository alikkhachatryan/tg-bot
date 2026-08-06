# MVP architecture

## Scope and decisions

The application is an async-first modular monolith. One codebase exposes the FastAPI
webhook/API process and supplies separate arq worker and scheduler processes. This keeps
domain boundaries clear without the deployment and consistency cost of microservices.

- **Background jobs:** arq. It uses the required Redis infrastructure, is async-native,
  has a small operational footprint, and is sufficient for the MVP's I/O-heavy tasks.
  Idempotency is enforced in domain services and persisted status records, not assumed
  from the queue.
- **AI:** provider protocol with a deterministic fake implementation for tests and the
  OpenAI-compatible DeepSeek Chat Completions API for production. The initial production
  model is `deepseek-v4-flash`; JSON Output is still validated through strict Pydantic
  models before persistence.
- **Storage:** private local files in development and private S3-compatible objects in
  production. Storage keys are generated internally and never derived from filenames.
- **Administration:** SQLAdmin in a later stage, protected by separate credentials and
  audit logging. Full resume access requires an explicit audited action.
- **Access:** closed beta allowlist by default; public access is a configuration change.
- **Embeddings:** deferred until deterministic matching works and representative tests
  prove that semantic similarity adds sufficient value.

## Runtime topology

```text
Telegram -> HTTPS reverse proxy -> FastAPI/aiogram webhook -> PostgreSQL
                                      |              |
                                      |              -> Redis
                                      -> enqueue arq jobs -> worker
                                                             |
                                             external sources / DeepSeek / storage

scheduler -> Redis distributed lock -> periodic arq jobs
```

Long polling is a separate development-only process. Webhook handlers acknowledge
updates quickly and never perform document parsing, AI calls, source synchronization,
or matching inline.

## Minimal MVP data model

The schema is introduced stage by stage rather than created mechanically up front.

| Table | Purpose | Important normalized fields / JSONB |
|---|---|---|
| `users` | Internal identity, lifecycle, beta access | status, locale, timestamps |
| `telegram_accounts` | Telegram identity owned by one user | unique telegram_user_id, username |
| `consents` | Versioned consent and withdrawal evidence | policy_version, granted_at, revoked_at |
| `resume_documents` | Private object metadata, extracted text, and processing status | storage_key, MIME, SHA-256, status, error_code |
| `resume_parse_runs` | AI parsing attempts introduced in stage 4 | status, parser_version, error_code |
| `candidate_profiles` | Confirmed profile and version | core fields normalized; evidence-rich sections in JSONB |
| `candidate_skills` | Skills used by deterministic matching | normalized skill, level, experience, evidence |
| `search_preferences` | Hard filters and notification inputs | roles/countries/timezones arrays; exclusions in JSONB |
| `onboarding_sessions` | Durable one-question-at-a-time progress | current_question, answers JSONB, status |
| `job_sources` | Adapter configuration and permissions | kind, status, config JSONB, retention rules |
| `vacancies` | Canonical logical vacancy | match-critical columns; requirements/benefits JSONB |
| `vacancy_source_references` | External identities and provenance | source/external ID, URL, content hash |
| `vacancy_matches` | Candidate-vacancy result | hard-filter result, score, components/explanation JSONB |
| `user_vacancy_actions` | Saved/application/feedback actions | action, reason, timestamps |
| `notification_preferences` | Quiet hours, digest, limits | mode, timezone, threshold, daily cap |
| `notifications` | Delivery idempotency and audit | unique match/type, status, attempts |
| `processed_telegram_updates` | Webhook deduplication | unique update_id, processed_at |
| `ai_requests` | Cost and reliability metadata | model, purpose, token counts, status; no full PII prompt |
| `audit_logs` | Security-relevant operations | actor, action, target, redacted metadata JSONB |

Experiences, projects, languages, vacancy skill groups, score components, and AI
explanations begin as versioned JSONB inside their aggregate when they are not queried
independently. Candidate skills and match-critical vacancy fields are normalized because
filtering and scoring require indexed queries. Tables are split later only when measured
query or integrity needs justify it. Raw external payloads use explicit expiration.

## Project layout

```text
app/
  api/routes/           HTTP, webhook, health, and metrics adapters
  bot/                  aiogram composition, handlers, keyboards, states
  core/                 settings, logging, security, observability
  db/                   async engine, sessions, models, repositories
  domain/               candidate, resume, vacancy, matching value objects
  ai/                   provider protocol, strict profile schemas, fake, and DeepSeek
  services/             application use cases and transaction boundaries
  workers/              arq worker, scheduler, and task entrypoints
  schemas/              shared Pydantic transport/structured-output models
alembic/                 migrations
tests/                   unit, integration, bot, and external-adapter tests
docs/                    architecture and operations documentation
infra/nginx/             reverse proxy configuration
```

Handlers remain thin. Services own business rules and explicit transactions. SQLAlchemy
models stay behind service/repository boundaries, while Pydantic models cross adapter
boundaries. External clients have timeouts and are closed during application shutdown.

## Implementation stages

1. **Foundation:** structure, configuration, Docker, FastAPI, aiogram composition,
   PostgreSQL, Redis, Alembic, logging, health checks, CI, and quality tooling.
2. **Telegram and users:** webhook/polling, registration, commands, beta gate, versioned
   consent, update idempotency, menu, and durable conversation state.
3. **Resumes:** secure upload validation, private storage, background extraction, status
   transitions, deletion, and safe errors.
4. **AI profile:** provider interface, fake/DeepSeek implementations, structured parsing,
   evidence/confidence, confirmation, and simple edits.
5. **Onboarding:** branching question engine, one message at a time, back/skip/pause, and
   restart-safe progress.
6. **Vacancies:** manual/forwarded intake and Remotive, Greenhouse, Lever, approved
   channel, and mock source adapters.
7. **Normalization and deduplication:** sanitization, extraction, hashes, canonical jobs,
   provenance, retention, and duplicate merging.
8. **Matching:** hard filters, configurable weighted score, explanations, threshold, and
   rematching. Embeddings remain optional.
9. **Notifications:** immediate/digest delivery, quiet hours, caps, buttons, retries, and
   delivery idempotency.
10. **Feedback and profile:** actions, reason capture, exclusions, saved jobs, and search
    preference updates without silently mutating confirmed skills.
11. **Admin:** users, sources, jobs, failures, AI usage, weights, feature flags, and
    audited privileged resume access.
12. **Security and release:** deletion workflow, privacy policy, audit review, backups,
    full test matrix, documentation, and production checklist.

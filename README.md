# JAHEZ Shipping

An independent English/Arabic Django shipping platform for JAHEZ TRADE CO.

**Current scope: Phase 7 quality, privacy and recovery. Phases 1–6 approved; Phase 7 is ready for review.** Bilingual tracking/manual operations, carrier and private AI workflows now have consistent error/correlation/privacy controls, tested durable restart recovery and matching database/private-file backup/isolated restore. See [Phase 7 evidence](docs/phases/PHASE_07_QUALITY_RECOVERY.md), [backup/restore](docs/BACKUP_RESTORE.md), [operating guidance](docs/OPERATIONS_RUNBOOK.md) and [SQLite migration plan](docs/POSTGRES_MIGRATION.md). Both keys remain privately configured; earlier limited live setup checks passed. Real carrier/webhook, complex original bill, off-server backups and production launch remain pending. Existing JAHEZ website/brand sources and services remain read-only. Phase 8 requires owner approval.

## Local quick start

Requires running Docker Desktop (macOS) or Docker Engine with Compose (Linux), plus Python 3 for the environment helper. Run commands from this project directory.

```bash
python3 scripts/init_dev_env.py
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml build
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py migrate
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py setup_roles
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py createsuperuser
```

The helper creates a private `.env.dev` with an independent random secret; it never overwrites an existing file. Do not use the example placeholder as a real secret. The environment persists across restarts. No provider API keys are required.

- English: http://localhost:18744/en/
- Arabic: http://localhost:18744/ar/
- Admin: http://localhost:18744/en/admin/ (Arabic: `/ar/admin/`)
- Integration health: http://localhost:18744/en/admin/integration-health/ (Arabic: `/ar/admin/integration-health/`)
- Liveness: http://localhost:18744/health/live/
- Readiness: http://localhost:18744/health/ready/

Create your own admin interactively with a strong unique password (minimum 12 characters). No default admin account/password is shipped. Assign intended staff to Shipping Operations or Shipping Read Only through Users.

For labeled local fixtures, run `docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_demo`. Copy the generated reference from the authorized shipment detail and submit it on the public homepage. The seed creates four synthetic shipments and one private sample bill, without creating users. The original shipping bill is still needed for its real field mapping.

For explicit carrier fixtures, run `docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_tracking_demo`. Review **DEMO-CARRIER** and its private carrier event, then approve bilingual display text/publication. This command performs no live provider request and cannot run in production.

[Phase 5 review](docs/phases/PHASE_05_AI_DRAFTS.md) · [AI behavior/model setup](docs/AI_BEHAVIOR.md) · [Phase 4 report](docs/phases/PHASE_04_17TRACK.md) · [17TRACK setup and contracts](docs/17TRACK_INTEGRATION.md) · [Data model](docs/DATA_MODEL.md) · [Status rules](docs/STATUS_RULES.md) · [Bill mapping](docs/DOCUMENT_FIELD_MAPPING.md) · [Company/CEO copy](docs/PUBLIC_COPY_REVIEW.md) · [Local development](docs/LOCAL_DEVELOPMENT.md) · [Phase progress](docs/PROGRESS.md) · [Technical decisions](docs/TECHNICAL_DECISIONS.md) · [Project boundaries](docs/PROJECT_BOUNDARIES.md) · [Asset manifest](docs/ASSET_MANIFEST.md) · [Complete project specification](PROJECT_PROMPT.md)

For local AI review, run `docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_ai_demo`, then open [English AI Workspace](http://localhost:18744/en/admin/ai/aidraft/workspace/) or [Arabic AI Workspace](http://localhost:18744/ar/admin/ai/aidraft/workspace/). No Groq request, account creation or customer message is sent by the seed.

## Focused verification

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py test --settings=config.settings.test
python3 scripts/check_boundaries.py
```

Production Compose is an initial skeleton, not approval to deploy. No VPS, Nginx, DNS or SSL changes have been made. Implement one phase at a time; read AGENTS.md and progress before continuing.

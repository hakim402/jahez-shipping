# JAHEZ Shipping

An independent English/Arabic Django shipping platform for JAHEZ TRADE CO.

**Current scope: Phase 3 manual shipping operations. Phases 1/2 approved; Phase 3 approval pending.** Staff can manage customers, shipments, products, manual events and private documents, then publish a restricted English/Arabic tracking summary. Dashboard counts use the database. Carrier and AI integrations remain disabled until their approved phases. Existing JAHEZ website sources/services remain read-only.

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
- Liveness: http://localhost:18744/health/live/
- Readiness: http://localhost:18744/health/ready/

Create your own admin interactively with a strong unique password (minimum 12 characters). No default admin account/password is shipped. Assign intended staff to Shipping Operations or Shipping Read Only through Users.

For labeled local fixtures, run `docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_demo`. Copy the generated reference from the authorized shipment detail and submit it on the public homepage. The seed creates four synthetic shipments and one private sample bill, without creating users. The original shipping bill is still needed for its real field mapping.

[Phase 3 review](docs/phases/PHASE_03_MANUAL_TRACKING_ADMIN.md) · [Data model](docs/DATA_MODEL.md) · [Status rules](docs/STATUS_RULES.md) · [Bill mapping](docs/DOCUMENT_FIELD_MAPPING.md) · [Company/CEO copy](docs/PUBLIC_COPY_REVIEW.md) · [Local development](docs/LOCAL_DEVELOPMENT.md) · [Phase progress](docs/PROGRESS.md) · [Technical decisions](docs/TECHNICAL_DECISIONS.md) · [Project boundaries](docs/PROJECT_BOUNDARIES.md) · [Asset manifest](docs/ASSET_MANIFEST.md) · [Complete project specification](PROJECT_PROMPT.md)

## Focused verification

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py test --settings=config.settings.test
python3 scripts/check_boundaries.py
```

Production Compose is an initial skeleton, not approval to deploy. No VPS, Nginx, DNS or SSL changes have been made. Implement one phase at a time; read AGENTS.md and progress before continuing.

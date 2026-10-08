# JAHEZ Shipping

An independent English/Arabic Django shipping platform for JAHEZ TRADE CO.

**Current scope: Phase 1 foundation preview. Owner approval pending.** Tracking lookup, shipment operations, carrier integration, AI, and the complete company page are not implemented yet. There are no live or fake shipment records in this phase. Existing JAHEZ website sources and services are read-only.

## Local quick start

Requires running Docker Desktop (macOS) or Docker Engine with Compose (Linux), plus Python 3 for the environment helper. Run commands from this project directory.

```bash
python3 scripts/init_dev_env.py
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml build
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py migrate
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py createsuperuser
```

The helper creates a private `.env.dev` with an independent random secret; it never overwrites an existing file. Do not use the example placeholder as a real secret. The environment persists across restarts. No provider API keys are required.

- English: http://localhost:18744/en/
- Arabic: http://localhost:18744/ar/
- Admin: http://localhost:18744/en/admin/ (Arabic: `/ar/admin/`)
- Liveness: http://localhost:18744/health/live/
- Readiness: http://localhost:18744/health/ready/

Create your own admin interactively with a strong unique password (minimum 12 characters). No default admin account/password is shipped.

[Local development](docs/LOCAL_DEVELOPMENT.md) · [Phase progress](docs/PROGRESS.md) · [Technical decisions](docs/TECHNICAL_DECISIONS.md) · [Project boundaries](docs/PROJECT_BOUNDARIES.md) · [Asset manifest](docs/ASSET_MANIFEST.md) · [Complete project specification](PROJECT_PROMPT.md)

## Focused verification

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py test --settings=config.settings.test
python3 scripts/check_boundaries.py
```

Production Compose is an initial skeleton, not approval to deploy. No VPS, Nginx, DNS or SSL changes have been made. Implement one phase at a time; read AGENTS.md and progress before continuing.

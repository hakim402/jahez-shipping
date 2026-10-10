# JAHEZ Shipping

An independent English/Arabic Django shipping platform for JAHEZ TRADE CO.

**Release 0.8.1: prepared for guided VPS deployment.** Includes the approved bilingual public interface, configurable WhatsApp contact, clearer admin navigation, English/Arabic form guidance and permission-checked deletion with retained audit history. Production uses a hardened image/Compose package, private configuration validation, backup/recovery and paused upgrade controls. See the [release checks](docs/RELEASE_0_8_1.md), [admin guide](docs/ADMIN_GUIDE.md), [VPS guide](docs/DEPLOYMENT_VPS.md), [Nginx/SSL](docs/NGINX_SSL.md), [upgrade/rollback](docs/UPGRADE_ROLLBACK.md), [backup/restore](docs/BACKUP_RESTORE.md) and [operating guidance](docs/OPERATIONS_RUNBOOK.md).

Repository: [hakim402/jahez-shipping](https://github.com/hakim402/jahez-shipping). Live deployment requires host inventory, DNS/TLS, private production configuration, provider/webhook verification and tested off-server backups. No development environment or database is included in the repository. See [publication policy](docs/PUBLICATION_POLICY.md); enable its Git hooks immediately after cloning.

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


For local AI review, run `docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_ai_demo`, then open [English AI Workspace](http://localhost:18744/en/admin/ai/aidraft/workspace/) or [Arabic AI Workspace](http://localhost:18744/ar/admin/ai/aidraft/workspace/). No Groq request, account creation or customer message is sent by the seed.

## Focused verification

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py test --settings=config.settings.test
```


[AI behavior](docs/AI_BEHAVIOR.md) · [17TRACK integration](docs/17TRACK_INTEGRATION.md) · [Data model](docs/DATA_MODEL.md) · [Status rules](docs/STATUS_RULES.md) · [Local development](docs/LOCAL_DEVELOPMENT.md)

The production package has been verified locally. Actual VPS, certificate and provider acceptance checks must be completed on the intended deployment.

# Local development and candidate review

Use only this checkout. Docker Desktop (macOS) or Engine/Compose (Linux), Python 3 and Compose 2.24.4+ are needed for the no-port review override. The normal dev project remains `jahez-shipping-dev`, web loopback 18744; production is `jahez-shipping-prod`, loopback 18743. Named data/Redis volumes remain stable. This cleanup does not start or restart owner services.

For this review, use the README image build and `python3 scripts/verify_cleanup.py`. It creates private synthetic env/data under ignored `private/cleanup-review`, disables Groq, uses no host ports or owner volumes, and cleans only its validated disposable Compose resources. It also tests old-image recovery and fresh/legacy migration paths. The real historical B/L/container example is never queried or seeded. Tests run against temporary databases, not the owner's database.

For a **separately approved new empty development installation only**:

```bash
python3 scripts/init_dev_env.py
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml build
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --wait redis
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --no-deps web python manage.py migrate --noinput
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --no-deps web python manage.py createsuperuser
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d web frontend
```

An existing `.env.dev` is preserved by the initializer; existing populated databases must use the [transition procedure](UPGRADE_ROLLBACK.md), not this fresh-install sequence. Migrations never auto-run in web. Redis is required for shared login counters; its failure denies login attempts/readiness rather than weakening protection. No API key is required to run the candidate. No worker or Beat exists.

Future dev URLs: `http://localhost:18744/en/`, `/ar/`, `/en/who-we-are/`, `/ar/who-we-are/`, `/en/admin/`, `/ar/admin/`. The owner creates the admin interactively; no account is auto-created. Tracking controls are disabled and localized. POSTing a reference has no lookup handler.

Frontend watches source in development; `exec frontend npm run build` rebuilds compiled CSS/local Alpine. Django reloads Python source in development. Do not edit a bound owner checkout while its server is running during a no-restart review. Image/dependency changes require a separately approved rebuild/recreation. Production has no source mounts/watch/dev server. Run `python3 scripts/compile_translations.py` after changing the singular Arabic catalog.

After approval, app-scoped status/logs use the same exact Compose prefix followed by `ps` or `logs --tail 50 web redis frontend`; test commands use `run --rm --no-deps web python manage.py test --settings=config.settings.test`. `down` preserves named volumes; never add `-v` or use global prune. Migration creation is `run --rm --no-deps web python manage.py makemigrations --check --dry-run` for consistency; only add future models after their separate approval.

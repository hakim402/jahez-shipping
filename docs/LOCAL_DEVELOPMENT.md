# Local development

Requirements: Docker Desktop or Docker Engine with Compose, Git and Python 3 for the small host utilities. Node and Django dependencies run inside Docker; a host `node_modules` or Python virtual environment is optional. Run these commands from the repository root.

Local project: `jahez-shipping-dev`. Web: `127.0.0.1:18744`. Data lives in named Docker volumes; `.env.dev` is private. An existing local database and administrator are preserved.

## First setup on a new checkout

Create the environment only if `.env.dev` is absent:

```bash
python3 scripts/init_dev_env.py
```

The initializer generates a private secret and refuses to overwrite an existing file. Set `SHIPPING_BUSINESS_TIME_ZONE=Asia/Shanghai` for China time. Add your own WhatsApp/Groq configuration privately when needed. Groq is disabled in the example; ordinary operation and tests need no API key.

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml build web
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --wait redis
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --no-deps web python manage.py migrate --noinput
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --no-deps web python manage.py createsuperuser
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --wait web frontend
```

Enter your chosen administrator credentials at the terminal prompts. Use the configured password validation. Existing installations only need a new administrator if the owner requests one.

Open [the website](http://localhost:18744/en/), [Arabic](http://localhost:18744/ar/) or [admin](http://localhost:18744/en/admin/). See the [admin guide](ADMIN_GUIDE.md) for real workflow steps.

## Daily work

Python source reloads in the development web container. The frontend container watches templates and Tailwind source. After pulling code, apply any forward migrations without deleting the database:

```bash
git pull --ff-only origin main
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml stop web
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml build web
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --no-deps web python manage.py migrate --noinput
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --wait web frontend
```

Keep meaningful local records backed up before schema work. Image rebuilding uses locked dependencies; source-only edits normally just reload. When frontend dependencies change, recreate the frontend container so its startup reruns `npm ci`:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --force-recreate frontend
```

For an immediate asset rebuild or Arabic catalog compilation:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec frontend npm run build
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec web python scripts/compile_translations.py
```

## Status, logs and stopping

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml ps
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml logs --tail 50 web redis frontend
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml stop
```

`stop` retains containers and data. `down` also retains named volumes unless `-v` is supplied. Keep those volumes and private environment files when updating code. Check readiness at http://localhost:18744/health/ready/; a missing migration or Redis outage returns 503.

## Test without owner data

This production image uses temporary test databases, synthetic references and mocked provider requests. It has no network or owner-data mounts:

```bash
docker build --target production -t jahez-shipping-review:0.9.0 .
docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 768m --cpus 1 \
  jahez-shipping-review:0.9.0 python manage.py test --settings=config.settings.test
python3 -m unittest tests.test_publication_policy
```

For complete synthetic release/Redis/failure/recreation/backup acceptance:

```bash
python3 scripts/verify_release.py --image jahez-shipping-review:0.9.0
python3 scripts/verify_nginx.py
```

The verifier creates a dedicated project with no host ports, an internal network, separate volumes and a synthetic environment. It cleans its disposable Docker resources. `private/release-review/` holds ignored evidence. Never point it at owner environments or volumes. `--keep-review` is only for immediate synthetic browser review; clean the exact generated directory using `--cleanup` afterward.

`scripts/verify_cleanup.py --image jahez-shipping-review:0.9.0 --old-image VERIFIED_OLD_IMAGE_ID` is the optional historical migration/recovery rehearsal. It requires a retained matching 0.8.1 image. It is not a normal development or deployment command.

Before publishing, use the [publication checks](PUBLICATION_POLICY.md). `python3 scripts/check_boundaries.py` is an additional owner-checkout check when its private protected-source baseline exists; it does not require modifying sibling projects.

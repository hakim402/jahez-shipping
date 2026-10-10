# Local development — release 0.8.1

Run all commands from the directory of this independent checkout. Never run them in `jahez-trade-co`.

## Prerequisites

macOS: Docker Desktop running with Compose; Linux: Docker Engine and Compose plugin running, with permission for your user to use this dedicated project. Python 3 is required only for the environment helper. Node/npm on the host are optional; container frontend performs normal rebuild/watch.

Docker bases are pinned. First build requires access to Docker Hub, PyPI and npm. No live carrier/AI credentials are required. Check `docker info` and `docker compose version`. Confirm local port 18744 is unused without stopping any existing application.

## First boot

```bash
python3 scripts/init_dev_env.py
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml build
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py migrate
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py setup_roles
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py createsuperuser
```

`init_dev_env.py` creates `.env.dev` mode 0600 with a random stable development secret. Keep that file; regenerate only deliberately because rotating it invalidates sessions. It does not read any existing website env file. Interactive `createsuperuser` asks you for credentials; use your own strong password. Do not put passwords in shell arguments or commit them.

The one-off web command starts this project's Redis automatically through depends_on, then waits for Redis health. SQLite migrations are run once by that command; web, worker and Beat never migrate themselves. The named data volume is initialized from a directory owned by UID 10001 in the image, so all app processes can write there without running as root. Do not override the app user or volume paths casually.

Services: web (Django autoreload), worker (Celery concurrency 1), beat (one scheduler, one-minute durable tracking recovery/reconciliation schedule from Phase 4), redis (internal only, AOF), frontend (Tailwind watch). Each uses this project's network. Development web/worker/Beat share source bind mounts, independent shipping data and Beat state. Frontend uses its own node_modules volume; its initial build then watcher writes compiled CSS/local Alpine into this project's static directory.

English: http://localhost:18744/en/ · Arabic: http://localhost:18744/ar/ · Admin: http://localhost:18744/en/admin/ · Arabic admin: http://localhost:18744/ar/admin/

Public contact links use `SHIPPING_WHATSAPP_NUMBER` from `.env.dev` (or `.env.prod` in production). Set an international number including its country code; a leading `+`, spaces, parentheses and hyphens are accepted. Empty or invalid values hide contact links. After changing `.env.dev`, recreate only the web service with `docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --no-deps web`. The homepage no longer displays synthetic-example or design-review controls.

## Reviews and useful commands

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml ps
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml logs -f web worker beat frontend
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py check
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py test --settings=config.settings.test
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py seed_demo
```

`seed_demo` is idempotent and development-only. It now creates four clearly synthetic shipments, products/events, and one private sample bill; existing reviewed shipments are retained without resetting publication. No account/password is created. The ordinary tracking form reads published, unarchived records by random JAHEZ reference, with shared-cache throttling (30 per address per five minutes); it never calls a provider. Copy the DEMO-MANUAL or DEMO-NO-UPDATES reference from authorized shipment admin for review. The short Phase 2 design fixture reference is not a database reference. 17TRACK defaults disabled until privately configured; AI remains unimplemented.

## Editing and rebuilding

Django web auto-reloads Python source. Templates reload on request. Tailwind watcher rebuilds on frontend/template changes. Rebuild vendored Alpine with:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec frontend npm run build
```

Worker and Beat do **not** auto-reload Python changes despite source mounts. Restart them after task/settings edits:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml restart worker beat
```

Dependency/image changes need build then up:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml build
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d
```

Future migration creation (inside this new app only):

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py makemigrations
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py migrate
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm web python manage.py setup_roles
```

Public bilingual copy is in apps/core/copy.py. The custom admin catalog is locale/ar/LC_MESSAGES/django.po; run `python3 scripts/compile_translations.py` after updating it. This helper compiles this app's simple catalogs with standard-library code, without a host gettext install. Django/Unfold ship their own translations. Public pages are fully bilingual. Phase 7 bilingual admin/public browser evidence is recorded in its report.

## Health and queue

`/health/live/` tests process serving. `/health/ready/` checks SQLite connection/shipment schema + Redis ping with short timeouts and no paid API call. Readiness does not authenticate or test external providers. Worker health uses a targeted Celery ping; Beat health checks its running PID, not that future operational tasks succeeded.

## Safe restart/shutdown

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml restart web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml down
```

`down` preserves all named volumes; never add `-v`. Use only this Compose project/file. Rebuilding and restarting preserve auth accounts, SQLite, private-directory files and Redis state. Do not inspect or alter other projects' data.

Production uses `.env.prod`, a separate Compose project/volumes and loopback port 18743. Its complete Phase 8 package is locally tested; actual VPS activation requires Phase 9 approval. See DEPLOYMENT_VPS.md and NGINX_SSL.md.

## Reproduce the Phase 1 persistence check

This development-only script creates its own synthetic, unauthenticated session and private marker; it does not create a customer/admin. Keep all steps scoped to this app.

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_persistence.py prepare
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml restart web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_persistence.py verify
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_persistence.py cleanup
```

Wait for web readiness after restart before running verify. Cleanup deletes only the script's identified synthetic record/file. This does not replace a real recovery or concurrency test.

## Phase 2 public design review

The app is already running locally at http://localhost:18744/en/ and http://localhost:18744/ar/. Company pages: `/en/who-we-are/` and `/ar/who-we-are/`.

Use **View a synthetic example** / **عرض مثال تجريبي** for the illustrative result. Open **Review tracking states** / **مراجعة حالات التتبع** for eight explicit states. Controls POST with CSRF protection and work without Alpine. They do not create records or call providers. The example reference is `JHZ-DEMO-7K4P8Q2`; typing it in the ordinary form does not select a fixture. Never use real references for design review.

Fixture selection requires both `DEBUG=True` and `PUBLIC_UI_PREVIEW_ENABLED=True`; production hard-disables the flag. Query parameters cannot select fixtures. The rate-limit/submitting examples are static design states, not proof of implemented live tracking, real throttling, or provider availability. Ordinary stored manual tracking is implemented in Phase 3; carrier and AI workflows are implemented separately; these design fixtures still provide no live-provider evidence.

The company page uses the approved company copy and Majed Saleem portrait. Review changes using synthetic fixtures without modifying production records.

## Phase 3 manual workflow

1. Sign in using your existing owner account, or create your own interactively using the first-boot command. Run `setup_roles` after migrations; assign only intended staff to the defined groups.
2. Create a customer and a private manual shipment with approved English/Arabic route labels. Save; copy its private random JAHEZ reference from its detail.
3. Add bilingual product rows and manual timeline entries. Select public only for reviewed rows; explicitly update the overview status independently of the timeline.
4. Upload a synthetic plain PDF/PNG/JPEG through Documents. It remains private; restricted downloads are audited. Do not use a real bill for screenshots.
5. Publish the shipment and submit its random reference on `/en/` and `/ar/`. Expect only approved summary fields, with unknown ETA when absent.
6. Try read-only access, archive/restore, and reference revocation. Restoring keeps the shipment private; the revoked reference stops working. Use synthetic records for these checks.

For existing data, take a consistent SQLite online backup and copy private files before schema changes. Phase 3 has a local pre-migration SQLite snapshot; complete matching backup/restore is documented in BACKUP_RESTORE.md. Never delete the data volume to roll back.

Reproduce the focused manual-record persistence check (development DEMO fixtures only):

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_manual_persistence.py prepare
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml restart web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_manual_persistence.py verify
```

Wait for readiness after restart. The script compares relations, status/publication/revision/reference hashes and private bill checksums; it also checks SQLite integrity/WAL/timeout. Its baseline lives privately under `/data`, not in Git. This does not prove backup recovery, concurrent throughput or future carrier jobs.

## Phase 4 carrier review

Keep `TRACK17_ENABLED=false` for synthetic review. Use your existing owner login; no new test account is needed. After migrations, `setup_roles` includes the carrier view/register/refresh/retry permissions for Operations and metadata view only for Read Only.

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py setup_roles
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_tracking_demo
```

Open `/en/admin/integration-health/` or `/ar/admin/integration-health/`. Expect disabled status, no verified live synchronization and explicitly labeled DEMO jobs. Review carrier events through Tracking Events; imported source/time fields stay readonly, approved bilingual titles/details and publication can be reviewed. DEMO-CARRIER starts private on first seeding and retains reviewed publication on reruns. DEMO references are barred from outbound provider calls and production public lookup.

A real supported carrier reference belongs on an active API/hybrid shipment. Its detail has **Review registration** and **Review detail retrieval**, each with confirmation. Disabled/missing-key/unsupported inputs fail honestly. Enabling the integration privately permits requested/scheduled server-side calls; never enter keys into public/admin forms or chat. Read the [exact 17TRACK setup](17TRACK_INTEGRATION.md) before enabling. Production webhook routing remains a later deployment step.

Reproduce the development recovery review only with 17TRACK disabled:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_tracking_recovery.py prepare
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_tracking_recovery.py dispatch
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_tracking_recovery.py verify
```

Prepare deliberately simulates broker publication failure **after a real SQLite commit**, leaving a private DEMO receipt/job. Dispatch uses the real dedicated Redis/Celery recovery task; wait for processing, then verify. Its private review marker makes prepare single-use; later runs can dispatch/verify the same review. Do not call this a live provider or real Redis-crash test.

Reproduce Phase 4 record/private bill persistence after all DEMO jobs finish:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_tracking_persistence.py prepare
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml restart web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_tracking_persistence.py verify
```

Avoid editing synthetic records between baseline and verification. Stable snapshots contain only synthetic IDs/flags/reference hashes/checksums, under private `/data`. This is persistence verification, not complete recovery. A Phase 4 pre-migration SQLite online snapshot exists locally at `/data/phase04-before.sqlite3`; matching database/files backup and restore is now available; see BACKUP_RESTORE.md.

## Phase 5 private AI workflow

The admin AI Workspace is `/en/admin/ai/aidraft/workspace/` (Arabic `/ar/admin/ai/aidraft/workspace/`). From a saved shipment use Request an AI draft; a private document has an extraction link with source selection prefilled. Upload alone does not send to Groq. Explicit consent, source permissions and current records are required. [AI behavior/model setup](AI_BEHAVIOR.md) documents limits, privacy, model modes, retention and review.

Local synthetic seed (no live credentials or calls):

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_ai_demo
```

Recreate only Shipping services after env changes; workers have the source mount but do not hot reload Python modules. Restart worker/Beat after service code changes. Tests force both integrations disabled/keys empty in base test settings; provider cases use explicitly synthetic overrides and isolated DB/private storage.

Reproduce deliberate publication-failure recovery using private DEMO work:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_ai_recovery.py prepare
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --force-recreate web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_ai_recovery.py dispatch
# After the actual worker finishes:
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_ai_recovery.py verify
```

Preparation is intentionally single-use and retains its private 0600 marker under `/data/phase05-recovery-review.json`; do not remove it to hide review history. Already prepared installations use dispatch/verify only. This uses **real SQLite/Redis/Celery conversion/validation with synthetic proposals** and a **simulated** broker submission failure; it does not prove live Groq or a real Redis crash/restore. No test user account is needed. The synthetic draft cannot make an external provider call.

Hash-only DEMO persistence review (prepare once after work settles; verify after recreation):

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_ai_persistence.py prepare
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --force-recreate web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_ai_persistence.py verify
```

The private 0600 marker is `/data/phase05-persistence-review.json`. A deliberately modified DEMO record changes the baseline and should fail verification; do not overwrite the baseline to hide a real difference. This checks recreation persistence/integrity, not complete backup/restore.

Offline production-image review after building the image:

```bash
docker build --target production -t jahez-shipping:0.8.1 .
docker run --rm --network none --entrypoint python jahez-shipping:0.8.1 scripts/verify_ai_production_image.py
```

This disposable container has no user data volumes, accounts or published ports; provider HTTP is locally mocked. It does not deploy production.


## Phase 6 operational assistant

Open `/en/admin/ai/aidraft/assistant/` or `/ar/admin/ai/aidraft/assistant/`. See [tool/permission contract](AI_SEARCH_TOOLS.md). Local reads need no provider and never change operational rows. Optional explanation requires source permission, explicit metadata consent and Groq; DEMO outbound remains blocked.

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_search_demo
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --pull never web python manage.py test tests.test_operations --settings=config.settings.test
```

The Phase 6 migration is `ai.0002_operational_assistant`; run once before workers as in the normal quick start. `setup_roles` updates definitions without creating accounts/assignments. Use existing intended staff for interactive review.

Hash-only persistence review uses a single-use private baseline (already prepared/verified locally; do not overwrite it):

```bash
# New checkout's first review only:
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_search_persistence.py prepare
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --force-recreate web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_search_persistence.py verify
```

Current image offline verification:

```bash
docker build --target production -t jahez-shipping:0.8.1 .
docker run --rm --network none jahez-shipping:0.8.1 python scripts/verify_production_quality.py
```

No production Compose/ports/volumes or real account is created by this image check. Phase 7 matching database/files restore and contention now passed; see [backup/restore](BACKUP_RESTORE.md). The isolated restore verifier uses production data/permission settings with source static URLs because the development image has no collected static manifest; the actual production image's collected static/manifest assets are checked separately offline.

Phase 7 requires no schema migration. Its dedicated single-use private persistence marker preserves the earlier phase evidence:

```bash
# Only before a new baseline exists; never overwrite a prior review marker:
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_quality_recovery.py prepare-persistence
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --pull never --force-recreate web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_quality_recovery.py verify-persistence
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --no-deps --pull never web python scripts/verify_sqlite_contention.py
```

The last command creates/discards its own temporary database and synthetic account, with providers disabled. It never opens the live `/data` DB. See [operating guidance](OPERATIONS_RUNBOOK.md) for actual Redis interruption, log checks and health/retention limits. The local data volume retains `/data/backups` and `/data/phase07-isolated-restore` privately; no production schedule/off-server copy has been configured.

## Phase 8 isolated production package checks

Production Compose is complete; it is still gated for real activation. Keep `.env.dev`/existing data; never initialize `.env.prod` merely for local QA. Docker Compose 2.24.4+ is needed for the no-port `!reset` review override. These checks use synthetic env/keys, no host port/account/provider, and separate temporary volumes:

```bash
docker build --target production -t jahez-shipping:0.8.1 .
docker run --rm --network none jahez-shipping:0.8.1 python -m pip check
docker run --rm --network none jahez-shipping:0.8.1 python scripts/verify_production_quality.py
python3 scripts/verify_production_stack.py
python3 scripts/verify_nginx.py
python3 scripts/check_boundaries.py
```

The stack verifier migrates an independent production-mode stack, checks nonroot private uploads/EN+AR/hashed assets/health, quiesced backup, release/refusal paths, recreation persistence and isolated restore; removes only its fixed synthetic project/volumes afterward. `--keep` retains private review resources for investigation; inspect/clean only their exact names. The Nginx test uses the pinned official container with networking disabled; HTTPS succeeds with disposable local certificates and deliberately fails when certificates are absent. This is configuration syntax evidence, not issued certificates/real server TLS. See DEPLOYMENT_VPS.md, NGINX_SSL.md and UPGRADE_ROLLBACK.md.

After dependency/image changes, rebuild and recreate **only Shipping** web/worker/Beat; source autoreload does not update worker imports or baked libraries. Preserve named data volumes and privately configured env. Existing Phase 7 backup archives were written by 0.7.0 and require its retained immutable image for verification/restore. New 0.8.1 backups use the current image; cross-version verification deliberately refuses. Do not overwrite baseline markers or label old evidence as a new run.

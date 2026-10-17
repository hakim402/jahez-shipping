# Local development and isolated acceptance

Use only this Shipping checkout. Docker Desktop (macOS) or Engine/Compose (Linux), Python 3 and Compose 2.24.4+ are required for the isolated no-port override. Normal development is `jahez-shipping-dev`, loopback 18744; production is `jahez-shipping-prod`, loopback 18743. Never infer target identity from a port alone.

The owner-authorized local reset is historical and complete. Development has the cleaned schema plus `containers.0001_initial` and `0002_reviewed_public_tracking`, preserving the existing owner-managed administrator and private files/configuration through additive migrations. No synthetic journey/account was seeded there. Keep the private matching old-image recovery archive. Do not reset development again or use the fresh-install sequence on it. Production reset remains a separate Phase 8 operation pending access and recovery checks.

## Current addresses and admin access

Home: `http://localhost:18744/en/` or `/ar/`; company: `/en/who-we-are/` or `/ar/who-we-are/`; admin: `/en/admin/` or `/ar/admin/`; lookup: `/en/track/` or `/ar/track/`. A reviewed public journey's code opens `/<language>/track/<code>/`. Lookup accepts the random JAHEZ code, never B/L or a physical container number.

Preserve an existing intended administrator. If the owner requests a new one, create it interactively with configured validation:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec web python manage.py createsuperuser
```

Enter the password only at its hidden terminal prompts; the configured minimum is 12 characters. Do not bypass validation, publish credentials or seed a default account. Existing hashes, sessions and permissions remain owner data. [Admin workflow](ADMIN_GUIDE.md) covers publication review, manual fallback, identity binding and explicit refresh.

## New empty development installation only

After verifying the intended installation is new and empty:

```bash
python3 scripts/init_dev_env.py
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml build
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --wait redis
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --no-deps web python manage.py migrate --noinput
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml run --rm --no-deps web python manage.py createsuperuser
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d web frontend
```

The initializer preserves an existing `.env.dev`. For an existing cleaned installation, inspect applied/pending migrations and retain a matching private backup before an approved additive migration. Populated legacy schemas require [their separate recovery gate](UPGRADE_ROLLBACK.md), not this empty-install sequence. Web never auto-migrates. Source newer than its schema fails readiness; fix the reviewed migration mismatch rather than resetting data.

Redis is required for shared fail-closed login/lookup limits and readiness. No API key is needed for ordinary local operation or mocked acceptance. Groq stays disabled in examples; preserve any existing private configuration. No worker, broker or Beat exists. The daily timer is prepared but inactive until Phase 8.

## Synthetic release verification

Use the [README build/test sequence](../README.md#reproduce-release-verification-in-isolation). The new production-image verifier is:

```bash
python3 scripts/verify_release.py --image jahez-shipping-phase07:0.9.0
```

It uses production settings, the installed image, no owner env/data/host ports and an internal-only network. Provider results come from local synthetic fixtures. It verifies the complete lifecycle, actual shared Redis/outage behavior, runtime resource/security/static/health controls, web recreation and matching recovery with model rows/private hashes. It cleans only its validated project/volumes; private synthetic evidence remains ignored. `--keep-review` retains a successful fixture temporarily for browser acceptance; after inspecting it, run `python3 scripts/verify_release.py --cleanup PRIVATE_REVIEW_DIRECTORY` with the exact generated directory. Do not leave synthetic sessions/resources running after review.

The historical `verify_cleanup.py --image jahez-shipping-phase07:0.9.0 --old-image VERIFIED_0_8_1_IMAGE_ID` additionally needs a verified matching immutable 0.8.1 image; substitute its checked ID, not an assumed tag. It tests guarded legacy transition/refusal and old-image restore only, not the chosen future fresh-production reset. No real B/L is queried or seeded by either verifier. Unit/source/Groq tests use local fixtures/mock transport, including parser/host/redirect constraints, prompt injection, time/token/content caps, concurrency and private/public separation. `tests.test_release_journey` exercises the whole admin-to-archive lifecycle; corruption regressions remain in `tests.test_recovery`.

Browser acceptance uses disposable synthetic journeys/contact/session. It verifies EN/AR keyboard forms, public/admin pages, desktop/mobile RTL, source dates, timeline and stale/error states. A local preview proxy may forward to the isolated production image for layout review; it is not real HTTPS/proxy/cookie deployment evidence. No message is sent, live provider accessed, owner login tested or real journey opted into publication. Release, authorized live source and production/scheduled evidence are recorded separately.

## Routine source work

Django reloads Python in development. The frontend watches templates/styles; `exec frontend npm run build` rebuilds compiled CSS/local Alpine. Production has no source mount/watch/dev server. Run `python3 scripts/compile_translations.py` after Arabic catalog edits. Dependency/runtime changes need a deliberate scoped rebuild, not a restart of unrelated projects.

Use the exact development Compose prefix followed by `ps` or safe `logs --tail 50 web redis frontend`. Check migration consistency with `python manage.py makemigrations --check --dry-run` in the configured isolated runtime. Do not run ordinary tests against owner data or print resolved environments. `down` preserves named volumes; never use `-v`, global prune or another app's commands. [Prepared scheduler instructions](OPERATIONS_RUNBOOK.md#prepared-linux-timer--activation-only-in-phase-8) remain installation guidance, not activation permission.

# Release 0.8.1 — VPS preparation and GitHub publication

Date: 10 October 2026

Prepared source release: `v0.8.1` on `main`. The GitHub tag identifies the exact source commit; record the deployed commit separately on the VPS. This is a locally verified deployment package, not evidence that a live VPS, certificate or webhook has already been activated.

## Included

- Owner-approved English/Arabic tracking and company UI; responsive harbor background, WhatsApp contact from private environment configuration, FAQ cards and the supplied original-preserving CEO portrait.
- Simplified admin navigation, bilingual form help and confirmed single-record deletion with permissions, protected relations, retained audit history and durable private-file cleanup.
- `shipments.0003_fileremoval_alter_auditentry_shipment_and_more`. Existing deployments must apply it through the paused upgrade procedure. Previous matching-version backup images remain necessary for old recovery points.
- Version 0.8.1 across application, package lock, development/production image defaults and production environment example. Dependency versions and public UI output were not changed during release preparation.

## Final checks actually run

| Check | Result |
|---|---|
| Complete Django suite, isolated test settings | 186 passed; no system-check errors; live integrations disabled |
| Production image build | Passed; digest-pinned bases, locked dependencies, translations and collected static manifest |
| `python -m pip check` in isolated release image | No broken requirements |
| Offline production security/quality verifier | Passed migrations, static manifest, bounded PDF/scan conversion, mock SDK transport, bilingual private/public separation, CSRF, hosts, redirects, error privacy and log redaction |
| Complete isolated production Compose review | Passed fresh migration, role setup, web/worker/Beat/Redis health, non-root/read-only runtime, bilingual HTTP and hashed CSS, private-file integrity, service recreation and persisted shipment/reference/publication |
| Paused release/rollback/recovery | Backup and isolated matching database/files restore passed; deliberately changed-schema rollback/resume refused while writers stayed paused |
| File-backed SQLite contention | Three separate processes, 60 operations; zero lost writes or duplicate claims; integrity/foreign keys passed. Local timings are not a VPS capacity claim |
| Exact Nginx configurations | HTTP bootstrap parsed; HTTPS refused absent certificates; HTTPS parsed with disposable self-signed fixtures |
| Private source/history audit | Configured credentials absent from selected source/history; no actual env, database, upload, backup or dependency directory selected; no file over GitHub's 100 MiB limit |
| Public UI freeze | Approved public templates, content, images and compiled CSS match the pre-admin baseline |
| Project boundary / whitespace | All 1600 protected checksums and protected Git state unchanged; diff check passed |

The production-stack verifier was updated to recognize the approved stylesheet cache query after its hashed filename. Its escape spelling was corrected without changing the executed check code.

The full stack review used only `jahez-shipping-phase08-review`, disposable private synthetic configuration and dedicated review volumes, with no host ports or live provider credentials. It created no owner account, sent no customer message and touched no development/private production volume. Validated review containers, network, volumes and temporary configuration were removed afterward. Nginx review certificates were temporary and never installed on a server.

The only expected deployment warning is `security.W004`: HSTS intentionally remains zero until actual HTTPS verification succeeds. No security check was suppressed to conceal an error.

## VPS steps that still require actual host evidence

1. Collect the intended host inventory privately. Verify tool versions, memory/disk, existing sites, include paths and ownership of port 18743.
2. Clone this repository into its own directory and pin `v0.8.1`. Generate a new private `.env.prod`; do not copy development secrets or records. Configure WhatsApp privately if contacts should appear.
3. Use [the VPS guide](DEPLOYMENT_VPS.md), or [paused upgrade procedure](UPGRADE_ROLLBACK.md) for an existing Shipping installation. Apply migration 0003 before starting the matching web and worker image.
4. Install only the separate Shipping Nginx/bootstrap files after verifying the actual layout. Issue the real certificate before enabling the HTTPS config. Verify HTTPS, admin login/CSRF, public lookup, private downloads and continued health of the existing sites.
5. Configure the intended administrator privately, verify appropriate real carrier/webhook/AI work when authorized, and set up scheduled encrypted/off-server backup retrieval plus restore evidence.

These are deployment acceptance requirements. No direct SSH, DNS, firewall, certificate, shared Nginx or live VPS operation was performed by this release check.

## Reproduce locally

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py test --settings=config.settings.test
docker build --target production -t jahez-shipping:0.8.1 .
docker run --rm --network none jahez-shipping:0.8.1 python -m pip check
docker run --rm --network none jahez-shipping:0.8.1 python scripts/verify_production_quality.py
docker run --rm --network none jahez-shipping:0.8.1 python scripts/verify_sqlite_contention.py
python3 scripts/verify_production_stack.py
python3 scripts/verify_nginx.py
python3 scripts/check_publication.py
```

The complete stack verifier refuses an already running review project and cleans only its validated disposable resources. Never substitute the development or real production project/volumes into these checks.

# JAHEZ Shipping

English/Arabic shared-container tracking with Django 5.2, templates, Tailwind, Alpine, Unfold and SQLite. **0.9.0 is a local release candidate.** The last recorded deployed release is 0.8.1; no production reset, upgrade or schedule activation is established by the local work.

Administrators register a carrier reference and physical-container journey, explicitly refresh validated carrier facts, review bilingual details/manual updates, publish and share one random JAHEZ code. Public pages read only the approved saved snapshot. They preserve actual/estimated dates, source precision and unknown zones, show the last approved check and staleness, and never invoke a carrier, browser, Groq or refresh job. This is milestone tracking, not continuous GPS.

First publication is manual. Automatic validated carrier updates require an explicit per-journey opt-in, off by default, on an already reviewed public journey. Private notes, unknown mappings and unreviewed AI Arabic labels never automatically publish. Archive hides the journey immediately. There are exactly two business models: Container and ContainerEvent; no customer accounts, uploads, invoices, broker or worker. Redis supplies shared fail-closed login and public-lookup counters.

The bounded daily command and 09:00 Asia/Kabul systemd package are prepared. The timer remains uninstalled/inactive until separately approved Phase 8 activation. Source access uses an undocumented carrier website interface with unverified unattended-use permission and continuity; see [source limits/manual fallback](docs/OPERATIONS_RUNBOOK.md#phase-1-carrier-source-proof). Earlier authorized live carrier/Groq acceptance is distinct from synthetic release tests and production activation.

## Local URLs and data

| Page | English | Arabic |
|---|---|---|
| Home | `http://localhost:18744/en/` | `http://localhost:18744/ar/` |
| Company | `http://localhost:18744/en/who-we-are/` | `http://localhost:18744/ar/who-we-are/` |
| Administrator | `http://localhost:18744/en/admin/` | `http://localhost:18744/ar/admin/` |
| Shared lookup | `http://localhost:18744/en/track/` | `http://localhost:18744/ar/track/` |

Enter the reviewed journey's random JAHEZ code to open `/<language>/track/<code>/`. B/L and physical container numbers are not lookup credentials. The configured future public origin is `https://shipping.jahez.online`; these local URLs do not imply the candidate is deployed there.

Development already has the cleaned schema and additive container/publication migrations. Existing owner accounts and private environment are preserved; no example records or default credentials are seeded. Do not reset it again. Fresh production is the owner's requested Phase 8 path, pending working access, actual target inventory and matching old-image recovery verification. [Local setup](docs/LOCAL_DEVELOPMENT.md) distinguishes a new empty installation from an existing database.

## Reproduce release verification in isolation

From this Shipping checkout, with Docker running:

```bash
docker build --target production -t jahez-shipping-phase07:0.9.0 .
docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 768m --cpus 1 \
  jahez-shipping-phase07:0.9.0 python manage.py test --settings=config.settings.test
python3 -m unittest tests.test_publication_policy
python3 scripts/verify_release.py
python3 scripts/verify_nginx.py
python3 scripts/check_boundaries.py
python3 scripts/check_publication.py --index
git diff --check
```

The production image uses locked dependencies/base digests and compiled assets. Its tests use temporary synthetic databases with no network or owner mounts. The host-only Git-history publication fixture is intentionally skipped inside the image and runs on the host. Boundary checks require this checkout's local protected-source baseline. `--index` checks the staged tree; review the complete intended changes before staging/publishing.

`verify_release.py` creates only the dedicated no-port `jahez-shipping-release-review` project, private synthetic environment, internal-only network and new volumes. It exercises the complete admin/refresh/public/daily/failure/manual/archive journey with local provider fixtures, real Redis and an outage, nonroot/read-only/resource/static/health behavior, recreation, and matching database/private-file backup/restore including container/event rows. It removes its disposable resources on completion. Evidence stays under ignored `private/release-review`. `--keep-review` is solely for immediate isolated browser inspection; explicitly clean its validated directory with `--cleanup` afterward. No owner environment, database, server, provider or timer is used.

The separate `scripts/verify_cleanup.py --image jahez-shipping-phase07:0.9.0 --old-image VERIFIED_0_8_1_IMAGE_ID` rehearses the historical populated-0.8.1 transition and matching-old-image restore with synthetic data and a verified matching immutable old image. Replace the placeholder with the checked image ID; the historical default ID may be absent on a new Docker installation. A reconstructed recovery image must be identified as reconstructed and verified against retained archives before use. It is not the selected fresh-production reset procedure. Do not apply the guarded irreversible retirement graph to an unverified owner installation; [upgrade/recovery gates](docs/UPGRADE_ROLLBACK.md) remain mandatory.

## Maintained guides

- [Local development and isolated review](docs/LOCAL_DEVELOPMENT.md)
- [Manual administration/publication](docs/ADMIN_GUIDE.md) and [data rules](docs/DATA_MODEL.md)
- [Operations, Groq, source fallback and inactive scheduler](docs/OPERATIONS_RUNBOOK.md)
- [Matching backup/restore](docs/BACKUP_RESTORE.md) and [upgrade/recovery](docs/UPGRADE_ROLLBACK.md)
- [Deployment boundaries](docs/DEPLOYMENT_VPS.md) and [Nginx/SSL](docs/NGINX_SSL.md)
- [Implementation boundaries](docs/CONTAINER_DESIGN.md) and [publication policy](docs/PUBLICATION_POLICY.md)

Development alone adds the frontend watcher. Production uses one Gunicorn worker/two threads, internal Redis and a dedicated data volume; the prepared host timer reuses the existing web container. The old shipments/tracking/ai app labels remain migration-only shells. Owner prompts, local phase reports, screenshots, private captures, databases and backups remain excluded from Git and image contexts.

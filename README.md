# JAHEZ Shipping

English/Arabic Django foundation for shared container tracking. **0.9.0 is a cleanup candidate, not a deployed release.** The last recorded live release is 0.8.1; this cleanup does not migrate owner databases or change the VPS.

The candidate keeps the branded homepage/company page, RTL, configured WhatsApp contact, Unfold administrator authentication, sessions, shared login protection, safe logs and SQLite backup/restore. Public tracking is explicitly unavailable. Container registration, website retrieval, Groq extraction and daily refresh are planned only; no public request calls a provider.

Legacy business tables are removed by guarded, irreversible migrations. Existing installations require a separately approved maintenance window and verified matching old-image database/private-file backup. **Do not run migration/startup commands against existing owner data during this review.**

## Verify in isolation

With Docker running, from this independent checkout:

```bash
docker build --target production -t jahez-shipping-cleanup:0.9.0 .
python3 scripts/verify_cleanup.py
docker run --rm --network none -e DJANGO_SETTINGS_MODULE=config.settings.test -e SHIPPING_DATA_DIR=/tmp/review jahez-shipping-cleanup:0.9.0 python manage.py test --settings=config.settings.test
python3 scripts/check_boundaries.py
python3 scripts/check_publication.py --index
git diff --check
```

The cleanup verifier uses synthetic private data, a separate no-port Compose project and retained immutable 0.8.1 image; no owner env/volume/service is used. Review results in the local-only cleanup report. No default admin/password is shipped.

## Maintained guides

- [Local development and isolated review](docs/LOCAL_DEVELOPMENT.md)
- [Minimal admin](docs/ADMIN_GUIDE.md) and [current data model](docs/DATA_MODEL.md)
- [Operations and Groq configuration](docs/OPERATIONS_RUNBOOK.md)
- [Backup/restore](docs/BACKUP_RESTORE.md) and [future migration/upgrade](docs/UPGRADE_ROLLBACK.md)
- [Deployment boundaries](docs/DEPLOYMENT_VPS.md) and [Nginx/SSL](docs/NGINX_SSL.md)
- [Next-phase design, not implementation](docs/CONTAINER_DESIGN.md)
- [Publication policy](docs/PUBLICATION_POLICY.md)

Runtime: Django 5.2, templates, Tailwind, Alpine, Unfold, SQLite; Redis exists only for shared fail-closed login counters. Development adds a frontend compiler/watch service. No Celery, broker, scheduler, upload pipeline or active business models. The three old app labels remain installed solely to run historical migrations and their retirement graph.

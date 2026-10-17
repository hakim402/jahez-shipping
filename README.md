# JAHEZ Shipping

English/Arabic shared-container tracking built with Django 5.2, Unfold, Tailwind, Alpine and SQLite. Administrators maintain a container journey, refresh carrier information, review the bilingual details and share one JAHEZ tracking code with everyone using that container.

Public pages show only the approved saved snapshot. They never call the carrier or Groq. Redis supplies shared login and lookup limits. Production runs **web + Redis**; local development also runs the frontend compiler.

## Start here

| Task | Guide |
|---|---|
| Run locally, update dependencies, test | [Local development](docs/LOCAL_DEVELOPMENT.md) |
| Pull updates on the VPS, rebuild Docker, migrate, restart, inspect logs | [Production](docs/DEPLOYMENT_VPS.md) |
| Register, refresh, correct, publish and archive a container | [Admin guide](docs/ADMIN_GUIDE.md) |
| Back up, verify recovery and roll back an update | [Backup and restore](docs/BACKUP_RESTORE.md) |
| Understand models, source dates and publication boundaries | [Data model](docs/DATA_MODEL.md) |
| Keep private files out of GitHub | [Publication policy](docs/PUBLICATION_POLICY.md) |

## Addresses

| | Local | Production |
|---|---|---|
| Website | http://localhost:18744/en/ | https://shipping.jahez.online/en/ |
| Arabic | http://localhost:18744/ar/ | https://shipping.jahez.online/ar/ |
| Admin | http://localhost:18744/en/admin/ | https://shipping.jahez.online/en/admin/ |
| Tracking lookup | http://localhost:18744/en/track/ | https://shipping.jahez.online/en/track/ |

Use the generated JAHEZ code for a public lookup. A B/L or physical container number is not a public access code. Administrators are created interactively; there is no default account/password.

## Repository layout

```text
apps/           Django application, integrations and historical migration shells
config/         Settings, URLs and WSGI
frontend/       Tailwind source
static/         Runtime images, fonts, CSS, JavaScript and licenses
templates/      Public and administrator templates
locale/         Arabic translations
deploy/         Gunicorn, proxy, logging and optional scheduler templates
scripts/        Environment setup, maintenance and release verification
tests/          Synthetic application, migration and recovery tests
docs/           The six maintained guides above
private/        Ignored operational records, recovery material and local history
```

`apps/ai`, `apps/shipments` and `apps/tracking` contain migration compatibility code, not active business features. Keep their original migrations: Django still needs the historical graph. Dependency lockfiles, migration/recovery tests and third-party licenses are also required project files.

Actual `.env` files, SQLite files, uploads, backups, deployment keys and local history stay outside Git and Docker build contexts. Named Docker volumes preserve application data across code updates. Routine updates apply migrations; the one-time fresh-database reset is not an update procedure.

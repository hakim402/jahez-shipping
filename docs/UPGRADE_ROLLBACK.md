# Future destructive transition — owner review only

**Do not execute against persistent owner data during this cleanup.** The commands below describe a later separately approved maintenance window. The tested supported starting point is the complete 0.8.1 schema. Preserve that source commit and immutable image. Never use `--fake`, delete migration metadata, delete volumes/uploads or reverse migrations to pretend recovery.

## 1. Before changing the old checkout or image

In the actual Shipping checkout, confirm `.env.prod` and the `jahez-shipping-prod` project. Inspect the exact volume and record the running immutable old image ID privately:

```bash
docker volume inspect --format '{{.Name}}' jahez-shipping-prod_shipping_data
docker inspect --format '{{.Image}}' jahez-shipping-prod-web-1
read -r -p 'Verified old 0.8.1 immutable image SHA: ' shipping_old_image
python3 scripts/release.py pause --confirm-production
python3 scripts/release.py backup --confirm-production
```

The last two commands must use the **old 0.8.1 checkout/helper and old four-service Compose**. They pause web/worker/Beat, retain a Shipping maintenance marker, and back up database/private files with the old image. Stop external/one-off writers too. Do not substitute the reduced helper before the old workers have stopped. Verify the printed archive with the old image, no network and a read-only Shipping volume:

```bash
read -r -p 'Verified backup archive ID: ' shipping_archive
docker run --rm --network none --mount type=volume,src=jahez-shipping-prod_shipping_data,dst=/data,readonly \
  "$shipping_old_image" python scripts/backup.py --verify "/data/backups/$shipping_archive"
```

First rehearse an isolated restore using the old image's restore/verifier and a separate empty target, retaining the source archive; the cleanup verifier demonstrates this on synthetic data. Preserve the old checkout outside the incoming release, using a private source archive or separate approved checkout, and privately preserve the production env. Do not rotate Groq or Django secrets. A backup must match current rows/files exactly; writes after backup make the migration guard refuse.

## 2. Switch candidate code only after approval and verified recovery

Build the reviewed 0.9.0 release without starting it. Ensure stopped legacy worker/Beat containers cannot restart; remove only those confirmed stopped containers with the old scoped Compose `rm -f worker beat` (no volume deletion). Retain Redis/data volumes and old source/image. Privately set the explicit incoming `SHIPPING_IMAGE` in production env, leaving keys/models/secret unchanged. No broker variables are needed by the candidate.

```bash
python3 scripts/preflight.py --running
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml build web
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never \
  -e SHIPPING_ALLOW_SCHEMA_CLEANUP=true \
  -e SHIPPING_PRE_CLEANUP_ARCHIVE="/data/backups/$shipping_archive" \
  web python manage.py migrate --noinput
```

Populated installs refuse without that explicit flag, valid marker and matching verified old 0.8.1 archive. The guard checks database rows (including users/hashes/sessions/admin history) and private-file hashes against the archive before any retirement operation. Fresh empty installs can complete the same graph without data-loss flags. Migrations are dependency ordered and deliberately irreversible. Retired content types/permissions are removed; required Django auth permissions and normal admin logging remain. Private files are **not deleted**.

With writers still stopped, check migrations, deployment checks and authentication/public empty-state behavior, then resume only the new web service:

```bash
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python manage.py migrate --check
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python manage.py check --deploy --fail-level ERROR
python3 scripts/release.py resume --confirm-production
```

The helper requires no legacy worker/Beat containers and waits for reduced web health. Do not remove a maintenance marker to bypass a failure. HSTS/TLS, actual VPS resource/security/proxy configuration and owner acceptance need their own observed checks; no live change is authorized by this guide.

## 3. Recovery is matching old image plus database/files

A code-only rollback cannot recover dropped rows. Keep web and every legacy writer stopped. Preserve current failure-state data if possible, and obtain an explicit decision for any writes accepted after the backup. Stage a verified old archive outside `/data` in a dedicated private recovery mount; confirm the exact Shipping volume, never another app's volume. Run **the old immutable image's** restore helper:

```bash
# Inside the correctly scoped old-image one-off container:
python scripts/restore.py --backup /recovery/ARCHIVE_ID --target /data \
  --replace --confirm-target /data --quiesced
```

Use `--allow-damaged-target` only after deliberate inspection of a damaged target. The old helper retains previous data privately. Verify the restored database/files with matching old source/image before resuming old web/worker/Beat. Never invoke 0.9.0 recovery against old archives or call empty reverse-created tables a successful rollback. The isolated cleanup test restores the actual synthetic old archive and confirms the original admin, legacy rows and private file, not merely schema presence.

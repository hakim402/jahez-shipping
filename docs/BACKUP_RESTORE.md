# Backup, restore and rollback

A backup belongs to a matching application version, schema, private-file set and recoverable image/source. A Git commit alone cannot recover deleted records. Keep private backup archives, environment files and recovery images out of GitHub and public downloads.

## Take a production backup

From the Shipping checkout on the VPS:

```bash
sudo python3 scripts/manage_backup.py --confirm-production
```

This pauses only Shipping web, takes and verifies a SQLite/private-file backup, and resumes web after migration/health checks. Redis stays running. If it fails, preserve the maintenance state and inspect the error before resuming. The wrapper is for the current two-service runtime; old worker/Beat installations are refused.

Archives are stored in `/data/backups/ARCHIVE_ID` inside the Shipping data volume, with private directories/files. The printed ID identifies the recovery point. Verification checks SQLite integrity, foreign keys, all table counts, schema/migrations, exact file hashes and the complete private-file set. Current archives use format 2/app 0.9.0. They include accounts/sessions and published snapshots, so they remain confidential.

Keep administrator edits and any installed daily refresh paused for a maintenance window. Record the image ID/source commit with the backup; retain that image before rebuilding a mutable tag. The [production update sequence](DEPLOYMENT_VPS.md#routine-update-after-pushing-local-code) shows the image-retention command. Keep `.env.prod` separately protected without printing its values.

## Verify an archive

Replace `ARCHIVE_ID` with the actual printed ID:

```bash
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps web python scripts/backup.py --verify /data/backups/ARCHIVE_ID
```

The selected image must match the archive's version/schema. Old format-1/0.8.1 archives require the retained old image/source and its verifier. Current code deliberately refuses incompatible archives. Preserve historical migrations and their recovery tests.

## Prove an isolated restore

Choose a new, unused restore directory in the Shipping volume. These commands restore into that separate directory, leaving the active database in place:

```bash
TARGET="/data/restore-review-$(date -u +%Y%m%dT%H%M%SZ)"
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps web python scripts/restore.py --backup /data/backups/ARCHIVE_ID --target "$TARGET"
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps web python scripts/verify_restore.py /data/backups/ARCHIVE_ID "$TARGET"
```

Run with the matching image. The verifier compares exact restored SQLite bytes and all private-file sizes/hashes before Django opens the restored database, then checks table counts/migrations and bilingual pages with providers disabled. A cold restore must be verified before writers alter it. Retain or remove only that explicit disposable review directory after inspection; it is not the live `/data/private` directory or a backup archive.

## Recover the active installation

A restore discards writes after the chosen backup. Confirm the recovery point and preserve the current failure-state database/files first. Pause web and any refresh schedule, verify no other writer is using the Shipping volume, select the matching image/source and verify an isolated restore before replacing active storage.

The restore CLI requires `--replace --confirm-target /data --quiesced` for an existing target plus a valid Shipping maintenance marker. Mount the verified archive separately at `/recovery`; an archive inside the target hierarchy is refused. It retains previous target files in a `.pre-restore-...` directory. Replacing damaged storage additionally requires `--allow-damaged-target`; it is never automatic. Exact host mounts/image/paths must be selected for the actual recovery case, not copied from a historical reset script.

For a failed migration, an older image alone cannot use an incompatible new schema. Recover the matching database/private files, configuration and image together, then verify migrations, internal readiness, administrator access and public results before allowing writes. Reverse migrations and `git checkout` do not restore deleted data.

## Off-server protection and retention

The volume-local archive protects against an application mistake, not loss of the VPS. Choose an owner-controlled off-server destination, encrypt before transfer, restrict access and set an explicit retention/failure-monitoring policy. Retrieve a copy from that destination and repeat the matching-image isolated restore, including actual private-file hashes. A successful upload or metadata listing is not a restore test.

No off-server destination or scheduled backup has been configured by the code. The carrier-refresh timer does not back up the database. Retention pruning is explicit: verify the correct recovery points and retrieved-copy restore before removing older archives, images or private files. Docker volume deletion/global pruning is not routine project cleanup.

# Shipping backup and restore

Phase 7 provides a tested local procedure. No production backup schedule or off-server destination is active. Archives contain confidential databases, password hashes, customer records and private files. Keep them outside Git/image contexts; restrict access and encrypt off-server storage/transfers. Never send archives or keys in chat.

## Matching recovery point

From this project's directory, with the development image already built:

```bash
python3 scripts/manage_backup.py --environment dev
# Before upgrading code/schema:
python3 scripts/manage_backup.py --environment dev --label pre-upgrade
# Explicit retention purge; default retention is 14 days, accepted range 1–365:
python3 scripts/manage_backup.py --environment dev --prune --retention-days 14
```

The wrapper uses exactly `jahez-shipping-dev`, `.env.dev`, and `compose.dev.yml`. It creates a private ownership marker at `/data/maintenance.lock`; application requests return bilingual 503 (health/static excluded) and workers stop claiming/reconciling. It stops web/worker/Beat with a 95-second grace period, then verifies no running containers carry this project's writer service labels. Redis remains running. Stop any external/manual database writers too: the marker cannot police a raw SQLite client. No volumes are deleted.

A one-off container uses SQLite's online backup API, including committed WAL content, then copies the complete private-file tree while writers are paused. It checks database integrity/foreign keys, applied migrations, schema fingerprint, application table counts, every document's recorded size/checksum, and archive file hashes. A private manifest records app version, time, label and hashes. Only a fully verified staging directory is renamed to a timestamp/UUID archive under `/data/backups`. All archive directories are 0700 and files 0600. Incomplete evidence is retained privately with `.incomplete-` prefix and is never a recovery point. The wrapper removes only its own marker and resumes Shipping. Review readiness/worker health afterward; failure is reported honestly.

Manual `backup.py --quiesced` additionally requires a valid Shipping marker, but the flag is an operator assertion, not independent proof that writers stopped. Prefer the wrapper.

## Verify and restore in isolation first

Use the actual archive ID printed by your backup; the IDs below are placeholders. List names locally without sharing manifests:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python -c "from pathlib import Path; print('\n'.join(p.name for p in Path('/data/backups').iterdir() if not p.name.startswith('.')))"
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/backup.py --verify /data/backups/ARCHIVE_ID
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/restore.py --backup /data/backups/ARCHIVE_ID --target /data/restore-review-UNIQUE_ID
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_restore.py /data/backups/ARCHIVE_ID /data/restore-review-UNIQUE_ID
```

Choose a fresh empty directory; never use `/data` for an isolated restore. The CLI shows the absolute target before any changes. Paths through symlinks, protected sibling projects or application code are refused. No archive extraction occurs. Version/file-set/hash/schema/document failures abort before installing. The isolated verifier disables both providers, selects production settings on that separate database, checks every application table count/private file hash/migration, renders EN/AR public pages and confirms DEMO lookup stays suppressed. No worker starts against the restored directory. The recovery point is private data on the local Docker volume, not a downloadable public file.

## Replacing existing data: deliberate operator action only

No live replacement was performed in Phase 7. A restore discards writes made after its snapshot from the active database; the old files are retained for rollback but those writes are not merged. Stop all Shipping writers and verify the exact volume/directory, take a fresh pre-restore backup, preserve the original archive outside the target hierarchy, and use the same app version as the archive. The helper requires all three flags:

```bash
# Inside an appropriately scoped one-off container with no running writers:
python scripts/restore.py --backup /recovery/ARCHIVE_ID --target /data \
  --replace --confirm-target /data --quiesced
```

An existing nonempty target must have a valid nonsymlink `/data/maintenance.lock` with `{"project":"jahez-shipping"}` and a valid Shipping database/private tree. To deliberately recover a damaged DB/document mapping, additionally supply `--allow-damaged-target`; ordinary replacement refuses a damaged target. This flag still requires a regular existing database, a private tree without symlinks, exact target confirmation and paused writers, and retains the damaged original verbatim. The archive cannot be beneath the replacement target: mount a verified copy separately at `/recovery`. A wrong/missing absolute confirmation refuses replacement. The previous DB, WAL, SHM and private tree are retained in `.pre-restore-UUID`. Installation failure restores moved originals and leaves staging/marker for inspection. Keep writers paused until validation succeeds. CLI replacement rollback and damaged-target recovery were tested only on disposable directories. Never automatically remove rollback evidence or a maintenance marker whose ownership is uncertain.

Code rollback alone does not reverse schema changes. Restore the matching code/image and database/files together if migration compatibility is unknown. Migrate once with workers stopped only after a verified pre-upgrade point. Reconcile private jobs afterward; do not replay outbound AI/provider actions blindly. Validate staff permissions, public summaries and an authorized private download before reopening.

## Daily retention and off-server protection

The retention option is explicit; only complete compatible-version archives that verify and are older than the chosen days are deleted. Invalid, incomplete and other-version evidence is preserved for manual investigation. The test suite verifies this on disposable archives. No real local archive was pruned.

For later server activation, a daily scheduler should run the production wrapper from the correct checkout with `--environment prod --confirm-production --prune --retention-days 14`, capture its exit status, verify recovery points and alert on failure/disk shortage. Schedule during an agreed maintenance window. Production scheduling/monitoring is Phase 9 work; no cron entry was installed here.

`--export-dir /backup-export` supports a separately mounted, private configured destination. Mount an operator-approved directory only on the backup one-off container, restrict its permissions, and configure encrypted/authenticated transfer to an external host or object store. The helper copies the complete archive, sets 0700/0600, and re-verifies it. It makes no SSH/API requests and cannot prove the mount is off-server or encrypted. A second directory or Docker volume on the same host does not protect against host loss. No destination, remote credentials or upload was configured/tested in this phase. Before claiming protection, verify a remote copy can be retrieved and restored into a separate environment, record the result and agree retention/deletion policy with the owner.

## Observed Phase 7 result

Local synthetic recovery tests do not replace a production disaster-recovery drill or establish capacity at higher write volume. Record production archive identifiers, restored counts and recovery evidence privately.

## Phase 8 versioned releases

Archives require their exact recorded app version. The retained Phase 7 local archives are 0.7.0; use its retained image to verify/restore them, not current 0.8.0 source. Old image verification can run offline with the Shipping data volume mounted read-only. New backups use 0.8.0. Never rebuild an old version tag from new source. Production paused upgrades, unchanged-schema rollback checks, private external staging and exact replacement commands are in [UPGRADE_ROLLBACK.md](UPGRADE_ROLLBACK.md); server activation/scheduling stays Phase 9.

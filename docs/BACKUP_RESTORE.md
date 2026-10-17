# Matching database and private-file recovery

A code commit is not a database backup. Local release acceptance uses only disposable synthetic databases/private files; owner data, volumes and existing archives remain unchanged. Real destructive application requires a verified **old 0.8.1** backup and its immutable source/image. See [exact transition commands](UPGRADE_ROLLBACK.md). Reversing migrations cannot recover deleted rows.

The reduced recovery helper uses SQLite online backup and a quiesced complete private-file copy. It verifies integrity/foreign keys, all table counts, applied migrations/schema and file hashes. Restore additionally compares the exact staged and installed SQLite file size/SHA-256, plus private-file sets/sizes/SHA-256, against the verified archive before reporting success. A valid SQLite row change with unchanged counts/schema must fail too. Container/Event rows, approved snapshots, auth/session rows and retained private bytes belong to the same recovery point. New archives use format 2 / app 0.9.0 and contain auth hashes/sessions; they remain confidential, with directories 0700 and files 0600. It refuses legacy business schemas: verify/restore old format-1 archives with their matching old image instead. Archive version/hash/file-set mismatch, symlinks and protected/code paths are refused.

For a later approved reduced-runtime maintenance window:

```bash
python3 scripts/manage_backup.py --confirm-production
```

This pauses only the reduced web service, backs up and resumes on success. A failure keeps web paused and retains the maintenance marker. It refuses installations with legacy worker/Beat containers, which need the transition sequence. Redis stays up. No backup scheduler is installed; the separate carrier-refresh timer package remains inactive. Manual `backup.py --quiesced` requires a Shipping marker but cannot independently prove writers stopped; operators must stop raw SQLite/one-off writers too.

Inside an appropriately scoped one-off container, using the matching archive version and an actual archive ID:

```bash
python scripts/backup.py --verify /data/backups/ARCHIVE_ID
python scripts/restore.py --backup /data/backups/ARCHIVE_ID --target /data/restore-review-UNIQUE_ID
python scripts/verify_restore.py /data/backups/ARCHIVE_ID /data/restore-review-UNIQUE_ID
```

Choose a fresh empty isolated target. No worker or provider starts against it. Before any restored writer starts, the verifier checks all table counts/schema/migrations, exact restored SQLite bytes, the exact private-file set/sizes/checksums and bilingual pages. Keep the isolated target cold until verification; later application writes are not the original recovery point. Missing, additional, corrupted or symlinked private files fail verification even if database counts still match. For deliberate existing-target replacement, the helper additionally requires `--replace --confirm-target /data --quiesced`, a valid Shipping maintenance marker and a verified archive **outside** the target hierarchy, mounted separately at `/recovery`. It retains previous DB/WAL/SHM/private files in `.pre-restore-UUID`; failed installation retains evidence and restores moved originals. Damaged-target recovery additionally requires `--allow-damaged-target`; it is not automatic.

A restore discards writes after the chosen snapshot. Obtain an explicit recovery decision for those writes; keep writers stopped and preserve failure-state evidence. Configure encrypted off-server access/transfer, retention, failure monitoring and retrieved-copy restore in a later approved operational step. No remote destination, credentials, transfer, purge or schedule is configured by this cleanup.

The release verifier `python3 scripts/verify_release.py` rehearses matching 0.9.0 backup/isolated restore using synthetic container/event rows, public snapshots and private bytes. It compares every original table row and actual hashes, rejects valid-database row changes and same-length private corruption through the CLI, and proves a corrupted staged copy cannot replace the original target. This local rehearsal does not establish an off-server copy, production recovery or host-loss protection.

If a recorded old image is missing, do not assume another tag is equivalent. A recovery image may be reconstructed only from verified retained source and lockfiles, under a separate tag. Record its new immutable identity and verify a copied retained archive in isolation, including actual recovered rows/private hashes, before treating it as a recovery option. Preserve a private image export and checksum. A successful synthetic rehearsal does not establish compatibility with an uninspected production archive or reproduce the missing original image bytes.

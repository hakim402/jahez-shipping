# Matching database and private-file recovery

A code commit is not a database backup. No owner database, private upload, volume or existing archive is changed in this cleanup. Real destructive application requires a verified **old 0.8.1** backup and its immutable source/image. See [exact transition commands](UPGRADE_ROLLBACK.md). Reversing migrations cannot recover deleted rows.

The reduced recovery helper uses SQLite online backup and a quiesced complete private-file copy. It verifies integrity/foreign keys, all table counts, applied migrations/schema and file hashes. New archives use format 2 / app 0.9.0 and contain auth hashes/sessions; they remain confidential, with directories 0700 and files 0600. It refuses legacy business schemas: verify/restore old format-1 archives with their matching old image instead. Archive version/hash/file-set mismatch, symlinks and protected/code paths are refused.

For a later approved reduced-runtime maintenance window:

```bash
python3 scripts/manage_backup.py --confirm-production
```

This pauses only the reduced web service, backs up and resumes on success. A failure keeps web paused and retains the maintenance marker. It refuses installations with legacy worker/Beat containers, which need the transition sequence. Redis stays up. No scheduler is installed. Manual `backup.py --quiesced` requires a Shipping marker but cannot independently prove writers stopped; operators must stop raw SQLite/one-off writers too.

Inside an appropriately scoped one-off container, using the matching archive version and an actual archive ID:

```bash
python scripts/backup.py --verify /data/backups/ARCHIVE_ID
python scripts/restore.py --backup /data/backups/ARCHIVE_ID --target /data/restore-review-UNIQUE_ID
python scripts/verify_restore.py /data/backups/ARCHIVE_ID /data/restore-review-UNIQUE_ID
```

Choose a fresh empty isolated target. No worker or provider starts against it. The verifier checks all table counts/schema/migrations and bilingual pages. For deliberate existing-target replacement, the helper additionally requires `--replace --confirm-target /data --quiesced`, a valid Shipping maintenance marker and a verified archive **outside** the target hierarchy, mounted separately at `/recovery`. It retains previous DB/WAL/SHM/private files in `.pre-restore-UUID`; failed installation retains evidence and restores moved originals. Damaged-target recovery additionally requires `--allow-damaged-target`; it is not automatic.

A restore discards writes after the chosen snapshot. Obtain an explicit recovery decision for those writes; keep writers stopped and preserve failure-state evidence. Configure encrypted off-server access/transfer, retention, failure monitoring and retrieved-copy restore in a later approved operational step. No remote destination, credentials, transfer, purge or schedule is configured by this cleanup.

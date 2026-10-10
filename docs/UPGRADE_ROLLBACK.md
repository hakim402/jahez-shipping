# Shipping upgrade and rollback — Phase 8

These are future **Phase 9/operator** actions on the independent Shipping checkout. No production upgrade or data replacement ran during Phase 8. Run each step separately, stop on failure, and retain private evidence. Never delete volumes, run Docker-wide prune/down, change the other apps or blindly reverse migrations. Take a matching database/private-file recovery point before changing the checkout or image configuration.

## 1. Prepare while the current release still runs

From `/opt/jahez-shipping`, inspect `git status --short`, current commit, `python3 scripts/release.py status`, disk headroom and the intended release's migrations. Obtain the approved new commit privately; this phase published no remote release. Preserve the current image locally and the existing private environment outside Git. Do not rotate its secret. Verify backup retention/off-server retrieval and agree a short Shipping maintenance window. Old code must remain available as an immutable image SHA.

```bash
cd /opt/jahez-shipping
python3 scripts/preflight.py --running
python3 scripts/release.py pause --confirm-production
python3 scripts/release.py backup --confirm-production
```

Pause records the **running web image SHA and original schema fingerprint** in a private `/data/maintenance.lock`, then stops only Shipping web/worker/Beat with 95 seconds of grace. It verifies their project/service labels have no active writers; Redis stays up. Stop any manually launched/raw SQLite writers too. The backup command runs the **still-configured old image**, not the incoming release; note its printed archive ID privately. Failed steps keep the marker/writers paused. No real reference or manifest content is printed.

## 2. Verify the old-version recovery point before switching

```bash
read -r -p 'Backup archive ID just printed: ' shipping_archive
read -r -p 'Running old image SHA recorded for this release: ' shipping_old_image
docker run --rm --network none \
  --mount type=volume,src=jahez-shipping-prod_shipping_data,dst=/data,readonly \
  "$shipping_old_image" python scripts/backup.py --verify "/data/backups/$shipping_archive"
```

Use the actual `sha256:...` image ID from the private release marker or read-only `docker inspect --format '{{.Image}}'` on the stopped Shipping web container. Archive verification deliberately requires its exact application version; a 0.7 archive cannot be verified/restored by 0.8 code. Keep old images through the retention window. This offline command has no env/provider/network or write mount. Do not use `latest` or rebuild an old tag from new source.

## 3. Switch, build and migrate with writers paused

```bash
read -r -p 'Approved new Shipping commit/tag: ' shipping_release
git checkout --detach "$shipping_release"
# Privately edit only SHIPPING_IMAGE to the new explicit version in .env.prod.
python3 scripts/preflight.py --running
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml build web
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python -m pip check
python3 scripts/release.py migrate --confirm-production
```

Build before migration; source/manifest assets are baked into the image. Migrations execute once in a one-off container, followed by deployment system checks. They never run automatically in web/worker/Beat. Schema compatibility is a release-specific decision; a successful migration is not proof old code remains compatible. If validation succeeds:

```bash
python3 scripts/release.py resume --confirm-production
python3 scripts/preflight.py --running
curl -fsS -H 'Host: shipping.jahez.online' http://127.0.0.1:18743/health/ready/
curl -fsS -o /dev/null https://shipping.jahez.online/en/
curl -fsS -o /dev/null https://shipping.jahez.online/ar/
```

Resume checks unapplied migrations, starts web and waits for readiness, then starts exactly one worker/Beat and waits for their health. If startup fails, it reinstates the release marker and stops writers. It refuses the original image if the schema fingerprint differs. Review admin login/CSRF/roles, an authorized private download, a reviewed public result and integration/job health. Do not send new provider actions just to prove a deployment. Record image SHA/commit, health, private backup ID and any remaining limitations. Confirm the existing websites still respond.

## 4. Roll back code only when the schema is unchanged

While the release marker exists and all writers remain paused:

```bash
python3 scripts/release.py rollback-check --confirm-production
```

This compares current SQLite schema to the original fingerprint and prints only the recorded old image SHA. If it passes, privately set `SHIPPING_IMAGE` in `.env.prod` to that SHA and run `resume` using this Phase 8 release helper. The old code/static assets are inside the immutable old image; retain this host release tooling until rollback checks complete. Do **not** build using a SHA as a new tag. The unchanged-schema path was tested on synthetic data; a changed schema was deliberately tested to refuse rollback.

If a failed release has already resumed, first pause it again. That new marker describes the currently running release, not the previous release; preserve and inspect `/data/last-release.json` and the prior deployment record. Do not treat a new pause's schema as proof of compatibility with older code. Obtain the prior original schema/image from the retained record, review migrations and any accepted writes, then choose an explicit matching recovery point. Never discard post-backup writes without the owner's concrete recovery decision.

## 5. Matching database/files restore after a schema-changing failure

Keep writers paused. Restoring loses active writes after the chosen snapshot; document that point and obtain the owner's decision if such writes exist. Preserve a fresh failure-state recovery point using its own app version where possible. A damaged dataset requires the narrowly documented `--allow-damaged-target` choice, not automatic deletion. Use the archive's old immutable image and matching code.

The archive cannot be underneath a replacement target. Export a verified copy to **only Shipping's** private host directory; this is local staging, not off-server protection:

```bash
sudo install -d -m 0700 -o 10001 -g 10001 /srv/jahez-shipping-recovery
docker run --rm --network none \
  --mount type=volume,src=jahez-shipping-prod_shipping_data,dst=/data,readonly \
  --mount type=bind,src=/srv/jahez-shipping-recovery,dst=/recovery \
  -e SHIPPING_ARCHIVE_ID="$shipping_archive" \
  "$shipping_old_image" python -c "import os,shutil; from pathlib import Path; from apps.core.recovery import verify,secure_tree; name=os.environ['SHIPPING_ARCHIVE_ID']; assert '/' not in name and '..' not in name; source=Path('/data/backups')/name; verify(source); target=Path('/recovery')/name; shutil.copytree(source,target); secure_tree(target); verify(target); print('Private staged recovery point verified')"
docker run --rm --network none \
  --mount type=volume,src=jahez-shipping-prod_shipping_data,dst=/data \
  --mount type=bind,src=/srv/jahez-shipping-recovery,dst=/recovery,readonly \
  "$shipping_old_image" python scripts/restore.py \
  --backup "/recovery/$shipping_archive" --target /data \
  --replace --confirm-target /data --quiesced
```

The exact target confirmation, existing Shipping marker, valid database/private mapping and old archive version are mandatory. The helper retains prior DB/WAL/SHM/private files in `.pre-restore-UUID`; installation failures restore moved originals and retain staging. A Docker volume mount can create a missing empty volume, so verify `docker volume inspect --format '{{.Name}}' jahez-shipping-prod_shipping_data` before either command and stop if absent. Do not alter these commands to point at another app.

Before live replacement, use a fresh `/recovery/review-UNIQUE_ID` isolated target with the writable recovery mount and run `scripts/verify_restore.py` against it under the old image. This disables providers, checks matching table counts/private hashes/migrations and bilingual pages. [Exact isolated commands and damaged-target constraints](BACKUP_RESTORE.md). After replacement, privately select the old image SHA, retain this host release helper, verify schema/migration consistency and `rollback-check` against the retained original release marker, then resume. If marker/image history is uncertain, remain paused and investigate; never unlink the marker to bypass the gate.

## Routine backup, export and failure handling

After launch, the production backup wrapper pauses and resumes the current Shipping release:

```bash
python3 scripts/manage_backup.py --environment prod --confirm-production --prune --retention-days 14
```

The wrapper is for routine backup, not a release pause: it resumes the same services even after backup failure and reports that failure. The release helper above intentionally leaves them paused. The retention purge only removes complete verified compatible-version archives past the cutoff; keep other-version evidence and its old image until deliberately reviewed. No schedule or real purge was configured locally.

For off-server protection, verify/export a complete archive to the private staging path above, then use the owner's chosen encrypted authenticated transfer/storage. Supply its destination privately during Phase 9; no destination or credentials are invented here. Protect staging/remote access and encryption keys, record successful retrieval, and restore the retrieved copy in isolation with its matching image before claiming host-loss recovery. Schedule a dedicated Shipping-only task during an agreed window, capture exit status, monitor disk and alert on failed backup/export/restore. A same-host mount is insufficient. [Backup and restore policy](BACKUP_RESTORE.md).

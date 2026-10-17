# Production: update and operate the VPS

Production is `jahez-shipping-prod`: web and Redis, with web bound only to `127.0.0.1:18743`. Existing Nginx serves https://shipping.jahez.online. Run commands in your normal VPS terminal from the Shipping checkout; use sudo there when Docker requires it. Credentials stay in `.env.prod` and at interactive terminal prompts.

## Routine update after pushing local code

On your development machine, review/test the changes, commit them and push:

```bash
git status --short
git add -p
python3 scripts/check_publication.py --index
git diff --cached --check
git commit -m "Describe the change"
git push origin main
```

Use `git add path/to/new-file` for any reviewed untracked files. On the VPS, keep administrator edits and any installed refresh schedule paused for the maintenance window. Save a matching backup and retain the old image before building over its tag:

```bash
cd ~/apps/jahez-shipping
sudo python3 scripts/manage_backup.py --confirm-production
sudo docker image tag "$(sudo docker inspect --format '{{.Image}}' jahez-shipping-prod-web-1)" "jahez-shipping:rollback-$(date -u +%Y%m%dT%H%M%SZ)"
git pull --ff-only origin main
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml build web
sudo python3 scripts/release.py pause --confirm-production
sudo python3 scripts/release.py migrate --confirm-production
sudo python3 scripts/release.py resume --confirm-production
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml ps
```

The sequence backs up the current version, pulls source, builds compiled assets, stops web for migrations and starts the updated web after its health check. Redis remains available. Continue each step only when the previous one succeeds. If migration/resume fails, web remains paused: use [recovery](BACKUP_RESTORE.md) rather than clearing the marker or starting an older image against the changed schema.

Routine updates retain SQLite, users, container records, private files and Docker volumes. No database deletion or fresh-reset command belongs in this workflow. The existing installation uses `SHIPPING_IMAGE=jahez-shipping:0.9.0`; for a versioned release change, update only that image setting to the intended release before its build, keeping other configuration intact. A restart alone cannot load changed code into an image without source mounts.

If the refresh timer is installed, stop its timer before maintenance and let an already-running bounded refresh finish. Restart that timer after web verification. Keep administrator writes paused from the backup until the update finishes; the recovery point represents the state when it was taken.

## Verify the update

Open the English/Arabic home, company, admin and tracking pages. Public health paths intentionally return 404 at Nginx. Check application readiness from the VPS:

```bash
curl --fail --silent --show-error -H 'Host: shipping.jahez.online' http://127.0.0.1:18743/health/ready/
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml logs --tail 50 web redis
```

Readiness checks migrations, database/session access, Redis and maintenance state. It does not contact the carrier or Groq. Confirm administrator login and a reviewed tracking result separately. Normal code updates do not require replacing Nginx, certificates, DNS or other applications.

## Change private settings or create an administrator

Edit `.env.prod` in your VPS terminal; preserve its independent Django secret, provider keys and contact/proxy values. Keep it mode 0600 with one assignment per name. China time is `Asia/Shanghai`; `Asia/Yiwu` is invalid. Source dates without a supplied zone remain unknown; the business timezone does not reinterpret them.

After changing environment settings, recreate web so it receives the new values:

```bash
chmod 600 .env.prod
sudo python3 scripts/preflight.py --running
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml up -d --wait --force-recreate web
```

Create an administrator only when needed, with your chosen credentials:

```bash
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml exec web python manage.py createsuperuser
```

## First installation on an empty VPS

Use this only for a new installation with empty Shipping storage. An existing installation follows the routine update above; historical 0.8.1 storage needs its separate matching recovery material before any destructive change.

Clone the repository into the intended Shipping checkout. Generate `.env.prod` once with `python3 scripts/init_prod_env.py`, then configure the private contact, proxy and optional Groq values. Existing environment files must be kept, not regenerated. Run `sudo python3 scripts/preflight.py` before first startup; it checks the free loopback port and service/storage contract without displaying secrets.

```bash
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml build web
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml up -d --wait redis
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps web python manage.py migrate --noinput
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps web python manage.py createsuperuser
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml up -d --wait web
```

The production image compiles CSS/JavaScript/translations and runs collectstatic during its build. Gunicorn serves the app; WhiteNoise serves collected static assets. No production frontend watcher, worker or Beat is required. Web is nonroot with a read-only root filesystem, one CPU, 128 processes and a default 768 MiB memory limit. Redis is private to the Compose network.

## Proxy, certificates and logs

The existing VPS proxy/TLS setup is retained during code updates. For a new host, inspect the host configuration and other sites before installing only Shipping's files:

| Repository template | Intended host destination |
|---|---|
| `deploy/nginx/jahez-shipping-http.conf` | Nginx `conf.d` inside `http` context |
| `deploy/nginx/jahez-shipping-proxy.conf` | Nginx `snippets` |
| `deploy/nginx/shipping-http.conf` | Shipping-only ACME/bootstrap site |
| `deploy/nginx/shipping-https.conf` | Shipping HTTPS site after real certificate files exist |
| `deploy/systemd/jahez-shipping-nginx-log.*` | Safe error-log socket/service |
| `deploy/nginx_error_log.py` | Root-owned log collector path referenced by that service |
| `deploy/logrotate/jahez-shipping` | Shipping log rotation |
| `deploy/certbot/jahez-shipping-reload` | Certbot deploy hook |

Templates use generic paths; adapt them to the actual host. Start the safe log collector before routing traffic. Verify domain/listeners, issue the Shipping certificate through the existing Certbot webroot setup, test `nginx -t` before reload, and check TLS/redirects/other-site continuity. Keep private/data/backups/health paths blocked publicly. Configure `SHIPPING_TRUSTED_PROXY_IPS` only for verified peer addresses; the proxy must overwrite client forwarding headers.

```bash
sudo nginx -t
sudo certbot certificates
sudo certbot renew --cert-name shipping.jahez.online --dry-run
```

The local `scripts/verify_nginx.py` checks template syntax with synthetic certificates; it does not test the live host. HSTS defaults to zero until HTTPS/renewal acceptance. Keep includeSubDomains/preload disabled for unrelated sites. Safe Shipping logs omit raw paths, query strings and contact/reference values.

## Refresh commands and optional daily schedule

An explicit refresh is administrator work. Public lookups never call providers. Preview eligible work without network requests or writes:

```bash
sudo docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml exec -T web python manage.py refresh_containers --active --dry-run
```

For a deliberately approved bounded run, replace `--dry-run` with `--limit 50 --max-seconds 900`. For one journey use `--container RECORD_ID --max-seconds 60`. The batch skips archived/completed records, shares a data-directory lock and never retries automatically. Failure preserves accepted data; inspect admin attention/last attempt/last success. Exit 0 is completed work, 1 needs attention, 2 is invalid/incomplete selection, and 75 is a busy/unavailable lock/database. Summaries contain counts, not references or credentials.

`deploy/systemd/jahez-shipping-refresh.service` and `.timer` are optional, currently prepared templates. Install only after the real one-shot/source/publication review succeeds. They are not enabled by Docker startup or routine code updates. The shipped calendar is **09:00 Asia/Kabul**, independent of the business display timezone; review the intended calendar before activation. To use China time, choose an explicit `Asia/Shanghai` calendar.

Before installation adapt all `/opt/jahez-shipping` paths to the actual checkout. If the checkout is under a home directory, `ProtectHome=read-only` is needed instead of `true`. Ensure image/env selection matches production. Validate both adapted unit files with `systemd-analyze verify` and the chosen calendar with `systemd-analyze calendar`. Then install the reviewed files mode 0644 under `/etc/systemd/system/` and inspect activation:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jahez-shipping-refresh.timer
systemctl list-timers --all jahez-shipping-refresh.timer
systemctl show jahez-shipping-refresh.service -p Result -p ExecMainStatus
sudo journalctl -u jahez-shipping-refresh.service --since today
```

`Persistent=true` may trigger one immediate catch-up run; enabling is a real provider action. A manual `systemctl start jahez-shipping-refresh.service` checks the service, not the first scheduled execution. Keep those acceptance results distinct. To pause future runs use `sudo systemctl stop jahez-shipping-refresh.timer`; stopping a timer does not cancel an already-running batch. Inspect staleness/failures in admin. [Backup and recovery](BACKUP_RESTORE.md) covers storage protection independently of refresh scheduling.

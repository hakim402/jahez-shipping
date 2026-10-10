# VPS deployment and release guide — 0.8.1

These commands are prepared for **Phase 9 after owner approval**. No server command, installation, firewall change, production environment or live deployment has been performed in Phase 8. Run only in this independent repository, expected `/opt/jahez-shipping`; keep the three existing applications intact. Record each check before advancing.

## 1. Read-only inventory on the actual host

Use your existing authorized SSH session; never send credentials or environment files in chat. Detect the OS/tooling before any install decision:

```bash
cat /etc/os-release
uname -m
command -v docker nginx certbot python3
docker version --format '{{.Server.Version}}'
docker compose version
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
sudo ss -H -ltn '( sport = :18743 )'
df -h /opt /var/lib/docker
free -h
sudo nginx -v
sudo nginx -T 2>/dev/null | rg '^\s*(user|include|listen|server_name|ssl_certificate\s)'
sudo ufw status verbose
systemctl list-timers --all --no-pager | rg 'certbot|snap.certbot'
certbot --version
```

If `rg` is unavailable use `grep -E` for these selected nonsecret directives; do not install it merely for inspection. Expected port output is empty. If occupied, identify the owner and stop preparation, not that application. Record Nginx's actual include layout and existing site names/statuses. Do not dump full Nginx configs, Docker environments or `.env` files. Check existing sites externally before/after each future reload.

The files below assume Ubuntu's `http` includes `/etc/nginx/conf.d/*.conf` and server includes `/etc/nginx/sites-enabled/*`, systemd, Python 3, and an existing healthy Nginx/Certbot. If the host differs, map the exact new Shipping files to its verified include locations; never replace nginx.conf/disable other sites. Docker Compose **2.24.4+** is required for the isolated review override; server commands also use `up --wait`. If prerequisites are missing, decide the OS-specific installation with the owner after inventory. Do not install competing Docker/Certbot copies or restart a shared Docker daemon casually.

Docker published ports can bypass UFW filtering, so protection relies on the actual **127.0.0.1:18743 binding** and no non-web host ports, not an assumed firewall rule. Do not reset firewall rules, disable Docker packet filtering, or close current SSH access. [Docker firewall reference](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

Default container memory ceilings total 2.75 GiB (web 768 MiB, worker 1536 MiB, Beat/Redis 256 MiB each). They are ceilings, not reservations; allow headroom for the existing apps/OS and PDF conversion. Inspect actual available RAM/disk before launch; adjust the documented `SHIPPING_*_MEMORY` values deliberately if required. SQLite stays one host, one Gunicorn worker/two threads, one Celery worker/concurrency 1, one Beat. More writers do not remove SQLite's constraint.

## 2. Independent checkout and stable private configuration

```bash
shipping_owner=$(id -un)
sudo install -d -m 0755 -o "$shipping_owner" -g "$(id -gn)" /opt/jahez-shipping
cd /opt/jahez-shipping
# Only for a new empty checkout; authenticate normally, never put a token in the URL:
git clone https://github.com/hakim402/jahez-shipping.git .
git checkout --detach v0.8.1
python3 scripts/init_prod_env.py
```

Use release `v0.8.1` and record `git rev-parse HEAD` in the server handover. Alternatively transfer this independent source tree with SSH/rsync, excluding actual private `.env`, `.env.dev`, `.env.prod` (keep `.env.dev.example` and `.env.prod.example`), data/private/backups/node_modules/staticfiles/.git unless intentionally transporting this repository's Git history; never transfer the protected sibling repositories as part of Shipping. Do not reuse or overwrite another project's checkout. Existing deployments must use [the paused upgrade procedure](UPGRADE_ROLLBACK.md); migration `shipments.0003` is required, and old images must not be resumed against the changed schema.

`init_prod_env.py` creates `.env.prod` exclusively with mode 0600, an independent random secret and integrations disabled; existing files are refused without rotation. Edit it privately on the host. Keep `DJANGO_SETTINGS_MODULE=config.settings.production`, explicit Shipping hostname/HTTPS origin, `/data`, dedicated Redis URLs, `SHIPPING_BIND_PORT=18743`, `SHIPPING_IMAGE=jahez-shipping:0.8.1`, business timezone and `SHIPPING_HSTS_SECONDS=0`. Do not source the file into a shell, share it, use dev secrets/default passwords or commit it. `SHIPPING_ENV_FILE` is reserved for isolated review; ordinary production uses `.env.prod`.

Optional keys/models may remain blank with flags false. When deliberately enabling Groq, configure both approved text/vision model IDs and private key; validate account access and request budgets privately, with a maximum of three images. When enabling 17TRACK supply its private key and deliberately register only an appropriate shipment/reference later. Startup validates enabled integrations' configuration but does **not** authenticate providers or prove model support/quota. Keep the stable secret/data paths across releases. Rotation is deliberate: take a backup, preserve the prior env privately and expect sessions/signatures to invalidate; never rotate by rerunning an init helper.

```bash
python3 scripts/preflight.py
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml build web
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python -m pip check
```

Preflight is read-only: checks private env permissions, required/insecure values, strict feature flags, pinned image reference, project/services/volumes/health/grace and free loopback port. It never prints secret values/resolved Compose environments. Do not use `docker compose config` without capture/redaction: it expands env secrets. Fresh build uses digest-pinned Python/Node/Redis; Python locked hashes and npm lock/ignore-scripts produce compiled local assets. Production runtime has no Node/watch/source bind mount/development server, uses UID 10001, a read-only root with bounded `/tmp`, dropped capabilities and no-new-privileges.

## 3. Initialize and migrate once, before workers

```bash
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml up -d --pull never --wait --wait-timeout 120 redis
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python -c "import os; from pathlib import Path; assert os.getuid()==10001; p=Path('/data/private'); p.mkdir(parents=True,exist_ok=True); assert os.access(p,os.W_OK); assert os.access('/beat',os.W_OK); print('Dedicated volume ownership/write access OK')"
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python manage.py migrate --noinput
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python manage.py setup_roles
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python manage.py check --deploy --fail-level ERROR
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml run --rm --no-deps --pull never web python manage.py createsuperuser
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml up -d --pull never --wait --wait-timeout 120 web
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml up -d --pull never --wait --wait-timeout 120 worker beat
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml ps
curl -fsS -H 'Host: shipping.jahez.online' http://127.0.0.1:18743/health/ready/
curl -I -H 'Host: shipping.jahez.online' http://127.0.0.1:18743/en/
```

Expected: migrations applied once, role definitions created with no automatic accounts/assignments, interactive strong unique admin password, healthy services, ready JSON, public HTTP redirect to HTTPS. `security.W004` is expected while HSTS is zero; other security failures require inspection. New named-volume copy-up inherits UID 10001 ownership/0700 paths from the image. Existing volumes are never wiped/recreated or recursively chowned blindly; an ownership failure requires inspection of that specific Shipping volume. Production names remain `jahez-shipping-prod_shipping_data`, `_redis_data`, `_beat_state`; do not change the project name/rename volumes across releases. DB and WAL/SHM share `/data`; Beat schedule state is independent. No service migrates automatically on startup. First migration needs only Redis running for these commands, not web/worker/Beat.

## 4. DNS, proxy, TLS and public smoke checks

Follow [NGINX_SSL.md](NGINX_SSL.md) exactly after recording the real host inventory. Activate an ACME-only HTTP bootstrap before issuance; app settings always remain HTTPS/secure-cookie. Never temporarily weaken Django HTTPS settings. Host Nginx proxies only the loopback port. At a direct edge it overwrites Host/forwarding headers; do not pass caller-supplied protocol/IP chains. Backend `SECURE_PROXY_SSL_HEADER` aligns with X-Forwarded-Proto. Trust only the observed proxy peer in `SHIPPING_TRUSTED_PROXY_IPS`; leave empty for a conservative proxy-wide application throttle until verified. Obtain the container peer from its own Shipping network/gateway and a controlled request; do not assume it is 127.0.0.1 inside Docker. No CDN real-IP trust is configured; a CDN requires owner-approved verified ranges and separate review.

After real TLS activation verify EN/AR/public/admin login+CSRF, proper assets, a real manual shipment/authorized private download, safe lookup, worker/Beat, and other hosted sites. Create real operational records manually; production refuses DEMO seeding/lookup and no development volume is reused. Live provider registration/webhook/Groq checks require the intended reference/source and consent, separately recorded; credential presence isn't verification.

## 5. Upgrade and rollback

Use [UPGRADE_ROLLBACK.md](UPGRADE_ROLLBACK.md). Take a matching pre-upgrade recovery point on the **old image before editing the image/env reference or checkout**. Pause only Shipping writers and keep the maintenance marker through migration. Build/pull new immutable/versioned image, migrate exactly once, check, then web followed by worker/Beat. Stable secret and named volumes remain. Failure keeps writers paused; a code rollback must match schema, and restoring DB/files can discard post-backup writes.

## 6. Ongoing commands and diagnostics

```bash
cd /opt/jahez-shipping
python3 scripts/preflight.py --running
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml ps
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml logs --tail 100 web worker beat
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml exec -T worker celery -A config inspect ping --timeout 5
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml exec -T redis redis-cli ping
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml exec -T web df -h /data /beat
docker compose --env-file .env.prod -p jahez-shipping-prod -f compose.prod.yml restart web worker beat
python3 scripts/manage_backup.py --environment prod --confirm-production --label pre-upgrade
```

Readiness checks DB/Redis/maintenance, not paid providers or all background tasks. Check worker/Beat separately. Logs are redacted/correlated and Docker rotates 10 MiB × 3; Nginx access log excludes URI/IP/referrer/user agent, and its private error collector retains only severity/time. Keep protected website services untouched. A safe shutdown is this exact Compose `down` with **no `-v`**; named volumes remain. Review [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) and [BACKUP_RESTORE.md](BACKUP_RESTORE.md) for privacy, retention, recovery and SQLite limits. Configure/verify daily backup scheduling and encrypted off-server retrieval/restore in Phase 9 before claiming protection; no schedule/destination is active now.

| Failure | Scoped next check |
|---|---|
| Port occupied / wrong app | Read ss/Docker port mappings; do not stop another app. |
| 502 | Web health, image/env startup failure, loopback route; check safe edge status and private collector severity. |
| Static 404 | Built/collected manifest, exact image, WhiteNoise proxy path, no stale bind mount. |
| Host/CSRF/login or redirect loop | Exact host/HTTPS origin, secure cookies, Nginx overwritten protocol, backend direct access; don't add wildcards. |
| DNS/IPv6/ACME failure | Resolve A/AAAA against actual host, challenge file externally, port 80 reachability, correct webroot/vhost. |
| Permission / readonly failure | UID 10001 and correct dedicated data/Beat volumes; conversion temp is `/tmp`; no source write required. |
| SQLite locks | One Beat/concurrency, long transactions, disk/capacity; [PostgreSQL plan](POSTGRES_MIGRATION.md). |
| Pending jobs / Redis | Dedicated Redis/AOF/worker/Beat; durable reconciliation, lease/error status; no blind provider replay. |
| Env/feature flags | Preflight field-name diagnostics, enabled keys/models privately, stable secret. |
| Webhook signature / quota | Restricted safe integration diagnostics; private signature/key configuration, proper exact reference, deliberate retry. |
| Groq model / scan limit | Supported chosen model/access/JSON mode/token budget and at most three images; manual operations stay available. |
| Maintenance / upgrade failure | Keep marker and writers paused; follow rollback checks; never erase flag solely to make health green. |

## Deployment acceptance record (not yet completed)

- [ ] Actual Ubuntu/tool/version/include/firewall/RAM/disk inventory recorded; existing sites healthy.
- [ ] Host port 18743 unused then verified loopback-only; no Redis/worker/Beat host ports.
- [ ] Independent checkout/approved commit, stable private production env, one-off migrations/admin/roles, healthy services.
- [ ] Real DNS/ACME/TLS/redirect/admin-CSRF/assets/private-download/public tracking checked; other sites healthy after reload.
- [ ] Provider tests separately classified; real references/sources not invented.
- [ ] Renewal schedule/hook/domain-specific dry-run, backup schedule/off-server restore and monitoring verified.
- [ ] Version/URLs/operators/known limits recorded in Phase 9 handover.

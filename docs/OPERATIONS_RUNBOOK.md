# Shipping operations — Phase 7 local verification

Run from the independent `jahez-shipping` directory. These development commands target only `.env.dev`, `compose.dev.yml`, and `jahez-shipping-dev`. Production server/proxy/TLS instructions remain Phase 8; no deployment has occurred.

## Status, safe diagnostics and restart

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml ps
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml logs --tail 100 web worker beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T redis redis-cli ping
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T worker celery -A config inspect ping --timeout 5
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml restart web worker beat
```

Check `http://localhost:18744/health/live/` and `/health/ready/` after changes. Liveness is process-only; readiness checks local database, Redis and maintenance state, never Groq/17TRACK. Worker and Beat have separate health checks; readiness alone does not establish their health. Keep one worker/concurrency 1 and one Beat. Never run unscoped `docker stop`, `docker system prune`, `down -v`, a second Beat, or migrations in every service's startup. The public port is loopback-only; Redis has no host port. Protected website/brand services are outside these commands.

Request responses carry random `X-Request-ID`, including throttles/CSRF/error/maintenance responses. Ordinary application logs allowlist JSON event/level/method/coarse route/status/duration/correlation, not messages, raw URLs, usernames/IPs, arguments, exception details, SQL, source text, file names or keys. Django request/security/SQL and SDK HTTP logs are silent; Celery root hijacking is disabled and fallback/root logs use the same safe formatter. Gunicorn access logging is disabled; its error logger redacts details. Docker rotates each service at 10 MiB × 3. Correlation helps identify a failing route/status; generic logs deliberately cannot diagnose raw provider payloads. Inspect restricted integration/AI health and safe error codes through authorized admin instead. Development `DEBUG=True` trace pages are for loopback development only; production generic pages are tested with `DEBUG=False`. Proxy/access logs are future Phase 8 configuration and not covered by application log redaction.

## Client identity and headers

Limits are public lookup 30/5 minutes and login 10/5 minutes, keyed by hashed client address in shared Redis cache, independent of reference/password. Cache failure refuses lookups/login safely with 503. An arbitrary `X-Forwarded-For` is ignored. `SHIPPING_TRUSTED_PROXY_IPS` is empty by default; only exact peer IP literals may supply one valid `X-Real-IP`. An approved edge must overwrite client forwarding headers and prevent untrusted direct access. Until the peer path is verified, requests through a proxy share a conservative proxy-wide limit. Phase 8 must verify host/proxy/HTTPS forwarding before configuring trust.

HTML responses have a same-origin CSP with object loading/framing blocked. Inline scripts/styles and JavaScript evaluation remain allowed because Unfold/Alpine currently require them; this is not a nonce-based strict CSP. Fonts/scripts are locally served. Error/admin/health/webhook and POST responses are no-store/noindex; private downloads preserve their stronger sandbox CSP and private/no-store headers. Maintenance responses also retain nosniff/frame/referrer protections. Production host/origin validation, HTTPS redirect and secure cookies are enabled. HSTS remains intentionally zero until Phase 9 verifies real TLS (the single expected deployment-check warning `security.W004`).

## Durable jobs and outages

Accepted webhook receipts/AI requests commit to SQLite before queue publication. Broker failure leaves pending work; one-minute Beat reconciliation recovers eligible work. Worker claims use 120-second leases/random fences, at most three attempts, bounded retry delays and permission/source rechecks. Tasks have 60/90-second soft/hard time limits. A stopped Redis makes readiness/login/lookup fail closed but public GET/manual local records persist. Restart this project's Redis and worker/Beat, then inspect private queue health; do not reset receipts or enqueue provider requests indiscriminately.

Real Phase 7 Redis stop/restart was observed with two new synthetic jobs; the actual failed broker publication retained both in SQLite, resumed workers processed both once, and repeated task calls were no-ops. The marker at `/data/phase07-redis-recovery.json` is private and single-use. `scripts/verify_quality_recovery.py` is a development review tool, not a production replay tool. Previous phase markers/reviews are retained; do not delete them to force a pass. Redis AOF is retained and helps accepted queue work, but durable database reconciliation is still required. This test was a controlled stop/restart, not host power-loss/AOF corruption simulation.

## Backup, maintenance and upgrade ordering

Use [matching backup/restore procedure](BACKUP_RESTORE.md). `maintenance.lock` gates application requests and job claims/reconciliation, but the actual writer stop is mandatory before snapshot or migration. A process already running can finish during shutdown; 95-second wrapper grace exceeds the 90-second task hard limit. External raw database writers must also be stopped.

For an approved future upgrade: record current image/code/schema, take verified pre-upgrade matching backup, stop web/worker/Beat, maintain the flag, build/pull the intended version, run migrations once in a scoped one-off process, check migration/system state and private integrity, remove only the owned maintenance flag, start web and then worker/Beat, and verify health/permissions/public lookup/download. A failed migration must keep writers paused; inspect whether rollback code is schema-compatible. Restoration can discard later writes and requires exact target confirmation. Do not automatically reverse migrations or remove the flag on an uncertain upgrade.

## Disk, files and retention

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web df -h /data /beat
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python -c "from pathlib import Path; print('data bytes',sum(p.stat().st_size for p in Path('/data').rglob('*') if p.is_file() and not p.is_symlink()))"
```

New private uploads are 0600 with 0700 created directories; private download requires explicit permission and is audited. Existing historical file permissions were not mass changed in this phase. Only PDF/PNG/JPEG up to 5 MiB, inspected content/mime and bounded page/resources are accepted; downloads are attachment/no-store/sandboxed and no public media route exists. AI processing is limited to five document pages, with scans additionally limited to the configured model's at most three images per request. Split larger scans intentionally before requesting external processing.

AI draft contents are erased when the configured retention ends (default 30 days): source/output/accepted changes cleared, state expired, lease cleared; decision identity/time and audit metadata remain. Assistant scope/result/output similarly expire. Original uploaded documents, operational records, carrier receipt normalized sources and audits are retained; shipments soft-archive, operational admins cannot hard-delete them. No automatic business-document/audit purge policy is active. Backups retain any earlier snapshot data until deliberately expired, independently of live AI expiry. Owner retention rules and encrypted off-server backup/schedule activation remain handover items.

## Common local failure checks

| Symptom | App-scoped next check |
|---|---|
| Port busy | Confirm Shipping's loopback 18744 binding and the actual occupant; do not stop an unrelated service. |
| Site unavailable | Check web health/restart state, readiness and maintenance marker ownership. Do not erase a marker blindly. |
| Static/icon problems | Verify frontend build and image collectstatic manifest; test static resolution in the production image. |
| Login/lookup 503 | Check dedicated Redis and cache configuration; throttling fails closed. |
| CSRF/host failure | Check exact origins/host/secure cookies and eventual trusted proxy forwarding; no broad wildcards. |
| SQLite locks | Check one Beat/concurrency, long transactions/disk and writer volume; use [migration signals](POSTGRES_MIGRATION.md). |
| Pending AI/carrier work | Check worker/Beat health, leases, safe error, configuration and source/permission changes before intentional retry. |
| Webhook 401 | Check signature configuration privately; never log raw body/key or disable verification. |
| Provider 429/configuration | Inspect safe diagnostics and account model/quota; manual operations stay available. Existing vision budget is 512 due the verified account limit. |
| Backup/restore refused | Check pause/marker, private paths/permissions, free space, version/checksums and exact target; incomplete files are not recovery points. |

DNS/IPv6/Nginx upstream/TLS renewal/proxy deployment diagnostics will be completed in the approved server packaging phase. None has been verified on the VPS here.

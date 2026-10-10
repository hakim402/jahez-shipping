# Nginx and SSL — complete Shipping files

Prepared and syntax-tested locally in Phase 8. **No live Nginx/DNS/certificate changes have been performed.** The HTTPS syntax check used disposable self-signed fixtures; a real server test must wait for real certificate files. Use the existing verified Nginx/Certbot installation. Do not stop Nginx, replace nginx.conf, disable other sites, use standalone issuance, or request parent/other domains.

## File layout and privacy

| Repository file | Exact Ubuntu installation target |
|---|---|
| `deploy/nginx/jahez-shipping-http.conf` | `/etc/nginx/conf.d/jahez-shipping-http.conf` — **http context**, named maps/zones/safe log format |
| `deploy/nginx/jahez-shipping-proxy.conf` | `/etc/nginx/snippets/jahez-shipping-proxy.conf` — per-location proxy settings |
| `deploy/nginx/shipping-http.conf` | `/etc/nginx/sites-available/shipping.jahez.online` initially |
| `deploy/nginx/shipping-https.conf` | same site path, only after certificate issuance |
| `deploy/systemd/jahez-shipping-nginx-log.socket` / `.service` | corresponding new files under `/etc/systemd/system/` |
| `deploy/certbot/jahez-shipping-reload` | `/etc/letsencrypt/renewal-hooks/deploy/jahez-shipping-reload` |
| `deploy/logrotate/jahez-shipping` | `/etc/logrotate.d/jahez-shipping` |

Verify the actual `http`/site include layout from [host inventory](DEPLOYMENT_VPS.md) before installation. No complete main nginx.conf replacement is supplied or needed. Zones are application-specific and apply to POST only: login 2/minute burst 10, lookup 6/minute burst 30; Redis fixed-window application limits remain authoritative. Webhook has no lookup/login edge limit and a separate 512 KiB bound, allowing normal retries. Upload proxy bound 6 MiB includes multipart overhead around the app's 5 MiB document limit. Connection/read/send timeouts are bounded; AI work stays asynchronous.

The safe access log includes time/method/status/duration/upstream status/random app request ID only. It excludes raw URI, query, IP, usernames, bodies, referrer and user agent. Ordinary Nginx error logs can expose URLs; these Shipping virtual hosts send errors to a dedicated local syslog socket whose stdlib collector writes only timestamp/severity/event to `/var/log/jahez-shipping/error.jsonl`, mode 0600, with 10 MiB × 3 rotation. The socket accepts local datagrams, never exposes logs; a malicious local datagram can produce only a generic severity event. systemd uses a dynamic unprivileged user/private log directory and restarts the collector; monitor its unit/disk status. Disk-write failure produces only a fixed diagnostic, never a payload. The shared Nginx main/global error log and unrelated virtual hosts are not rewritten; inspect their existing privacy policies separately. Start the collector before Shipping traffic; absence of that socket can lose Shipping error diagnostics, though safe access status remains available.

WhiteNoise handles compiled assets through the same proxy, retaining application CSP/cache/privacy headers. No media alias, public upload root or database/backups/env route exists. CSP has the documented Alpine/Unfold inline/eval allowances; do not add a second restrictive global policy without testing admin/assets. The site explicitly overwrites caller forwarding headers, uses only the Shipping hostname, and has no default-server/catch-all takeover. TLS uses supported 1.2/1.3/session directives with explicit cert paths, no assumed Certbot TLS snippets or conflicting duplicate directives.

## 1. DNS and HTTP reachability

Use actual server addresses, not guessed values:

```bash
dig +short A shipping.jahez.online
dig +short AAAA shipping.jahez.online
```

Set A to this VPS's verified public IPv4. Leave AAAA absent unless IPv6 reaches this host and Nginx listens correctly. Supplied files deliberately use IPv4 listen only; if verified IPv6 is required, add `listen [::]:80;` to each HTTP block and `listen [::]:443 ssl;` to the HTTPS block, re-test, and verify externally before setting AAAA. Fix mismatched/stale records before requesting a certificate. If a CDN/proxy is present, verify the route and authoritative client/protocol handling separately; no CDN address trust is assumed here.

## 2. Install the dedicated bootstrap only

Run from `/opt/jahez-shipping` **after Phase 9 authorization** and inventory confirms these paths:

```bash
sudo install -d -m 0755 /var/www/jahez-shipping-acme/.well-known/acme-challenge /etc/nginx/snippets
sudo install -m 0644 deploy/systemd/jahez-shipping-nginx-log.socket /etc/systemd/system/
sudo install -m 0644 deploy/systemd/jahez-shipping-nginx-log.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jahez-shipping-nginx-log.socket
sudo systemctl start jahez-shipping-nginx-log.service
sudo systemctl status jahez-shipping-nginx-log.socket jahez-shipping-nginx-log.service --no-pager
sudo install -m 0644 deploy/nginx/jahez-shipping-http.conf /etc/nginx/conf.d/jahez-shipping-http.conf
sudo install -m 0644 deploy/nginx/jahez-shipping-proxy.conf /etc/nginx/snippets/jahez-shipping-proxy.conf
# Refuse existing Shipping entries before copying; inspect/preserve them first:
sudo test ! -e /etc/nginx/sites-available/shipping.jahez.online && sudo test ! -L /etc/nginx/sites-available/shipping.jahez.online
sudo test ! -e /etc/nginx/sites-enabled/shipping.jahez.online && sudo test ! -L /etc/nginx/sites-enabled/shipping.jahez.online
sudo install -m 0644 deploy/nginx/shipping-http.conf /etc/nginx/sites-available/shipping.jahez.online
sudo ln -s /etc/nginx/sites-available/shipping.jahez.online /etc/nginx/sites-enabled/shipping.jahez.online
sudo install -m 0644 deploy/logrotate/jahez-shipping /etc/logrotate.d/jahez-shipping
sudo nginx -t && sudo systemctl reload nginx
```

Inspect an existing Shipping site entry first and preserve its prior file privately rather than blindly overwriting it. `sudo test` failing is a stop condition, not a command to ignore. Shared Nginx reload occurs only after `nginx -t` passes; verify the other hosted applications immediately afterward. Bootstrap serves only ACME files and generic 503/Retry-After elsewhere. It contains no TLS paths and does not proxy insecure login/app traffic or weaken Django HTTPS/cookies.

```bash
printf 'JAHEZ-ACME-REVIEW\n' | sudo tee /var/www/jahez-shipping-acme/.well-known/acme-challenge/jahez-review >/dev/null
curl -fsS http://shipping.jahez.online/.well-known/acme-challenge/jahez-review
curl -I http://shipping.jahez.online/en/
```

Verify the challenge **from a separate external network**, not only the VPS; expect the exact marker and generic 503 outside the challenge. Check port 80/firewall/cloud security rules without disrupting SSH/other sites. Remove only this temporary marker after successful verification.

## 3. Issue only the Shipping certificate

Use the installed valid Certbot method found by inventory; don't add a competing apt/snap copy. The email below is an explicit owner input, not guessed or embedded in the repo:

```bash
read -r -p 'Certificate renewal email (owner supplied): ' shipping_cert_email
sudo certbot certonly --webroot --webroot-path /var/www/jahez-shipping-acme \
  --cert-name shipping.jahez.online -d shipping.jahez.online --email "$shipping_cert_email"
sudo certbot certificates --cert-name shipping.jahez.online
sudo test -r /etc/letsencrypt/live/shipping.jahez.online/fullchain.pem
sudo test -r /etc/letsencrypt/live/shipping.jahez.online/privkey.pem
```

Certbot may ask the owner to accept its terms; the owner performs that live step. Webroot issuance leaves Nginx and unrelated virtual hosts running. Confirm actual lineage paths; if they differ, update just this site's two certificate directives and hook comparison to the recorded real lineage before proceeding. Never enable HTTPS config referencing nonexistent files or copy an unrelated certificate/key.

## 4. Activate HTTPS and verify security

```bash
sudo cp -p /etc/nginx/sites-available/shipping.jahez.online /etc/nginx/sites-available/shipping.jahez.online.bootstrap-backup
sudo install -m 0644 deploy/nginx/shipping-https.conf /etc/nginx/sites-available/shipping.jahez.online
sudo nginx -t && sudo systemctl reload nginx
curl -I http://shipping.jahez.online/en/
curl -I https://shipping.jahez.online/en/
curl -I https://shipping.jahez.online/ar/
openssl s_client -connect shipping.jahez.online:443 -servername shipping.jahez.online </dev/null 2>/dev/null | openssl x509 -noout -dates -subject -ext subjectAltName
```

Expected: challenge still reachable over HTTP, other paths redirect to the fixed HTTPS host, valid hostname/chain/expiry, EN/AR 200, local fonts/CSS/scripts, generic error pages, secure cookies, successful intended admin login/CSRF and public/manual tracking/private-download separation. Externally backend port 18743 must be unreachable. Check the other sites before/after reload. Do not bypass browser certificate warnings or use curl `-k` as acceptance evidence. Verify request ID/cache/CSP/frame/referrer headers and ensure global Nginx headers haven't combined into a broken CSP. Webhooks use this exact HTTPS `/webhooks/17track/` path; keep signature enforcement.

Leave `SHIPPING_HSTS_SECONDS=0` until actual TLS/redirect/admin/renewal checks pass. Then deliberately start at 300, later 86400/longer after reliable operation, using the scoped pause/resume process to reload env. IncludeSubDomains and preload remain **false**; no parent-domain policy affects the other sites. [Django proxy/HTTPS settings](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header).

## 5. Renewal and diagnostics

```bash
sudo install -m 0755 deploy/certbot/jahez-shipping-reload /etc/letsencrypt/renewal-hooks/deploy/jahez-shipping-reload
systemctl list-timers --all --no-pager | rg 'certbot|snap.certbot'
sudo certbot renew --cert-name shipping.jahez.online --dry-run --run-deploy-hooks
sudo systemctl is-active jahez-shipping-nginx-log.socket jahez-shipping-nginx-log.service
sudo tail -n 30 /var/log/nginx/jahez-shipping-access.log
sudo tail -n 30 /var/log/jahez-shipping/error.jsonl
sudo logrotate --debug /etc/logrotate.d/jahez-shipping
```

Use the detected existing renewal timer; verify it is enabled/healthy rather than installing a duplicate cron job. The new hook only acts on the recorded Shipping lineage, tests Nginx, then reloads the shared service safely. Use the installed Certbot's supported flags; if `--run-deploy-hooks` is unavailable, run the domain dry-run and test the hook separately with `sudo env RENEWED_LINEAGE=/etc/letsencrypt/live/shipping.jahez.online /etc/letsencrypt/renewal-hooks/deploy/jahez-shipping-reload` after `nginx -t`/other-site checks. Record observed output; documentation alone does not establish renewal. [Certbot webroot/hooks guide](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot).

Common failures: wrong A/AAAA, missing listener/reachability, wrong webroot/Host/site include, missing cert lineage, upstream web unhealthy/port mismatch, cookie/CSRF/protocol mismatch, global CSP conflict, untrusted forwarding peer, quota/signature failure. Inspect only Shipping's files/safe logs and known actual inventory. Missing error collector is a diagnostics problem to fix before opening traffic; never switch to raw request logging as a workaround.

## Local verification classification

`python3 scripts/verify_nginx.py` checks these exact files in pinned Nginx 1.30.5: HTTP bootstrap passes with no cert; HTTPS fails without cert; HTTPS passes with disposable self-signed fixture files. This establishes syntax for that image only. Actual Ubuntu Nginx/OpenSSL includes/modules/certs/socket-activation/Certbot/renewal/DNS/reachability remain **not run** until Phase 9. [Nginx stable version](https://nginx.org/en/download.html) and [rate-limit context/key behavior](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html) checked 2026-10-09.

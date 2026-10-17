# Retained Shipping proxy/TLS configuration

These files are a future configuration candidate, not permission to alter the existing VPS. No Nginx, certificate, DNS, firewall or shared service is changed during cleanup. Existing deployed configuration remains separate; actual host syntax/continuity requires a later approved operation.

| Source | Ubuntu target after verified host inventory |
|---|---|
| deploy/nginx/jahez-shipping-http.conf | /etc/nginx/conf.d/jahez-shipping-http.conf inside `http` context |
| deploy/nginx/jahez-shipping-proxy.conf | /etc/nginx/snippets/jahez-shipping-proxy.conf |
| deploy/nginx/shipping-http.conf | /etc/nginx/sites-available/shipping.jahez.online during ACME bootstrap |
| deploy/nginx/shipping-https.conf | same site path only after real certs exist |
| deploy/systemd/jahez-shipping-nginx-log.socket and .service | corresponding /etc/systemd/system/ files |
| deploy/certbot/jahez-shipping-reload | /etc/letsencrypt/renewal-hooks/deploy/jahez-shipping-reload |
| deploy/logrotate/jahez-shipping | /etc/logrotate.d/jahez-shipping |

Complete files live in the repository. They use only Shipping server_name (no default takeover), proxy loopback 18743, overwrite caller forwarding headers, bound uploads/timeouts, serve compiled static through WhiteNoise and deny private/data/backups/health routes publicly. There is no provider webhook location. The named login POST zone remains as edge defense; shared lookup now uses GET with its own shared Redis application limit and no obsolete lookup POST handler. The shared Redis login and lookup limits remain authoritative. Actual trusted proxy peer IPs must be verified before configuring them; no broad forwarded-header trust is assumed.

Safe per-site access logs exclude URI/IP/referrer/user agent. The private Unix syslog collector discards raw error text before writing severity/time/event, with 0600 files and bounded rotation. Start/check its socket service before traffic in a later approved deployment. Do not fall back to raw URL logging. The shared global Nginx log policy is outside this scoped change.

A future certificate setup must verify A/AAAA against actual reachable listeners, install the dedicated HTTP ACME-only webroot/maintenance vhost, run `nginx -t` before reload, and use the existing Certbot webroot installation for **shipping.jahez.online only**, with an owner-supplied email. Do not stop shared Nginx or enable HTTPS files before their exact certificate paths exist. Then install the HTTPS site, test before reload, check other sites, real chain/hostname/expiry, redirects, EN/AR/assets/admin CSRF/secure cookies and renewal timer/domain-specific dry-run. Do not use TLS verification bypass as acceptance evidence.

HSTS defaults to zero; increase conservatively only after actual TLS/admin/renewal acceptance. includeSubDomains/preload remain false. CSP/frame/referrer policy comes from Django; do not add conflicting global policies that break Unfold/Alpine.

```bash
python3 scripts/verify_nginx.py
```

This local networking-disabled pinned Nginx test checks exact files: HTTP parses with no cert, HTTPS refuses missing certs, HTTPS parses with disposable self-signed fixtures. It does not prove current Ubuntu include/module/cert/systemd/Certbot/IPv6 behavior or real TLS. Host-specific commands must follow actual inventory and the separately approved [transition](UPGRADE_ROLLBACK.md), never a blind copy of historical private deployment instructions.

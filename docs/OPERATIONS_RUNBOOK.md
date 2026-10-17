# Reduced-runtime operations and Groq configuration

0.9.0 is a local shared-tracking candidate. The last recorded deployed release is 0.8.1; the VPS has not been inspected or changed by the local implementation/release work. Follow the [migration gate](UPGRADE_ROLLBACK.md) before any future activation.

Production services are web and dedicated Redis. Development also has the frontend compiler/watch. Redis holds shared hashed-IP login and public lookup counters. Admin login permits at most 10 POST attempts per 300 seconds, with 429 after the limit and 503 on counter failure. No process-local production substitute is used. Redis has no host port; only web binds loopback 18743 (dev 18744). SQLite remains single-host with bounded transactions/WAL. No broker, worker, Beat or periodic job exists. The Phase 1 proof command below is explicit and separate from application requests.

`/health/live/` reports process/version. `/health/ready/` checks the installed migration graph, retained session table, Redis/cache and maintenance state. Neither calls a provider or inspects retired business models. Missing migrations/cache or maintenance returns generic 503. Safe structured app logs omit raw URLs, secrets, SQL, message text and exception payloads; random request IDs support diagnosis. Nginx logs use the dedicated safe format/error collector. Cookies/CSRF/host validation/security headers and static serving remain in place.

## Preserved Groq boundary

Private env is left untouched. Retained variables: `GROQ_ENABLED`, `GROQ_API_KEY`, `GROQ_TEXT_MODEL`, `GROQ_VISION_MODEL`, `GROQ_TEXT_OUTPUT_MODE`, `GROQ_VISION_OUTPUT_MODE`, `GROQ_MAX_TOKENS`, `GROQ_VISION_MAX_TOKENS`. Do not paste keys into chat or commit them. Examples use disabled/empty configuration; existing valid configured values remain private. SDK/Pydantic versions stay pinned, without upgrades.

`apps.integrations.groq.configuration()` reports field readiness; `create_client()` creates a bounded fixed-endpoint SDK client without database access or network activity at construction. The shared refresh service uses it for bounded port-label translation when explicitly invoked by the protected admin action or Phase 5 command; no public route uses it. It performs no browser navigation/extraction/translation by itself. Callers must close the client; tests use mock HTTP transport only. A configured key/model is not proof of live authorization, quota, extraction accuracy or carrier access.

Historical carrier variables in a private old env are ignored by current code, not erased. They are absent from active examples/validation. Private files remain on storage for recovery; no upload/download UI or public media alias exists. Do not delete them, old images, volumes or backup evidence as cleanup.

After separately approved activation, use exact scoped Compose commands from [deployment](DEPLOYMENT_VPS.md). Inspect web/Redis status, safe logs and disk. No production backup or monitoring schedule is installed. The later Phase 5 retrieval timer is packaged but inactive. Same-host archives do not establish host-loss protection.

## Phase 1 carrier source proof

`apps.integrations.sealegend` configures one adapter/host/path in code: HTTPS `www.slg-shipping.com`, POST `/slg-sealegend-rest/containerDynamicForWeb/list.do`, JSON key `bkgNo`. This is the public website's **undocumented endpoint**, not an official supported API. A bounded inspection of the public navigation/assets and a site-restricted API/export search found no supported developer interface. The [carrier terms](https://www.slg-shipping.com/#/terms-of-use?tab=gateway) describe changeable information and content-use restrictions; permission for unattended reuse and service guarantees are not established by technical access.

An authorized live proof on 16 October 2026 succeeded in the carrier UI and through direct HTTP, then twice in an isolated nonroot/read-only Python 3.12 container with no owner environment, cookies or volumes. The two adapter responses had identical fingerprints and identities. This short sample does not establish daily availability, provider rate limits, VPS egress or a stable API contract. No browser runtime/dependency was added. JavaScript is needed for the carrier's UI, not this HTTP method. Authentication, CAPTCHA and session cookies were not required for the observed calls; future challenges must fail safely, never be bypassed.

Each explicit lookup makes exactly one request, no retry or redirect, with a 6-second socket timeout, 20-second killable child-process deadline including DNS/TLS/body, 256 KiB response cap, and JSON/identity encoding requirements. All DNS answers must be public; the checked literal is connected with certificate validation and the carrier hostname for TLS. Unsafe mixed answers, IP transition forms and redirects to any destination fail before another request. Proxy variables are not used. No remote scripts, navigation, subresources or returned URLs execute. Only bounded safe error codes leave failures.

The candidate preserves the B/L separately from all container identities, route codes, raw equipment, nullable quantity/type, and per-event vessel/voyage/raw status. No container is bound or saved. Multiple containers set `container_selection_required`; none is silently selected. Duplicate presentation variants collapse without dropping distinct actual/estimated facts. Original timestamps retain date/minute/second precision and designation; timezone/normalized instant stay null. Undated or missing values stay missing, and no shipment-level progress is inferred from an ETA, B/L type or empty return. Source changes/mismatches fail rather than generate invented facts.

In a configured Shipping Python runtime, run `python manage.py probe_carrier`; enter the authorized B/L at its hidden prompt. For scripts, use `--stdin` with a private input file, never a reference argument or shell history literal. Default output contains only counts/selection state. `--save-private` replaces the single ignored `private/source-proof/candidate.json` (0600, private directories 0700; output symlinks refused). It saves a candidate file, never database/public records. This option needs a writable local checkout and is not a production data-import workflow. Remove the capture when review no longer needs it; no indefinite page archive is maintained.

For offline/manual fallback use `--from-file <private-carrier-json-file>` with the same B/L prompt. This parses a bounded, manually obtained carrier JSON response with **zero network calls**, using the same identity validation. Keep the JSON confidential. If the website/interface stops working, inspect facts manually in the carrier page or contact the carrier; do not replace the adapter with unrestricted URL fetching or invent a successful refresh. Phase 3 provides verified manual-copy date/route fields and bilingual manual timeline updates; see the [admin guide](ADMIN_GUIDE.md). This does not import the JSON or perform retrieval.

The standalone probe remains database/AI-free. Phase 4 reuses its unchanged adapter/parser inside the explicit admin refresh service, which saves validated facts to Container/ContainerEvent. Routine tests remain synthetic/mock-only. Phase 6 public lookup reads approved saved data; no active schedule or production activation is established. Current schema rules and limits are in [the data guide](DATA_MODEL.md).

## Phase 4 explicit admin refresh

Refresh now requires container change permission and CSRF-protected POST after confirmation. Save edits first. Archived journeys are excluded; a B/L with several containers requires an explicit verified selection. The service keeps old facts on failure. New carrier events remain private unless the Phase 6 gate admits validated known dated updates for an explicitly opted-in already reviewed published journey. Unknown stages require review. Retries are deliberate; neither the carrier adapter nor Groq automatically retries. The Phase 5 command and inactive timer package reuse this service; activation remains separately gated.

Core identities, route, equipment and actual/estimated dates come from the strict deterministic parser. Groq receives at most eight bounded source port names for Arabic transliteration, without B/L, physical identity, manual notes or credentials in model content. The existing private model/key/mode are preserved; unchanged accepted labels are reused even when ETA changes. An unsupported schema-mode model fails safely rather than silently switching models or output modes. Arabic transliterations need administrator review; they are not independently verified operational facts.

The current SDK request uses `https://api.groq.com/openai/v1/chat/completions`, no tools or redirects/retries, and strict local validation for both JSON/schema modes. Provider documentation checked 17 October 2026: [structured outputs](https://console.groq.com/docs/structured-outputs), [API reference](https://console.groq.com/docs/api-reference). Supported strict schema models are explicitly bounded in code and must be rechecked before changing configuration. The provider process group has an 18-second hard deadline, including carrier/AI/DNS, with a shorter per-request AI timeout. No request/proxy timeout was increased.

Separate authorized Phase 4 live acceptance passed on 17 October 2026 in a disposable nonroot/read-only container and temporary SQLite database: the first carrier refresh saved validated facts and Groq Arabic port labels in 4.265 seconds; the second accepted unchanged source data in 2.582 seconds, retained the translation cache and kept the same three event records. No record/event was public; claims were released and success timestamps recorded. At most one model request was allowed, with AI disabled on the second check. No real reference/key was committed or printed. The container and temporary database were removed. This short sample does not establish ongoing availability, VPS egress or permission for unattended use; scheduled execution and production activation require later phases.

## Phase 5 bounded daily command

Run only in the intended Shipping runtime/environment. These are deliberate commands, not public endpoints:

```bash
python manage.py refresh_containers --active --dry-run
python manage.py refresh_containers --container 123 --status
python manage.py refresh_containers --active --limit 50 --max-seconds 900
```

Replace the example internal admin ID for a scoped selection. Dry-run/status reads bounded selection counts only: no provider, claim, lock file or database write. It is safe before schedule activation. `--active` includes unpublished journeys; archive or either completed carrier/manual state excludes a journey. ETA age does not stop checking. Eligibility is checked again in the claim transaction. The command and admin share the exact Phase 4 refresh path.

One run selects up to 50 journeys by default (configurable 1–100), oldest attempt first with never-checked first. Its default 900-second budget can be reduced to 60 seconds; 900 is the hard maximum. It starts another record only with at least 30 seconds remaining for the bounded service and cleanup. No automatic retry occurs at either batch or provider level. One failure does not stop the next selected record. A shared data-directory OS lock refuses concurrent batches; per-container claims also prevent overlap with the admin. Crashed batch locks release automatically; leave the lock file in place. Claims recover after their existing expiry.

Output is one JSON summary containing counts/booleans only: selected, attempted service calls, changed, unchanged, skipped on eligibility recheck, failed, attention, deferred, more_eligible and dry_run. No identifiers, raw errors or credentials are printed. Exit 0 means selected work completed without attention; 1 means failures/unknown stages require review; 2 means bounds/selection are invalid or selected/eligible work remains; 75 means a batch lock/database is unavailable. Dry-run exits 0 after valid selection even when more work exists. `--quiet` suppresses successful unchanged/no-work output; changed results and actionable failures/incomplete work stay visible. Batch failures do not send messages. Inspect the existing admin attention filter and last attempt/success for diagnosis. Review bounds against actual fleet size and provider timing before activation; deferred work is not automatically replayed in a loop.

## Prepared Linux timer — activation only in Phase 8

`deploy/systemd/jahez-shipping-refresh.service` and `.timer` are a package only. They are not installed or enabled by this implementation. The actual deployment host's systemd/Docker support, installed current image, service identity, data volume, paths and production environment must be verified in Phase 8. Do not use a development container or historical production image for this timer.

The proposed calendar is `*-*-* 09:00:00 Asia/Kabul` (04:30 UTC), with one-minute accuracy. The timezone is explicit. `Persistent=true` permits one bounded catch-up activation after missed calendar occurrences, rather than replaying one run per missed day. A matching oneshot already running is not started a second time. `Restart=no` prevents retry loops. These semantics follow the official [timer documentation](https://github.com/systemd/systemd/blob/main/man/systemd.timer.xml) and [calendar syntax](https://github.com/systemd/systemd/blob/main/man/systemd.time.xml), checked 17 October 2026.

The service uses [Compose exec](https://docs.docker.com/reference/cli/docker/compose/exec/) with no TTY/input, targeting only the already-running `jahez-shipping-prod` web service, its installed image/environment and shared data-directory lock. It does not start containers, migrate, add a queue, or pass secrets in arguments. The host Docker client runs as root because Docker socket access is administrative; the application command retains the existing container's nonroot user. The 960-second service timeout includes startup margin over the 900-second application budget. Stopping the Docker client does not guarantee cancellation of a container exec; the application budget/locks provide the bounded run. No host-level timeout alone is claimed to kill the provider group.

Phase 8 installation procedure, after owner approval and host verification:

1. Confirm `/opt/jahez-shipping`, `/usr/bin/docker`, `.env.prod`, Compose project/service, current image and persistent volume match the approved Shipping installation. Adjust both unit files if needed; paths contain no secrets. A non-default `SHIPPING_IMAGE`/`SHIPPING_ENV_FILE` must resolve consistently with the approved deployment; never print resolved Compose environments.
2. Review the time before installation. To customize it with a timer drop-in, reset inherited `OnCalendar=` to empty, then add exactly one explicit-zone value. Verify with `systemd-analyze calendar '*-*-* 09:00:00 Asia/Kabul'`. Do not create an additional cron job or second timer.
3. In the verified running application, run `refresh_containers --active --dry-run` first. Review selected/more_eligible counts and bounds. This does not make provider calls.
4. Run `systemd-analyze verify deploy/systemd/jahez-shipping-refresh.service deploy/systemd/jahez-shipping-refresh.timer` on that Linux host. Fix host prerequisites rather than bypassing failures.
5. Only in the separately approved Phase 8 activation window, copy these two reviewed files to `/etc/systemd/system/` with mode 0644, then run the following. Enabling a persistent timer can immediately initiate one paid catch-up batch; that transmission/activation must be approved.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jahez-shipping-refresh.timer
systemctl list-timers jahez-shipping-refresh.timer
systemctl status jahez-shipping-refresh.service
journalctl -u jahez-shipping-refresh.service --since today
```

The above commands are installation instructions, not commands executed during Phase 5. Review actual next-run time, one manual synthetic check where appropriate, actual scheduled execution and admin freshness separately; configuration parsing does not prove timer execution.

Removal/rollback, scoped to these units: disable the timer with `sudo systemctl disable --now jahez-shipping-refresh.timer`. If its oneshot is active, let its bounded run finish before removing the two installed files and any reviewed timer drop-in, then run `sudo systemctl daemon-reload`. Do not stop/recreate the web container, remove data/locks/environment files or clear provider credentials. Disabling the timer prevents future triggers; it does not cancel an already-running command or undo accepted facts.

## Phase 6 public lookup and publication

GET `/<language>/track/?code=...` normalizes a valid shared JAHEZ code and redirects to its canonical result path. Results read only a validated approved snapshot of a published, non-archived journey. Invalid syntax is 400; missing/private/archived/not-yet-reviewed journeys share 404 feedback. Cache/database/snapshot failure returns generic 503; no exception or private diagnosis reaches the result. Approved data may be stale and is not continuous GPS tracking.

The lookup counter permits 30 attempts per 300 seconds for one hashed client identity, shared across codes and languages. Limit exhaustion returns 429 and Retry-After 300; counter failure denies lookup with 503. Production uses the existing shared Redis backend. Only configured trusted proxies affect client identity; direct spoofed forwarded headers do not obtain a new bucket. No business rows are written by lookup. It never invokes refresh, carrier/browser retrieval, Groq or the daily command.

Results use private/no-store caching, no-referrer and noindex/nofollow. Canonical/hreflang metadata omit the shared capability code; the visible language switch retains it. Existing safe application/proxy logging omits raw paths/query values. Treat codes as recipient-controlled shared access, keep screenshots/operational evidence private, and do not add analytics or external scripts that collect them. The configured WhatsApp contact remains a contact link without appending the code or B/L.

First publication is manual. Per-journey automatic carrier publication is off by default and requires a deliberate confirmed opt-in after reviewing that real journey. It cannot first-publish private records, expose manual notes/new private events, accept unknown mappings or publish unreviewed AI Arabic port labels. Accepted current carrier fields/milestones alone may advance the approved copy; omitted fields and approved manual/Arabic content are preserved. Uncertain source data holds the old copy and admin attention. Review the public last-success time separately from private refresh health; it becomes stale at 30 hours. See the [admin workflow](ADMIN_GUIDE.md) before sharing a code. No real journey was opted in by the implementation, and the Phase 5 timer remains inactive until Phase 8.

## Release acceptance and remaining activation

Build and test the locked candidate with the [README isolation sequence](../README.md#reproduce-release-verification-in-isolation). `scripts/verify_release.py` uses installed production code, synthetic providers and an internal-only review network, verifies shared Redis and actual outage refusal, and rehearses web recreation plus matching database/private-file recovery. It pins its generated test environment/image/limits against inherited shell interpolation so owner configuration cannot be substituted. Source/template/catalog/fixture/lockfile hashes are checked against the intended checkout before acceptance. This rehearsal does not activate a timer or prove live carrier, HTTPS, VPS or off-server backup behavior.

Production Compose bounds web to 768 MiB by default, one CPU and 128 processes; Redis defaults to 256 MiB, half a CPU and 64 processes. Gunicorn stays at one worker/two threads with a 30-second request timeout. These are configured limits verified in isolated runtime, not throughput or fleet-capacity claims. Verify actual target architecture/resources before transferring/building the candidate in Phase 8. No dependency upgrade or browser runtime is required by the proven direct-HTTP source method.

Django deployment checks retain the expected `security.W004` warning while HSTS is zero pending actual TLS acceptance. Do not silence the check or enable HSTS merely to obtain a clean local report. Verify real certificates, proxy behavior, other-site continuity and recovery first in the separately approved activation window. Keep source/mocked, installed-image/synthetic, authorized live provider and actual scheduled/deployed evidence separate.

# Reduced-runtime operations and Groq configuration

0.9.0 is a local cleanup candidate. The last recorded deployed release is 0.8.1; it has not been inspected or changed during cleanup. Follow the [migration gate](UPGRADE_ROLLBACK.md) before any future activation.

Production services are web and dedicated Redis. Development also has the frontend compiler/watch. Redis is intentionally retained for shared hashed-IP admin login counters: at most 10 POST attempts per 300 seconds, with 429 after the limit and 503 on counter failure. No process-local production substitute is used. Redis has no host port; only web binds loopback 18743 (dev 18744). SQLite remains single-host with bounded transactions/WAL. No broker, worker, Beat, periodic job or retrieval command exists.

`/health/live/` reports process/version. `/health/ready/` checks the installed migration graph, retained session table, Redis/cache and maintenance state. Neither calls a provider or inspects retired business models. Missing migrations/cache or maintenance returns generic 503. Safe structured app logs omit raw URLs, secrets, SQL, message text and exception payloads; random request IDs support diagnosis. Nginx logs use the dedicated safe format/error collector. Cookies/CSRF/host validation/security headers and static serving remain in place.

## Preserved Groq boundary

Private env is left untouched. Retained variables: `GROQ_ENABLED`, `GROQ_API_KEY`, `GROQ_TEXT_MODEL`, `GROQ_VISION_MODEL`, `GROQ_TEXT_OUTPUT_MODE`, `GROQ_VISION_OUTPUT_MODE`, `GROQ_MAX_TOKENS`, `GROQ_VISION_MAX_TOKENS`. Do not paste keys into chat or commit them. Examples use disabled/empty configuration; existing valid configured values remain private. SDK/Pydantic versions stay pinned, without upgrades.

`apps.integrations.groq.configuration()` reports field readiness; `create_client()` creates a bounded fixed-endpoint SDK client without database access or network activity at construction. No route or task uses it. It performs no browser navigation/extraction/translation by itself. Callers must close the client; tests use mock HTTP transport only. A configured key/model is not proof of live authorization, quota, extraction accuracy or carrier access.

Historical carrier variables in a private old env are ignored by current code, not erased. They are absent from active examples/validation. Private files remain on storage for recovery; no upload/download UI or public media alias exists. Do not delete them, old images, volumes or backup evidence as cleanup.

After separately approved activation, use exact scoped Compose commands from [deployment](DEPLOYMENT_VPS.md). Inspect web/Redis status, safe logs and disk. No production backup schedule, retrieval scheduler or monitoring configuration is added in this cleanup. Same-host archives do not establish host-loss protection.

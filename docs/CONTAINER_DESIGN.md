# Next phase: shared container tracking — design only

This is a proposal, not implemented models, retrieval, scheduling or publication. The initial business schema should contain only **Container** and **ContainerEvent**. Customer accounts, customer rows, per-person shipments/products and document/AI review records are unnecessary for the shared-container business.

## Container

Keep separate fields for the carrier's B/L/search reference and the actual container identifier; neither is interchangeable with vessel/voyage or an internal database ID. Record source website and supported source adapter, equipment quantity/type, loading/discharge codes and reviewed bilingual route labels, vessel/voyage, raw carrier status plus reviewed bilingual status. Unknown facts remain null/unknown.

Represent departure/arrival separately and distinguish **estimated versus actual** explicitly. Preserve each raw timestamp and its displayed precision/type, plus a nullable source timezone and nullable normalized instant. If the source displays no timezone, retain it as an unzoned local datetime/text, label “timezone not supplied”, and leave the UTC instant empty. Never silently apply the application/business timezone or render it as an exact instant. Corrections retain provenance instead of upgrading an estimate to an actual fact.

Include independent manual notes, archive flag/time and deliberate publication control. Public lookup returns only reviewed saved fields for published, non-archived records. Last refresh attempt/success and a bounded safe error code/summary are separate; errors omit secrets, page bodies and identifiers. Failed retrieval retains the last good facts, their source/last-success time and manual notes. Carrier refresh never overwrites independent manual notes or implicitly publishes a record.

## ContainerEvent

Reference Container; record origin (`carrier` or `manual`), raw source status/text/time/timezone/precision, reviewed English/Arabic title/detail, optional source event identifier, observed/retrieved time, publication flag and stable dedupe key. Prefer a source-provided ID; otherwise hash a canonical tuple of container, source, raw event time, status/location/text. Repeated retrieval updates provenance/last-seen safely instead of duplicating a milestone. Manual events have their own identity and cannot be overwritten by carrier events. Unknown event timezone follows the same nullable-instant rule.

## Retrieval boundary and one future command

Prove supported source access first: documented carrier interface/export before an HTTP adapter, browser retrieval only if necessary and permitted. Use a host allowlist, bounded redirects/time/content, explicit timeouts and safe diagnostics; do not let an administrator-provided URL become unrestricted SSRF. Authentication/CAPTCHA/terms/source availability must be evaluated against the actual source. Do not promise unattended extraction before that proof.

A later application command should drive both explicit manual refresh for one container and once-daily refresh of active containers through the same bounded retrieval/validation/save path. Choose the scheduler later; none exists now. Acquire per-container concurrency protection, validate facts/events atomically, record attempted/successful refresh separately and avoid unnecessary paid requests. Public page views read saved data only, never initiate retrieval or AI.

Groq may receive bounded, already retrieved content for structured facts/translation. Its API is not a web browser. Treat page content as untrusted data, never instructions; select a supported model/output mode, validate with a strict local schema, preserve source evidence and distinguish missing/uncertain facts. Reject unsupported facts and malformed output, never invent dates/statuses. No automatic publication, manual-note overwrites or private-data transmission merely on page view.

The reference website/example supplied by the owner is historical context only. This cleanup does not query, seed, publish or send that real reference to any service. Future source access and real-reference tests require their separately approved phase.

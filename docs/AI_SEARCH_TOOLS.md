# Read-only operational assistant — Phase 6

Open `/en/admin/ai/aidraft/assistant/` or its `/ar/` equivalent. Local search never calls Groq or 17TRACK. Optional, explicitly consented private explanations use Groq in the Celery worker. No assistant action changes, publishes, registers, uploads or sends a shipment/customer record.

## Fixed tools and query scope

`apps/ai/operations.py` has four fixed ORM functions behind an explicit allowlist. The model does not choose ORM fields, SQL, Python, URLs, commands or nested tool calls; it only explains a projected result. A worker re-runs the selected tool before and after Groq for source/permission validation.

| Tool | Meaning |
|---|---|
| `delayed` | Active, nonterminal shipments with confirmed delay or overdue known ETA. Exclude delivered, returned and cancelled. Missing ETA, hold status or outage alone does not establish delay. |
| `arrived` | Recorded `actual_arrival` within explicit local dates. Later delivered status can still match. Arrival status/events without this date do not establish arrival in the range. |
| `status` | One exact allowed status; optional date range applies to record creation. |
| `quality` | Deterministic flagged shipments and per-issue totals across the selected scope; optional dates apply to record creation. |

All tools exclude archived rows. Normal queries exclude DEMO; the development checkbox selects **only** DEMO. Production rejects DEMO scope. Dates require both ordered ISO dates and at most 366 days inclusive. Aware local midnight bounds use the configured business timezone (Asia/Kabul), with a half-open end at the next local midnight. Timestamps retain explicit UTC offsets.

Database counts, displayed rows and quality totals share one short atomic snapshot. On SQLite's configured IMMEDIATE mode, this briefly reserves the writer; scale/contention testing remains Phase 7. Count covers every match; display/model rows are the first 25 by shipment ID. A notice distinguishes full count from the sample. Narrow status/date scope to inspect other results. There is no unrestricted export, user-selected field/sort expression or customer/document search.

## Questions and clarification

A deliberately small local bilingual grammar recognizes “Which shipments are delayed?” / “ما الشحنات المتأخرة؟” and “Which shipments arrived this week?” / “ما الشحنات التي وصلت هذا الأسبوع؟” (plus documented show variants). “This week” explicitly means Monday–Sunday in the business timezone and shows its exact dates. A recognized question selects query/date scope; otherwise use structured controls with the question empty. Vague “recently”, unsupported requests, injected instructions and oversized/invalid dates require clarification instead of guessing. Questions are not persisted or sent to Groq. This is a narrow operational assistant, not unrestricted conversational database access.

## Deterministic quality flags

Missing bilingual routes; no products; invalid quantity/negative weight or volume; public item missing Arabic product/unit labels; future actual dates (five-minute tolerance); delivery before arrival; delivered without actual delivery date; duplicate nonempty trimmed/case-insensitive bill/order identifiers **within the selected active scope**; API/hybrid without a carrier reference. Unknown ETA alone is not an error/delay. One shipment may contribute to several totals. These checks flag suggestions, never correct data. Existing write constraints prevent many invalid quantities/references; checks also support other legacy/manual inconsistencies.

Projection excludes customer contacts/details, documents/filenames, raw provider text, product descriptions, private notes/reasons and bill/order/carrier/customer tracking reference values. The model gets only scope, count/sample size, IDs, statuses, timestamps, quality codes/totals and warnings. Shipment links are built server-side; model URLs are never followed or used.

## Permissions and private background explanations

Every tool call requires active staff, `ai.query_shipments` and `shipments.view_shipment`. Quality also requires `ai.check_quality`, `shipments.view_shipmentitem` and `shipments.view_trackingleg`. Current roles grant workspace-wide shipment access; this app does not implement tenant/customer-specific row isolation.

Operations and Read Only definitions gain query/quality permissions and `ai.view_assistantrun`; no new users/assignments. External explanations additionally require existing `ai.request_ai` (Operations/owner), consent and non-DEMO scope. Read Only cannot request external work. Runs are requester-only and source-permission-revalidated; there is no generic editable run admin or apply action.

A signed ten-minute selection binds user/scope/result hash. Tampering, changed results, cross-user tokens and missing consent cannot schedule work. Persist the run before dispatch; unique actor/scope/source key deduplicates repeated confirmation. Failed broker publication leaves pending work. The worker uses a 120-second fenced lease, checks authority/source before and after Groq, and performs network work outside writes. Shared Groq rate control, safe diagnostics and three-attempt bounded backoff apply; local rate/cache deferrals retain attempt budget. One-minute recovery dispatches at most 25 eligible jobs and recovers expired leases. Retention uses existing 1–90-day configuration; expired scope/result/output purged in batches of 100, audit metadata retained. Views hide expired answers immediately even before purge.

Strict schema/citation/numeric validation rejects extra tools/mutation fields, unknown source IDs and unsupported numeric claims. It cannot prove semantic truth. Exact database results remain prominent; AI wording is a private suggestion. Changed sources hide stale saved results/answers and offer a new query. Provider failure leaves local results usable. No operational update, publication or customer communication is available.

## Reviewed examples

`python manage.py seed_search_demo` adds three private DEMO-SEARCH fixtures without users, uploads or requests; repeat calls retain history. Review observed two delayed DEMO shipments (including an earlier carrier fixture), one actual arrival during 2026-10-05–2026-10-11, and seven quality-flagged DEMO shipments. These describe invented review data only.

Using the existing owner session, a real empty non-DEMO query (no non-DEMO shipment rows existed) was submitted and explicitly selected for explanation. Real Redis/Celery/Groq processing completed with exact count zero and a bilingual scope-cited answer. No customer/document/reference was sent and persisted DEMO proposals were not relabeled as recognition. No staff account/session was manufactured.

Real business-data answer quality, arbitrary language coverage, scale/concurrency and full crash/restore remain unverified.

# 17TRACK integration — Phase 4

The implemented adapter targets **v2.4** exclusively. Official contracts were checked on 2026-10-09 at [17TRACK API documentation](https://api.17track.net/en/doc). No live account/key/reference test was performed in this phase; recorded fixtures are invented and explicitly labeled. Manual tracking remains independent.

Verify authentication and account quota privately before enabling live registration. Validate real-reference mapping and webhook/TLS delivery on the intended deployment.

## Configuration and exact endpoints

Configure privately in this app's environment file, never in chat, frontend code, screenshots or Git:

| Variable | Default / purpose |
|---|---|
| `TRACK17_ENABLED` | `false`; disabled requires no key and sends no requests |
| `TRACK17_API_KEY` | Empty; API authentication and documented webhook verification key |
| `TRACK17_RECONCILE_SECONDS` | 21600 (six hours), clamped to 3600–86400 |

Existing `.env.dev` is preserved by the helper; add these fields privately when needed. Changing environment values requires recreating this app's containers, not just Django reload. Set enabled only when ready to allow requested/scheduled server-side carrier calls. The integration UI shows configured/unverified rather than claiming a key has been validated live.

Outbound host is fixed to `api.17track.net`, with HTTPS and normal certificate verification. There is no configurable arbitrary base URL and no redirect following. Requests use the `17token` header and JSON arrays. A maximum of 40 identifiers is enforced; current operational jobs intentionally send one reference at a time. No customer contact, bill, public capability, document or route is sent.

| Action | Endpoint / behavior |
|---|---|
| Register | `POST https://api.17track.net/track/v2.4/register` with carrier-issued `number` and explicit positive numeric `carrier` |
| Retrieve stored details | `POST https://api.17track.net/track/v2.4/gettrackinfo`; ingests `data.accepted[].track_info`, handles each rejected number independently |
| Incoming webhook | Local `http://localhost:18744/webhooks/17track/`; future production **`https://shipping.jahez.online/webhooks/17track/`** |
| Integration health | `/en/admin/integration-health/` and `/ar/admin/integration-health/` |

The production webhook URL is a configuration target for the later approved VPS launch; it is not deployed now. Do not send private payloads to a third-party webhook testing service. Localhost is unreachable to 17TRACK; no tunnel was opened.

Registration requires an active API/hybrid shipment, configured key, explicit carrier and supported identifier. DEMO records cannot be sent to the live provider. A bill of lading/container/internal order is not automatically a supported tracking number. Carrier-specific extra query parameters and automatic carrier detection are intentionally unsupported in this phase: use manual tracking if a carrier requires more fields. The provider decides actual coverage; a numeric code alone does not prove support.

An HTTP 200 does not establish per-number acceptance. The adapter checks top-level `code` and exact number/carrier matches in accepted/rejected arrays. Already-registered code `-18019901` is idempotent for registration only. Unsupported carrier/identifier, no updates, authentication, quota, timeout and rate failures become fixed safe diagnostic codes, never echoed provider messages.

## Webhook contract and verification

The selected v2.4 notification contract is one object: `event` is `TRACKING_UPDATED` or `TRACKING_STOPPED`; `data` contains a number/carrier and, for updates, `track_info`. Legacy schemas and the ambiguous batch shape shown in the documentation's quick example are rejected rather than silently interpreted as this contract. Confirm the actual account's notification shape during live acceptance.

1. Require configured integration, POST and JSON; reject bodies above 512 KiB (also bounded by Django's request limit).
2. Read **unchanged bytes**. Calculate lowercase SHA-256 hex over `raw_body + b'/' + API_key.encode('utf-8')`; compare with the `sign` header using `hmac.compare_digest`. This is the provider's concatenation algorithm, not an invented HMAC protocol. Changed whitespace invalidates a signature calculated from a reserialized body.
3. Parse and normalize only after verification. Bound providers to 10, events to 500, descriptions to 4000 characters and locations to 160. Drop phone/contact/address/tag/URLs and other unneeded fields; retain private source text and original date/time information needed for review.
4. Within a short SQLite transaction, persist a SHA-256-deduplicated private receipt and its unique pending job. Queue after commit; a submission failure leaves durable pending work for reconciliation.
5. Return **HTTP 200** only after durable acceptance, including duplicate receipts. Unknown/ineligible references are durably quarantined by the worker without creating shipments. Database failure returns 503; malformed content 400, invalid signature 401, oversized body 413, wrong type 415, disabled/missing-key 503. Responses contain no tracking number or job/record details.

The documented signature has no timestamp/nonce. Body-level deduplication and event fingerprints prevent replays from creating duplicate history; retained valid messages can be replayed, so possession of the provider key remains important. Keep the endpoint TLS-only in production and keys private. Rotation support currently uses one active key; coordinate it with the provider and expect retryable failures during a mismatched-key interval.

## Time and event/status mapping

Carrier events preserve original carrier `time_raw` and `time_iso` privately. An aware, valid `time_utc` or `time_iso` becomes UTC; missing/naive/invalid/far-future time remains unknown. Receipt time never substitutes for unknown occurrence time. Unknown-time published events explicitly say their exact time is unconfirmed. No ETA is inferred from provider events/ranges.

| Provider main/sub status | Normalized meaning |
|---|---|
| InfoReceived | preparing |
| InTransit | in transit |
| InTransit_Departure | departed |
| InTransit_Arrival / AvailableForPickup | arrived |
| InTransit_CustomsProcessing | customs |
| OutForDelivery | out for delivery |
| Delivered | delivered, subject to all-leg/coverage rules |
| Expired / DeliveryFailure / Exception / customs requiring information | on hold |
| Exception_Returned / Exception_Cancel | returned/cancelled, subject to coverage |
| NotFound or unknown future status | no business-status mapping; retain private history |

Each carrier event has a stable fingerprint scoped to its tracking leg; identical history in repeated receipts/detail retrieval is inserted once. Official carrier event stages such as PickedUp/Departure/Arrival map separately from main status. Unknown/inconsistent main statuses do not advance business state. Provider source fields are immutable in staff forms/services. Authorized staff may edit approved bilingual display text and publication; imported raw text is never automatically public. Default titles use controlled bilingual normalized labels; private provider descriptions are separate.

Overall status changes require API/hybrid mode, no manual lock, a newer known observation and no protected terminal/backward regression. Existing non-created manual statuses receive an observation watermark during migration; explicit staff status corrections update it. Releasing a lock does not immediately reapply older carrier history. Future newer observations can apply under the same rules.

For multiple references, incomplete/unknown leg state cannot complete the whole shipment. When all legs have known states/times, common ranked progress uses the least advanced leg; a later hold can signal an exception. Automatic delivered requires **all** legs delivered and the owner's explicit **all packages covered** setting. Returned/cancelled aggregation is restricted to a single fully covered leg. Staff final confirmation remains available through the manual workflow when coverage is incomplete. A single-package delivery never completes uncovered/multi-leg freight.

Successful synchronization is distinct from receipt arrival and business status. A verified sync timestamp is recorded only when every reported participating provider has a successful known synchronization time; use their oldest time conservatively. Public freshness requires a timestamp for every leg and uses the oldest. Older than 24 hours gets a stale notice; missing sync stays unknown. Outage/staleness does not set the delay flag or invent an ETA.

## Durable jobs, rate limits and recovery

`WebhookReceipt` and `IntegrationJob` are persistent SQLite records. Jobs are pending, running, retry, succeeded, failed or quarantined; lease tokens fence stale workers. Registration/refresh keys deduplicate work per leg; one active outbound job per leg is admitted. Repeated queue messages cannot claim completed/running work. Registered identifiers remain retained; add a new reference to change them.

One Beat task runs each minute: recover due pending/retry work and expired 120-second leases (bounded to 50 jobs), then schedule up to 10 due eligible stored-detail queries. Receipt processing is primary. Reconciliation defaults to six hours; manual, archived, terminal and stopped tracking are excluded. Requested detail retrieval has a 15-minute cooldown. Re-tracking/reactivation, stop/delete/change-carrier and paid real-time endpoints are not implemented; do not imply those controls exist.

The official limit is three requests/second; this app conservatively uses one shared-cache outbound slot/second. Cache failure prevents requests. Connect timeout is three seconds, read timeout eight seconds, response capped at 1 MiB; Celery has a 60-second soft/90-second hard limit. Retry up to five attempts with bounded exponential delay/jitter; honor numeric Retry-After up to one hour. Local rate/cache deferrals do not consume the provider-attempt budget. Quota exhaustion backs off for an hour; inspect allocation before an operator retry.

Network work happens outside database write transactions. Only claim, receipt/application and completion records hold short atomic transactions. Redis loss does not erase accepted SQLite truth; recovery after Redis/worker/Beat availability returns is bounded. Permanent authentication/identifier/contract failures stop automatic rescheduling until operator review. Failed/exhausted work remains visible for authorized explicit retry. SQLite contention/capacity, full Redis crash/restore, off-server backups and comprehensive recovery remain Phase 7.

## Review without credentials

Run `python manage.py seed_tracking_demo` in the development container. It adds **DEMO-CARRIER**, a private hybrid shipment with a labeled fixture, one private carrier event and a processed receipt/job. It performs no provider request and does not create an account. DEMO synchronization is excluded from live health metrics; DEMO rows are visibly labeled. Existing reviewed publication is retained on repeated seeding.

Review its carrier event, approve bilingual display wording, and publish only the synthetic summary if desired. Public pages clearly label the record as synthetic; production hides it. Refer to [local development](LOCAL_DEVELOPMENT.md) for commands.

After credentials are configured privately and a real eligible carrier reference is supplied, later authorized live checks should verify registration, actual account webhook format/signatures, detail response mapping, quota and TLS delivery. No live verification or provider account change is claimed here.

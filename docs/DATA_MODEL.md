# Data model and application boundaries

There are exactly two business models: `Container` and `ContainerEvent`. Django also retains Users, Groups, Permissions, Sessions, ContentTypes, admin logs and migration metadata. The migration-only `ai`, `shipments` and `tracking` apps register no business models; their files preserve the historical migration graph.

## Container: one physical container on one journey

| Data | Rule |
|---|---|
| `journey_key` | Immutable internal UUID. A later voyage uses a new journey even if the physical number/B/L is reused. |
| `search_reference`, `container_number` | Distinct B/L/search and physical identities. The number can be empty until an unambiguous carrier result or explicit valid selection binds it. |
| Source | Only the configured Sea Legend adapter/website. A bound source/B/L/container cannot be silently reassigned. |
| Equipment/route/vessel | Quantity may be null; missing text stays empty. Separate codes, English/Arabic labels, vessel and voyage. |
| Status | Raw carrier status plus a normalized enum; unknown stages require review. A separate optional manual override is retained. |
| Source dates | Separate actual/estimated departure and actual/estimated arrival JSON values, described below. |
| Manual content | Separate English/Arabic notes; a source refresh cannot overwrite them. |
| Publication | `is_published=False`, empty `public_snapshot`, `auto_publish_carrier_updates=False` by default. |
| Archive | Nullable `archived_at`; archived journeys are hidden publicly and skipped by batches. |
| Lookup | Immutable random `JHZ-` Base32 code with 128 bits of entropy; not a B/L or customer credential. |
| Refresh | Last attempt/success, allowlisted failure, fingerprint, bounded current evidence, revision and claim/expiry metadata. |

Uniqueness is scoped to `(journey_key, source_adapter, search_reference, container_number)`, including an empty pending binding. One B/L may identify several physical containers. A physical container can appear on later journeys. Binding requires a sole unambiguous result or an explicit selected number present in the result; it never guesses from a vessel/IMO number.

Actual departure from the loading port can establish In transit; actual arrival at the discharge port can establish Arrived. Estimates, empty-return stages and undated text do not imply delivery/completion. Unknown/incomplete source information preserves prior accepted state and flags review.

## Dates and source evidence

A missing source time is SQL null. A present value has exactly these fields:

```json
{
  "raw": "2026-02-03 21:00",
  "precision": "minute",
  "designation": "estimated",
  "source_timezone": null,
  "normalized_instant": null
}
```

Precision is date/minute/second; designation is actual/estimated/unknown where permitted. Validation checks the calendar, precision and matching field designation. Source timezone must be explicitly supplied as an IANA name or UTC offset. An optional aware normalized instant must agree with the raw clock time; date-only values cannot claim an exact instant. The business timezone never fills a missing source zone.

Evidence is one bounded current object (maximum 8 KiB): adapter, matching fingerprint, aware observation time and source facts. It is private provenance, not a page archive or extraction-history table. Raw provider bodies, arbitrary exception payloads, B/Ls and evidence never enter the public snapshot.

## ContainerEvent: carrier and manual milestones

An event belongs to a container and has origin `carrier` or `manual`, optional source event/leg identity, location, raw text/status, source time/designation, bilingual title/detail, default-private `is_public`, stable deduplication key and timestamps. Containers with events are protected from deletion.

Deduplication is scoped to `(container, origin, dedupe_key)`. Stable carrier IDs identify source events. Actual milestones without an ID use canonical source facts/time; estimates use a stable leg/location/stage slot so a changed ETA updates the same event. Retrieval time/translations do not create new milestones. Revisited ports require a stable leg identity. Manual events get independent random identities; identical notes may intentionally be separate events.

## Refresh and public boundaries

Explicit refresh takes a short claim, performs bounded carrier/optional translation work outside the write transaction, then uses revision checks and atomic validation/save. Ordinary model edits increment revision. Missing source values do not erase accepted fields. Carrier and manual content remain independent. Direct SQL/bulk updates bypass model validation and are not an application write path.

First publication requires administrator review. Public views project only the validated approved snapshot and eligible visible events. Opt-in carrier auto-publication can update already-reviewed carrier facts, but cannot first-publish a journey, expose manual notes, accept unknown stages or approve new unreviewed Arabic labels. Private/archive gates apply even if a snapshot exists. Public pages perform no provider calls or business writes.

Production Redis provides shared fail-closed counters: login 10 attempts/300 seconds; public lookup 30 attempts/300 seconds. Counter failure returns 503; exhaustion returns 429. Only explicitly trusted proxy peers influence client identity. Public tracking responses use private/no-store caching, no-referrer and noindex metadata without exposing a code in canonical links.

## Migrations, recovery and tests

Original migrations remain unchanged. The retirement graph removes legacy models only after its historical recovery gate; `containers.0001_initial` creates the two tables and `0002_reviewed_public_tracking` adds publication fields without replacing the database. Historical helper functions serialized in migrations remain necessary.

Tests use temporary synthetic databases and mocked carrier/Groq responses. Keep migration, concurrency, publication privacy and exact SQLite/private-file restore regressions. See [local verification](LOCAL_DEVELOPMENT.md#test-without-owner-data), [admin workflow](ADMIN_GUIDE.md) and [matching recovery](BACKUP_RESTORE.md).

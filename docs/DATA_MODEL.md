# Shared container data model

The local 0.9.0 candidate now has exactly two business models in `apps.containers`: **Container** and **ContainerEvent**. Django users/groups/permissions, sessions, content types and ordinary admin logs remain. No customer, inventory, invoice, upload, job, extraction-history or custom audit model is added. Phase 3 provides manual Container administration and inline manual events. Phase 6 provides read-only public tracking through a separate strict approved snapshot.

## Container: one physical container on one journey

| Data | Rule |
|---|---|
| `journey_key` | Internal UUID grouping for a source journey. Several containers under one B/L may share it. A later journey uses a new key. |
| `search_reference`, `container_number` | Separate B/L/search and physical identities. Registration can leave the container number empty. It is never a globally unique container inventory. |
| `source_adapter`, `source_website` | Configured Sea Legend adapter/website only. No arbitrary administrator URL or model-controlled destination. |
| Equipment/route/vessel | Nullable equipment quantity; equipment type; origin/destination codes (loading/discharge) and separate English/Arabic labels; vessel and voyage. Missing text stays empty, missing quantity stays null. |
| `raw_status`, `carrier_status` | Keep raw status independently. Normalized choices: Needs review, Preparing, In transit, Arrived, Customs, Ready for collection, Completed, On hold. Default is Needs review. |
| Four source-time values | Separate actual/estimated departure and actual/estimated arrival; details below. |
| Manual fields | Independent English/Arabic notes and one nullable status override. Clearing the override returns to the carrier state. |
| Publication/archive | `is_published=False` by default; nullable `archived_at`. Public access also requires a valid approved snapshot. Archive/private state always hides the result. |
| Approved publication | `public_snapshot={}` initially; `auto_publish_carrier_updates=False` initially. Two additive fields, with no extra model. See the public boundary below. |
| Lookup | One immutable `JHZ-` Base32 code per container journey, generated from 16 random bytes (128 bits). Customers sharing that container use the same code. No customer-token table. |
| Refresh health | Separate attempt/success times, allowlisted safe failure code, SHA-256 source fingerprint and bounded current evidence. No page bodies or arbitrary exception messages in failure fields. |
| Concurrency metadata | Revision plus nullable UUID claim/expiry pair. Ordinary model saves increment revision. Phase 4 uses a short claim/expiry and revision check around explicit refreshes; provider work runs outside write transactions. |

The database enforces uniqueness on `(journey_key, source_adapter, search_reference, container_number)`, including the empty pending binding. Two different container numbers under one B/L/journey are allowed. The same physical container and B/L can appear on a later journey with a different key. Grouping is explicit; creating a new random journey key is a new journey, not an automatic duplicate check against all historical voyages.

`bind_container(available_numbers, selected_number=...)` accepts a sole unambiguous identity or an explicit choice present in a multi-container result. It does not save implicitly. After binding, mismatched identities, removal of the number and source/B/L reassignment fail ordinary model validation. Use a separate journey rather than silently reassigning it. Lookup/journey keys are immutable after creation. Raw B/L, internal IDs and source evidence have no public template path. `tracking_path('en'|'ar')` constructs the shared code-only result path. Missing, private, archived and unreviewed journeys return the same generic 404.

Phase 4 advances carrier state only from a retrieved actual departure at the loading port (In transit) or actual arrival at the discharge port (Arrived). Estimates, undated labels and empty-return stages never imply delivery/collection/completion. Unknown stages flag review; incomplete responses retain the prior accepted state. Manually copied dates do not establish carrier state. Manual overrides remain independent.

## Source time values

Source timestamps use bounded validated JSON values inside the two tables, avoiding a separate time/history model. A missing timestamp is SQL null. A present value has exactly these keys:

```json
{
  "raw": "2026-02-03 21:00",
  "precision": "minute",
  "designation": "estimated",
  "source_timezone": null,
  "normalized_instant": null
}
```

Supported precision is `date`, `minute` or `second`, matching the original text. Invalid dates and mismatched actual/estimated fields fail validation. No Django/business timezone is applied to the raw value. Source timezone accepts an explicitly supplied IANA name or UTC offset; an optional ISO aware instant must agree with that raw source clock time in the supplied zone. Date-only values cannot carry an exact instant. No instant is generated automatically, even when a timezone is supplied. Display and ordering rules must respect missing timezone/precision; event creation order is only the storage default, not a claimed chronological carrier timeline.

Accepted evidence replaces one JSON object, limited to 8 KiB: adapter, matching fingerprint, aware observation time and source facts. It is private provenance for the current extraction, not a page archive or independent history. Source evidence and source times are validated on ordinary model writes. Direct SQL, `QuerySet.update()` and bulk operations bypass model validation; future application writes must use validated model/service boundaries. Database uniqueness/quantity/claim-pair constraints remain effective for bulk writes.

## ContainerEvent: carrier and manual timelines

Each event belongs to a Container, with origin `carrier` or `manual`; optional source event/leg ID; raw status/text and location; explicit actual/estimated/unknown designation and nullable source-time value; English/Arabic title/detail; default-private public flag; stable deduplication key; and creation/update times. Container deletion is protected while events exist; archiving is preferred.

Deduplication is scoped to `(container, origin, dedupe_key)`:

- Carrier source event ID, when available, plus designation establishes identity.
- Otherwise an actual event uses canonical source status/location/leg, designation, original source time and raw text. Retrieval time and translated titles are excluded.
- An estimate uses its status/location/leg milestone slot. Changed ETA or estimate wording updates that existing event instead of creating another milestone. Revisited ports need the stable source-leg discriminator; do not invent one from retrieval order/time.
- Manual events receive their own random stable key; identical manual notes can be intentionally separate events. Origins, parent container and persisted milestone keys cannot be silently changed.

`ContainerEvent.objects.record_carrier(container=..., **facts)` is a model-level idempotent write helper, exercised with synthetic data. It accepts only carrier fact/text fields. It cannot set publication, edit manual events, change container notes or change a manual status override. This helper performs no retrieval or Groq calls itself. The Phase 4 refresh service invokes it within the atomic save after deterministic grounding and a claim/version check. Missing source values never erase known fields/events. Revisited estimate slots without stable leg identity fail rather than merge ambiguously. New events remain private in this helper; manual fields are excluded. The separate Phase 6 publication gate can mark only accepted eligible carrier milestones public inside the same refresh transaction for an opted-in published journey.

## Forward migration and retained history

`containers.0001_initial` depends on the completed historical retirement graph and creates only `containers_container` and `containers_containerevent`. No retained table is reset or deleted. Django creates the two models' content types and ordinary permissions without granting them to existing groups. The cleaned development database received this forward migration. `containers.0002_reviewed_public_tracking` adds only the default-off auto-publication flag and empty approved snapshot, preserving all original rows. Existing publication flags alone do not expose working facts: an administrator must review and create the first snapshot. Both additive migrations have been applied only to the authorized local development installation; production remains unchanged.

The historical `shipments`, `tracking` and `ai` app shells/migrations and serialized defaults remain solely for migration execution. They register no active models and must not be restored to satisfy old requirements. Old populated installations still require their separate guarded retirement/backup procedure. A new schema does not recreate retired business data or recover it through reverse migrations.

## Explicit refresh transaction boundary

`refresh_container(pk)` requires autocommit. A short transaction acquires one unexpired claim and records attempt time; provider work runs in a separate process group, killed/reaped after 18 seconds. The save rechecks claim, revision, archive and source identity, then atomically updates accepted facts/events and last-success time. End-to-end service work has a 24-second budget with bounded SQLite lock waits; a 27-second claim can recover an interrupted worker. This stays below the configured 30-second Gunicorn / 45-second proxy limits. No queue or new table is added.

Admin forms carry a revision token so an older form cannot overwrite a completed refresh. Manual edits during retrieval invalidate the refresh save. Safe failure codes and claim release never replace last-good facts/success time. Source evidence remains within 8 KiB, containing accepted field evidence, selected-milestone digest/count and cached port labels. It is not a raw-page archive. AI port transliterations are private review text; operational facts and fixed bilingual stage labels do not come from the model.

## Daily selection and attention

Phase 5 reuses the same service with `active_only=True`: eligibility is rechecked inside the claim transaction before any provider work. Archived journeys or a completed carrier state/manual override are excluded; publication and a past ETA never exclude an otherwise active journey. A status changed while provider work is in flight invalidates the version as before. The deliberate admin action retains its non-archived selection rule.

The batch command has an advisory OS lock in the shared Shipping data directory, separate from per-container claims. It holds no SQLite write transaction around network work. The lock inode remains after release; process exit/crash releases ownership, so do not delete it to resolve contention. Phase 5 added no model, field, job table or migration. Batch writes use the Phase 4 service; Phase 6 adds its approved-publication gate inside that same atomic save.

Admin attention is derived without writes: active claim, last failure, unknown-stage review, missing successful check or success at least 30 hours old. Archived/completed states explain exclusion. Last successful check stays distinct from attempt time. The timer package is inactive until separate Phase 8 activation; attention does not prove a schedule has run.

## Approved public boundary

The strict versioned JSON snapshot allows only reviewed container/equipment/route/vessel/voyage/status, four source-time values, bounded public events and separate approved-check/review times. It has at most 100 events and 256 KiB of encoded JSON. Oldest events are dropped when needed and the result explicitly says it shows recent published updates. English/Arabic manual notes, B/L, source evidence/raw status, error codes, internal IDs and arbitrary extra keys are excluded. Private event merge keys and snapshot bookkeeping remain server-side and are stripped from the template projection. Templates receive a deliberate display dictionary, never an unrestricted Container/Event or raw snapshot.

Manual confirmation creates or replaces the approved copy after the parent and inlines save. Ordinary working edits do not mutate that copy. The default-off auto gate requires an already approved, published, non-archived parent and a fully accepted refresh without review flags. Only facts present in that response and recognized dated carrier milestones may advance. Approved Arabic labels and manual event copies/status are preserved; private omitted working facts cannot leak through a partial refresh. An unreviewed manual-override change holds automatic publication. Unknown/undated stages, invalid data, provider or publication errors preserve the last-good public copy; the private/public save rolls back together on gate failure.

The public service queries only the filtered snapshot column and validates it again before projection. Malformed snapshots fail closed with generic temporary-unavailability feedback. It renders original source clocks/precision and explicit actual/estimated designation, without inferring zones or an exact date-only instant. Last successful check belongs to the approved copy, is labelled UTC, and becomes stale at 30 hours; an unknown check remains unknown. A new private success does not make an old public copy appear current. No public request calls a provider or writes business data.

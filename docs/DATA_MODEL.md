# Manual shipment data model — Phase 3

All operational records live in this application's independent SQLite database. Existing website records are not imported. Seven operational models and two Phase 4 integration models are implemented. AI drafts remain planned for Phase 5.

| Model | Relationship and purpose | Public exposure |
|---|---|---|
| Customer | Private name, company, contact, address and notes; shipments protect the relation from deletion | None |
| Shipment | Customer, internal order/bill, random customer reference, mode, approved bilingual route, status, dates, publication, delay/override reasons, archive and revision | Approved route, mode, status and known dates only |
| ShipmentItem | Shipment; bilingual description/unit, decimal quantity, optional SKU, cartons, decimal weight/volume; private by default | Only explicitly published description, quantity/unit and cartons |
| TrackingLeg | Shipment; ordered private carrier identifiers/numbers, registration and synchronization fields; unique shipment/sequence | None in Phase 3 |
| TrackingEvent | Shipment and optional leg; occurrence/receipt time, private source/location, approved bilingual text, mapped status, source and creator | Only explicitly published approved text, occurrence time and source |
| Document | Shipment; private random stored filename, original filename, SHA-256, type, size/pages, uploader and upload time | None |
| AuditEntry | Actor or integration identity, object/action, related shipment, timestamp, approved before/after values and changed field names | None |

A reference contains 160 random bits (`JHZ-` plus 40 hex characters), with a database uniqueness constraint. It is separate from bill/order/carrier numbers. Ordinary lookup uses POST and exact reference matching, requires published/unarchived records, never echoes the reference, and returns a deliberately constructed dictionary rather than a model. Production excludes synthetic records. Responses are no-store/noindex; no analytics are installed.

UTC is the storage timezone. `BUSINESS_TIME_ZONE` controls request date presentation (default Asia/Kabul); unknown ETA stays null. Decimal quantities/dimensions and positive-value validation prevent float rounding. Public routes/products/events require bilingual approved content. A leg on an event must belong to the same shipment; future event times over five minutes are rejected.

## Roles and writes

`setup_roles` maintains Shipping Operations (operational add/change/view plus publication, correction, archive, reference revocation and document download) and Shipping Read Only (view only). It creates no users or assignments. An owner assigns intended staff interactively through Users. Deletion permissions are not assigned to either group by default. Owners or explicitly authorized staff may delete eligible single records with a reason and confirmation; protected links and carrier/AI/audit history remain retained. See [admin deletion rules](ADMIN_GUIDE.md).

Permission checks run in views and write services. Published shipment edits and public product/event changes require publication permission. Archived records cannot be edited until restored. Shipment forms carry a revision token; a short atomic compare-and-update rejects stale saves. File inspection and storage run before the short metadata/audit transaction; failures remove the newly stored file. Broader competing-writer/load and recovery testing remains Phase 7.

Audit snapshots retain operational status/date/publication/quantity changes and field names, with private correction/deletion reasons when applicable. They exclude customer contact values, document bytes, raw source text, carrier numbers and customer reference capabilities. Audit rows survive deletion of an eligible archived shipment through a nullable link. Archive unpublishes the shipment, restore keeps it private, and reference revocation invalidates its old public capability.

Private files have no storage URL or media route. Authenticated, authorized downloads are audited, served as attachments with generic filenames and no-store headers. Inspection is bounded; see [document mapping](DOCUMENT_FIELD_MAPPING.md). This is restricted upload/download, not AI extraction or an antivirus service.

## Phase 4 additions

WebhookReceipt stores a unique body digest, event type, private normalized source payload, processing state/time and safe error; unnecessary provider contact/address/URLs are dropped. IntegrationJob stores deduplication key, operation, related leg or one-to-one receipt, state/attempts/due time, lease/token and safe diagnostic. No confidential payload appears in admin job/receipt screens or task arguments; task arguments contain only job IDs.

Shipment adds explicit carrier-coverage confirmation and status observation watermark. Legs add received/observed/sync/reconciliation state; provided carrier/number pairs are globally unique. Registered identities are retained. Events add a unique provider fingerprint and private original time information; carrier occurrence can remain null while manual events still require an aware known time. Carrier source fields are immutable while approved bilingual display/publication may be reviewed by staff.

See [17TRACK rules](17TRACK_INTEGRATION.md) for durable recovery, provider mapping and privacy boundaries. Existing website databases remain separate.

## Phase 5 — AIDraft

`ai.AIDraft` links one existing shipment to extraction/summary/message work with an optional private document or specific carrier event. Unique source-version/task/checksum dedupe key, private source/output JSON, fixed model/usage/latency metadata, durable attempts/availability/lease-token state and explicit reviewer/accepted changes support background processing and atomic application. Source images are temporary memory only. Whole-record child fingerprints catch newer manual/carrier edits. Accepted messages remain private; AI is absent from public serialization. Expiry clears private draft contents, retaining audit metadata; original documents/operational changes are retained. See [AI behavior](AI_BEHAVIOR.md).

## Phase 6 — AssistantRun

`ai.0002_operational_assistant` adds a separate private explanation outbox: requesting user, allowlisted scope, bounded projected result/source hash, output, safe model/usage/latency, unique confirmation key, fenced lease/attempts/recovery and retention. No shipment/customer/document foreign key or mutation payload exists. Runs are requester-only and source/permission-revalidated. Local searches create no work records; optional confirmation creates run/audit records only. Operational tables are unchanged by this migration. See [tools and permissions](AI_SEARCH_TOOLS.md).

## Release 0.8.1 — FileRemoval and retained audit links

`shipments.0003` adds a private, unregistered cleanup outbox containing only a unique storage filename and creation time. Document deletion records cleanup in the same transaction as metadata deletion; after-commit cleanup retries from the scheduled worker if storage fails. No file is removed on rollback. This migration also changes the audit-to-shipment link to SET_NULL so audit records survive eligible shipment deletion, and updates tracking-mode captions without changing stored values.

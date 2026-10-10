# SQLite limits and PostgreSQL migration plan

SQLite is currently one local persistent volume shared by one web service (production Gunicorn: one worker/two threads), one Celery worker with concurrency 1 and one Beat. Redis is dedicated and not a database replacement. WAL, 20-second busy timeout and short `IMMEDIATE` transactions are configured; `ATOMIC_REQUESTS` is off. Provider calls, document conversion and upload inspection stay outside write transactions. Optimistic revisions, unique constraints, durable jobs and lease tokens protect conflicts/idempotency; SQLite does not provide row locks through `select_for_update()`.

Phase 7 exercised three independent processes against an actual temporary SQLite file: 20 permission-aware admin saves, 20 signed durable webhook receipts, and 20 fenced AI job claim/completion pairs. A known 200 ms held write forced contention. All 60 operations completed without lock errors/lost writes; duplicate claims refused; the 20 carrier receipt jobs then processed; integrity/foreign keys/WAL/busy timeout passed. Observed operation timing in this run:

| Role | Median ms | p95 ms | Maximum ms |
|---|---:|---:|---:|
| Admin | 7.07 | 12.15 | 249.03 |
| Webhook | 10.32 | 193.23 | 222.51 |
| AI claim/completion | 8.46 | 13.73 | 455.07 |

This is a small synthetic contention check, not a production throughput benchmark. Every process still serializes writes. Reproduce with `scripts/verify_sqlite_contention.py` in a development image; it uses a fresh temporary directory, synthetic account/data and disabled providers, without opening `/data`.

## Migration signals

Investigate recurring `database is locked` failures or write latency approaching the 20-second timeout, webhook retries accumulating despite healthy Redis/provider access, a sustained increase in write volume or operationally unacceptable queues. Capture safe aggregate timing/status and private queue counts; do not log payloads/SQL/customer data. Agree service-specific latency/volume targets after observing actual traffic. Any second application host, higher writer concurrency requirement or need for independent database operation is a reason to move before scaling. Do not add workers as a SQLite remedy.

## Planned PostgreSQL cutover (not implemented or run)

1. Select supported managed/self-hosted PostgreSQL and a pinned compatible Python driver; define an independent Shipping database/role, private network/TLS, least privileges, backups/restore monitoring and credentials outside Git. Add environment-based connection configuration and remove SQLite-only `transaction_mode`/PRAGMA options for PostgreSQL. Keep initial worker concurrency conservative.
2. Run migrations on an empty staging database, then execute the permission/privacy, status, webhook/idempotency, AI lease/review, contention and end-to-end suites using actual PostgreSQL connections. Check unique constraints, JSON fields, timezone-aware dates/decimals, and nullable provider keys. Audit all locking assumptions; retain conditional revision/lease updates even where row locking becomes available.
3. Rehearse conversion on a verified SQLite recovery point plus matching private tree. Use a controlled Django ORM/data export/import process covering auth/permissions/groups, content types, sessions (or deliberately revoke sessions), shipments/audit/files, tracking receipts/jobs and AI drafts/assistant runs. Preserve relationships/IDs and reset sequences; handle content-type/natural-key relationships explicitly. Avoid blindly importing system-generated permission/content-type rows over freshly migrated ones. Retain file names/checksums, private file storage and capability references. Export only to a private encrypted location; never Git.
4. Verify per-table counts, foreign keys, timestamps, decimals, retained audit/review history, all private hashes, safe public summaries and authorized downloads. Test restart/recovery and a clean PostgreSQL backup/restore. Keep external integrations disabled for rehearsal so restored work cannot trigger charges or duplicate actions.
5. During an agreed maintenance window pause requests/web/worker/Beat/external writers; take and verify a final matching SQLite/files backup; complete the rehearsed import; change connection settings; run migration checks once. Start web, validate, then one worker/Beat. Reconcile durable work with existing fencing/idempotency; inspect pending outbound requests before releasing them. Measure latency/errors against agreed targets.
6. Keep pre-cutover code/config and SQLite/files recovery point private and immutable. Establish a rollback deadline. Before accepting new PostgreSQL writes, rollback may restore the prior configuration/point. After new writes, switching back would lose them; pause and reconcile/export those changes explicitly. Do not run two databases as independent writable authorities. Only retire SQLite artifacts after owner approval and a verified PostgreSQL recovery drill.

The initial release remains SQLite. PostgreSQL dependencies, services, schema conversion and production deployment are outside Phase 7.

# AI behavior and private review

Phase 5 implements extraction, summaries and message drafts. Phase 6 adds [fixed operational searches/data-quality checks](AI_SEARCH_TOOLS.md) and optional private background explanations. Groq runs server-side in background jobs. Public lookup only reads operational data and never invokes or displays AI drafts or assistant results.

## What is sent and when

Uploading a bill does **not** send it externally. Authorized staff open the AI request action, select a shipment/task/document or optional carrier event, review the disclosure and explicitly confirm sending it to **Groq**. No bulk/automatic document processing is configured.

Extraction sends text from the selected private document. Text-poor PDF pages are actually rendered by PDFium to bounded JPEG images, then sent as base64 image inputs to the separate vision model. PDFs are never passed directly as image URLs. Documents can contain private business/contact data: staff must consider the full selected document before consent. History tasks deliberately omit customer contacts, internal notes/order/bill/carrier numbers and the private JAHEZ access reference. Carrier translation explicitly includes that selected carrier event's necessary original text; inspect it before authorizing. Requests have no tools, database access, remote image URLs or sender integration.

Both provider models are **owner-configured**, with no baked-in model fallback. Official references checked 2026-10-09: [supported models](https://console.groq.com/docs/models), [structured outputs](https://console.groq.com/docs/structured-outputs), [vision/base64 input](https://console.groq.com/docs/vision), [Python SDK](https://github.com/groq/groq-python). Current documented text candidates include `openai/gpt-oss-20b` and `openai/gpt-oss-120b`. The documented vision candidate `qwen/qwen3.8-27b` is listed as a **preview** model; availability/account access and quality need separate live testing. Recheck before configuring; no model has been live-tested here.

## Private setup

Set these only in the appropriate private `.env.dev`/`.env.prod`, never in chat or committed source:

```dotenv
GROQ_ENABLED=true
GROQ_API_KEY=<your-private-key>
GROQ_TEXT_MODEL=<currently-supported-text-model>
GROQ_VISION_MODEL=<currently-supported-vision-model>
GROQ_TEXT_OUTPUT_MODE=schema
GROQ_VISION_OUTPUT_MODE=json
GROQ_MAX_TOKENS=4096
GROQ_VISION_MAX_TOKENS=512
GROQ_RETENTION_DAYS=30
```

Text `schema` mode requests strict structured output; all nested fields are required and extra properties forbidden. Vision defaults to JSON-object mode followed by the same local Pydantic validation; use `schema` only after checking that model's image/schema combination. Modes accept `schema` or `json`; no silent model/version fallback or tool use. Configured readiness is not proof of account access or factual accuracy. Keep `GROQ_ENABLED=false` for local demonstrations or unavailable service. Restart/recreate only this project's web/worker/Beat after environment changes:

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml up -d --force-recreate web worker beat
```

Text and vision response budgets are separately configurable, each bounded to 512–8192 tokens. `GROQ_VISION_MAX_TOKENS` defaults to `GROQ_MAX_TOKENS` when absent. Choose budgets according to your provider account capacity and document size; incomplete output is rejected. A small budget can truncate multi-item bills. Validate larger documents privately before enabling extraction.

## Limits, failures and durability

- Existing uploads accept inspected plain PDF (1–40 pages), single-frame PNG/JPEG, at most 5 MiB. AI extraction is narrower: **at most five pages**, 24,000 total extracted characters, 10,000 per page. Split larger documents or use manual entry. Encrypted/active/external-action PDFs, malformed/changed/oversized files fail safely.
- Inspection/conversion runs in a subprocess with 10-second CPU/768 MiB address-space limits and a 15-second parent timeout. Rendered pages stay in memory: at most 1.5 million rendered pixels/page, 1400-pixel longest JPEG edge, 650,000 bytes/image. Base64 is discarded after processing, never persisted in the draft or logs. Text below 40 nonblank characters/page invokes vision; mixed files include digital text plus scanned-page images. A visible source page link supports manual visual verification.
- Minimal history has at most 20 recent received events and 25 items; a 4000-character event and 120,000-byte source limit. Truncated/missing/stale history and unknown ETA warnings are explicit. Raw Chinese snippets are preserved; bilingual proposed descriptions/writing remain drafts.
- Groq SDK 1.7.0 / Pydantic 2.14.0 / pypdfium2 5.14.0 and transitive dependencies are hash-locked. Actual SDK serialization was tested with a local mock HTTP transport. SDK base host is fixed `https://api.groq.com`; SDK emits `/openai/v1/chat/completions`. TLS verification is enabled, redirects/proxy-env disabled, no custom model-provided host/URL or tools.
- Connect timeout 3 seconds, read timeout 30 seconds, response elapsed guard 40 seconds/128 KiB, completion tokens clamped 512–8192. Global Celery soft/hard limits remain 60/90 seconds. Client retries disabled; durable application attempts capped at three. Shared cache allows one request per two seconds; cache failure defers safely. Backoff 60×2^attempt seconds (max one hour) plus 0–15 seconds jitter; provider rate/outage and invalid output retry within this bound. Permanent account/configuration failures require review. Cache/rate deferrals do not consume provider attempts, but retention still bounds job lifetime.
- AIDraft is both durable work record and private proposed result. Commit before dispatch; broker publication failure preserves pending work. One-minute Beat recovery dispatches up to 25 due jobs, with 120-second leases and worker tokens that fence stale results. Recovery never keeps a write transaction open during conversion/network I/O. No Redis result backend stores document outputs.
- Visible states/errors use controlled safe wording; no provider exception body, raw prompts, keys, contact data or tracebacks in ordinary SDK/worker logs. Audit records store decisions/field names, not entire outputs.
- Retention default 30 days, configurable 1–90. Recovery expires overdue work/results and clears private source/output/accepted-change contents while retaining task/model/usage/review/audit metadata. Uploaded source documents and accepted operational records follow their existing retained-record lifecycle; expiry does not delete them. Separate backups may retain older contents according to the later backup policy. Summary warnings/proposals can contain source-language text; they are displayed escaped, never executable HTML.

## Source validation and staff decisions

Pydantic rejects extra fields/type coercion, oversized proposals, missing/unknown source citations, invalid quantities, duplicate field proposals, and unsupported mutation fields. Digital snippets must match an included source page. Scanned snippets are visually transcribed proposals: a valid page citation cannot establish that handwriting was read correctly. New numeric claims in writing are rejected unless present in its cited records; alphabetic/semantic factual correctness still requires review. Schema validation and prompt-injection instructions never confer permission or accuracy.

The provider system instruction explicitly treats documents/messages as **untrusted data**. Staff and server retain all authority; models cannot query, run SQL/Python/shell, call tools, register tracking, publish, or send messages. Source links/times support review, not a guarantee against hallucinations.

Extraction applies only individually selected reviewed values: internal order/bill number and bilingual route labels can fill empty values; selected validated products append **privately**. Existing nonempty different values require intentional correction in the existing shipment editor. Invoice/container/carrier numbers remain separately labeled suggestions and cannot automatically become tracking references. Customer records, status, arrival/delivery dates, ETA, locks, carrier coverage/registration and publication are excluded. This workflow updates the selected existing shipment; creation of a customer/new shipment is intentional manual work first.

Application rechecks staff permissions, archive state and a complete private hash of current shipment/children (items/events/legs/document checksums). Any newer operational edit invalidates the draft, including child edits. Fields/items/decision/audit save atomically. Rejecting stale proposals remains possible. Explicit requests after rejection/expiry create a fresh deduplicated draft while retaining the earlier decision history. Applying twice, an already-applied identical document checksum on the shipment, duplicate bill/order on another shipment or duplicate selected item fails safely. Hash/version checks do not replace document checksum verification; both exist.

Writing has editable English/Arabic statements and fixed citations. Approval saves private text only; no automatic event publication, email, WhatsApp or SMS. Review requires source permissions; document drafts additionally require private-document view/download. Read-only staff can see authorized history drafts, but cannot request/retry/approve/apply; they do not see extraction contents without private download permission. Request permissions are rechecked by the worker before and after provider work.

## Demonstration and live verification

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python manage.py seed_ai_demo
```

Creates private **DEMO-AI** with fictional digital/scanned PDFs and four labeled local drafts. Actual extraction/rendering runs locally; output proposals are deliberately invented fixtures, **not live AI output or OCR recognition**. No account/password/API request is created. Production rejects the command and cannot process/apply DEMO work. The seed is idempotent for the current source version and retains reviewed history; rerun after source edits to create current review fixtures without resetting old decisions. Public DEMO visibility remains development-only.

The browser review approved one edited local message and applied one digital item privately. That makes the other original suggestions stale, as intended; refreshed current fixtures are available. The repeated fictional `DEMO-BILL-001` also occurs in the earlier manual demo: selecting it for another shipment deliberately triggers the duplicate-identifier guard. For a clean extraction application review, select the scanned packing-box item or another unused synthetic field, not the duplicate bill.

Live tests require privately configured keys/models and an explicitly chosen appropriate source. Verify model access and synthetic extraction before handling customer data. Chinese/handwriting recognition, complex bills, factual quality and real carrier/webhook acceptance require separate testing on the intended deployment.

Run the explicit development-only setup check when authorized (it makes live API calls with invented content):

```bash
docker compose --env-file .env.dev -p jahez-shipping-dev -f compose.dev.yml exec -T web python scripts/verify_provider_setup.py --live-synthetic-check
```

Use `--only-vision` after the flag to repeat only the image check. The script reads 17TRACK quota without registering a shipment, reports safe numeric diagnostics and never prints keys/provider bodies or saves results to the database. Health/readiness does not run this check.

Phase 7 adds `GROQ_MAX_IMAGES` (default 3; configurable 1–3). Requests beyond that count are rejected locally before Redis outbound-slot allocation or SDK creation, with a bilingual splitting instruction. This follows the selected [Groq vision model's documented three-image request limit](https://console.groq.com/docs/vision), checked 2026-10-09. The five-page document converter limit still applies to digital text; it is not permission to send five scanned images in one model request. Larger scan quality and the owner's original bill remain unverified. Phase 7 uses synthetic/offline provider fixtures only; it makes no new live provider request.

Maintenance prevents new claims and reconciliation until the verified matching snapshot is complete. See [privacy/retention and recovery operations](OPERATIONS_RUNBOOK.md).

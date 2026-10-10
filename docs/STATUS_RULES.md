# Manual status and publication rules — Phase 3

Normalized states are created, received at China warehouse, preparing shipment, departed, in transit, customs clearance, arrived at destination, out for delivery, delivered, on hold, returned and cancelled. The labels are reviewable with operations.

The shipment overview is authoritative. Staff explicitly update its status; timeline events do not automatically update it. Events can therefore preserve older history and individual package milestones without regressing a delivered shipment or declaring every package delivered. Forward changes may skip stages. Delivered, returned and cancelled are terminal; changing a terminal state or moving backward requires correction permission and a recorded correction reason.

Manual tracking requires no carrier registration or keys. Hybrid currently permits manual work and a recorded customer-facing status lock, alongside verified provider ingestion. API/hybrid modes can now request Phase 4 carrier registration when configured; API mode can be selected without making manual startup depend on credentials. Changing a locked status or releasing its lock requires correction permission and a correction reason; creating a lock requires the private override reason. Provider fields show actual registration/receipt/sync state.

For an existing shipment with more than one tracking leg, marking the whole shipment delivered requires the explicit all-packages/legs confirmation. The form and write service both enforce it. One package event never completes the whole shipment. Phase 4 aggregation follows the explicit [17TRACK rules](17TRACK_INTEGRATION.md); all-leg delivery additionally requires confirmed complete package coverage.

## Delay and dashboard calculations

Delay is separate from normalized status: a staff-confirmed delay with a required reason, or a known ETA earlier than now for an active nonterminal shipment. Missing ETA, missing updates and synchronization failure do not imply delay. Delivered/returned/cancelled and archived shipments are excluded.

Dashboard counts query active database records:

| Card | Included states |
|---|---|
| Pending | created, warehouse, preparing |
| In transit | departed, in transit, customs, arrived, out for delivery |
| Delivered | delivered |
| Attention | nonterminal and confirmed delay, overdue known ETA, or on hold |

Attention can overlap another card; these are not percentages. Recent shipments show the six most recently updated; attention shows at most five. Counts/rows require shipment-view permission. Provider health reports disabled/missing-key/configured-unverified state; successful sync metrics exclude DEMO fixtures.

## Publication and control

Shipment, product and event visibility are separate; records default private. Public lookup requires an active published shipment; its products/events additionally require their own public flag and approved bilingual content. ETA is labeled estimated; actual arrival/delivery are distinct optional timestamps. Unknown values stay unknown.

Archive, restore and reference revocation use a CSRF-protected confirmation POST. GET does not mutate. Archive immediately removes public lookup access and preserves history/files. Restore leaves publication off. Revocation replaces the random customer reference; audit does not store either capability. Read-only staff cannot perform these actions, upload, publish or change statuses.

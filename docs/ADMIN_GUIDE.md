# Administrator workflow

Open `/en/admin/` or `/ar/admin/`. Create your intended administrator interactively using the [local](LOCAL_DEVELOPMENT.md) or [production](DEPLOYMENT_VPS.md#change-private-settings-or-create-an-administrator) command. There is no default login or automatic role assignment. Staff status alone grants no container permissions; Users/Groups appear only with the corresponding Django permissions.

## Add a container journey

1. Choose **Containers → Add** and enter the carrier B/L/search reference.
2. Keep the physical container number empty until the carrier identifies one, or explicitly select the intended number from a multi-container result.
3. Keep B/L, container, vessel and voyage distinct. Register a new journey for a later voyage rather than rebinding an existing journey.
4. Save privately. A generated `JHZ-...` code belongs to this journey; everyone sharing that container uses the same public code.

Source identity is fixed after binding. Changing a B/L/container/source means a separate journey. The two-model [data rules](DATA_MODEL.md) explain identity and date precision.

## Refresh and review

Use **Refresh now** for one explicit bounded carrier/Groq attempt. Check the returned container identity, route, vessel/voyage, actual versus estimated dates, carrier status and last-success time. Review Arabic labels before approving them. HTTP success alone does not establish that extracted facts are correct.

The adapter uses a fixed Sea Legend website interface, not an arbitrary URL. The interface is undocumented and can change or become unavailable; unattended-use permission and long-term availability are not established by a successful sample. Groq only proposes bounded port-label translations; it does not browse, choose facts, change identities or determine delivery. Provider requests are explicit admin/batch actions, never public lookups.

A failed refresh keeps previously accepted facts, manual edits and the public snapshot. Inspect the allowlisted failure/attention message and last attempt versus last success. Unknown stages require review. The provider operation has an 18-second hard bound; a concurrent edit/claim prevents a stale result from overwriting newer work.

## Manual correction and fallback

When the source is unavailable, copy verified information into the manual English/Arabic fields and add a manual event if needed. Distinguish actual/estimated/unknown dates and retain their original precision. Use a manual status override deliberately; clearing it returns to the carrier state. Private notes and newly added manual events are not automatically public.

A carrier date without a source timezone remains unknown. China business display time (`Asia/Shanghai`) must not be assumed to be the source clock's timezone. ETA passing does not establish arrival, collection or completion.

## Publish and share

1. Review the intended English/Arabic public details and event visibility.
2. Confirm first publication in admin. This creates a strict approved snapshot, not a live view of private working fields.
3. Open the tracking link and verify it in both languages before sharing it.

Public lookup accepts only the JAHEZ code. It does not accept a B/L or physical-container number. Missing/private/archived/unreviewed results share generic feedback. Codes grant shared access; keep operational captures private and avoid analytics that collect result URLs.

**Automatically publish validated carrier updates** is off by default. Opt in only after reviewing that real journey and its first publication. It cannot first-publish a private record, expose manual notes/new private events, accept unknown statuses or approve unreviewed AI labels. Unknown/uncertain changes preserve the old public copy and flag admin attention. Manual changes still need deliberate review/publication.

The public last-success time refers to the approved snapshot. A private refresh does not make an older public copy current. Public information is marked stale after 30 hours; this is milestone tracking rather than continuous GPS.

## Archive and daily checks

Archive hides the result immediately while retaining the journey/events. Prefer archiving to deletion; a container with events is protected from deletion. Archived or completed journeys are skipped by the batch. An old ETA alone does not stop checks.

Daily refresh is an optional host timer, configured separately from publication opt-in and business display timezone. Review its one-shot/schedule setup in [production](DEPLOYMENT_VPS.md#refresh-commands-and-optional-daily-schedule). Use the admin attention filter to inspect failures/stale successes; a timer being enabled is not proof a scheduled run succeeded.

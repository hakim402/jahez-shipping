# Minimal administrator foundation

The cleanup candidate preserves Unfold login, Django staff/superuser authentication, password validation, CSRF, sessions and ordinary admin logs. `/en/admin/` and `/ar/admin/` show a localized preparation message. Users and Groups are the only registered models; their screens still require the corresponding Django permissions. No sample admin credentials or automatic role assignment exists.

Existing administrator hashes, required permissions and sessions are preserved by the tested schema upgrade. Retired business permissions/content types are removed deliberately; old group names remain without granting replacement powers. `setup_roles` reports this policy and does not create accounts, business groups or assignments.

Customer/shipment/product/document controls, AI tools, carrier health, metrics, custom audits and seed commands have been removed. Container registration/import/refresh interfaces will require a separately approved phase. The candidate does not claim to show current container data.

Use [isolated review](LOCAL_DEVELOPMENT.md) now. Do not create users or run the destructive migrations against owner data in this cleanup phase. Production/admin acceptance remains separate from synthetic test authentication.

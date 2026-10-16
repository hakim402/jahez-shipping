# Current data model and publication state

The 0.9.0 candidate has **no active business models**. Django auth users/groups/permissions, content types, sessions, ordinary admin logging and migration metadata remain. It does not replace the retired custom audit system.

Historical `shipments`, `tracking` and `ai` app labels remain installed only for migration execution. Their `models.py` files register no models; there are no admin screens, tasks, routes or services for them. The serialized `public_reference` callable survives only because the original migration imports that exact path. It is not a current tracking feature.

The retirement graph guards populated installations first, deletes dependent AI tables, then carrier tables, then shipment child/parent tables, and removes only retired content types/permissions. Required Django permissions, administrator password hashes, sessions and admin history remain. Old group names/assignments are not repurposed or granted new powers; obsolete business permissions are removed. An ordinary admin log entry referencing a retired content type remains with a null content type.

The twelve retired table names and dependency/verification evidence are in the local-only cleanup inventory. Do not reverse these migrations expecting data to return; use the matching pre-cleanup database/private-file backup and old source/image.

## Status and publication

No container status/publication implementation exists yet. The homepage keeps its visual layout but displays an English/Arabic unavailable state with disabled controls. There is no old reference lookup, upload/download, carrier webhook or AI workspace endpoint. Page requests render saved branding only; they cannot initiate retrieval or paid AI calls.

Future identifier, status, archive/publication, date and event rules are [design only](CONTAINER_DESIGN.md). No new model/migration, scheduler or source retrieval is implemented in this phase.

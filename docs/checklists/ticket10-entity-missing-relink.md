# Ticket 10 — Entity missing and Relink entity runtime checklist

Status: not run

This checklist requires a separately authorized MTA/Map Editor runtime. It is
not executed by repository implementation or review work.

1. Create an active Spatial Link, perform a map edit in the stock map so the persisted entity is
   absent, save/reload the map, and confirm F7 shows `Entity missing` while the
   link and metadata remain.
2. Destroy or unstream only the Runtime Instance and confirm F7 reports runtime
   unavailability without changing the persistent state to `Entity missing`.
3. In F7 select the missing record and an unlinked target from another loaded
   map; repeat with different `interior` and `dimension` values.
4. Verify the Relink preview compares the source metadata, then confirm and
   verify the target keeps its own map/entity IDs while receiving the Spatial
   Link, name, Entity Tag, radius and `Show radius`.
5. Cancel the preview, force a failed transaction, restart the resource, and
   verify no duplicate link and consistent source/target state.
6. Exercise the Pick Entity path when available and verify it obeys the same
   unlinked-target and cross-map rules.

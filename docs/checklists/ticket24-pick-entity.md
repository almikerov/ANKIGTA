# Ticket 24 — Pick Entity manual checklist

Status: not run

This checklist covers acceptance only a human can observe. Automated checks
verify everything reachable programmatically; nothing here is verified by
driving the GUI.

## Scenarios

- Open F7, enter Pick Entity, confirm movement/look remain available while
  shooting, vehicle entry and ordinary interactions are blocked.
- Aim at a managed object, vehicle and ped; confirm the first visible target is
  selected and a wall causes an occlusion rejection.
- Aim at an unmanaged element, an unloaded element and an element from an
  outside-loaded-map resource; confirm each reports its specific rejection.
- Exercise the streaming boundary with the target just inside and just outside
  the streamed set; confirm distance is not an ANKIGTA-imposed bound.
- Verify a destroyed or stream-out managed Runtime Instance; confirm it is unavailable
  to the raycast and remains reachable only through the F7 list.
- Press Esc, select a target, submit an invalid target, and exercise resource stop;
  confirm cursor, movement/look, shooting, vehicle entry, interaction and
  camera/input state exactly match the state before the modal opened.
- Use Pick Entity as the Relink entity target source; confirm the server
  eligibility checks are identical and no unmanaged target can be relinked.

Expected evidence: F7 screenshots/logs for each outcome, target map/entity IDs,
and a before/after input-state capture.

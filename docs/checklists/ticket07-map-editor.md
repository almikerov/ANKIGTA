# Ticket 07 Map Editor checklist

Status: not run

This checklist is intentionally manual. It must be executed only in an
explicitly authorized MTA/GTA runtime validation task.

- [ ] Open the matrix map and assign object, vehicle and ped; stock Save; read
      back each identity; close and reopen; move and edit model; verify the
      Spatial Link remains on the persistent IDs.
- [ ] Clone (clone) an entity and save; verify the duplicate entity ID is visible,
      both records are blocked from study, and no `.map` is rewritten by
      ANKIGTA.
- [ ] Use `copyResource`, `renameResource`, and `Save As`; choose
      Original / renamed for a rename and verify the map identity and Spatial
      Link survive.
- [ ] Repeat copy/resource collision and choose New copy; stock Save must
      persist new map/entity IDs and must not transfer the Spatial Link.
- [ ] restart/reload with an unsaved pending link; verify it is discarded.
- [ ] Exercise ambiguous owner recovery and `Проверить ещё раз`; leave failed
      read-back pending with stock Save/Editor recovery guidance.

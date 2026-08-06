# 09 — Linking during a play-test

**What to build:** an object the player is pointing at is linkable, even when
the editor is play-testing the map it lives in.

Reported item: `The entity was not changed: editor_play_test_map` on Link.

## Both copies exist at once, and the player is standing in the wrong one

Measured on the owner's running server with `editor_test` running. Every
authored element exists **twice**:

```
object (vgsSstairs04_lvs) (2)  ->  owner=editor_main  dimension=200
object (vgsSstairs04_lvs) (2)  ->  owner=editor_test  dimension=0
vehicle (Sentinel) (1)         ->  owner=editor_main  dimension=200
vehicle (Sentinel) (1)         ->  owner=editor_test  dimension=0
```

`editor_main` holds the map being edited, in the editor's working dimension.
`editor_test` holds the play-test copy, in dimension 0 — which is where the
player is while testing, and so is the copy they are pointing at.

`World.owningResource` walks the element's ancestors and answers `editor_test`,
`isPlayTestResource` says yes, and adoption refuses. **The refusal is correct
about the element and wrong about the intention.** The player is editing a map,
pressed Test, is looking at their object, and wants to link it.

## What ticket 02 already decided, applied one place further

02's follow-up settled that **a map is its identity, not the name of the
resource it loads from**: one document answers to `editor_dump` while unsaved,
`editor_test` while play-testing, and its own name afterwards, while the
`ankigtaMapId` written inside it never changes. Row matching was moved onto
identity. The *adoption* path was not.

The same rule finishes it: a play-test element is not a different entity, it is
the same entity seen from inside the test. It carries the same `id` and its
document carries the same `ankigtaMapId` as the working copy. Adopt against the
identity, and record the entity against the map that owns it — not against
`editor_test`, which will be rewritten on the next Test press.

**Refusing is still right where there is nothing else.** A play-test whose
document carries an identity no working copy answers to has no other copy to
adopt against, and a link made there would still point at something that stops
existing. That case keeps `editor_play_test_map`, and the reason should say
which of the two situations it is.

## The message, separately

`The entity was not changed: editor_play_test_map` puts a machine token in front
of a player. Whatever this ticket decides the behaviour is, the refusal a person
reads should be a sentence.

**Blocked by:** None.

**Status:** ready-for-agent

- [ ] An object linked while the editor is play-testing is adopted, not refused
- [ ] It is recorded against the map that owns it, not against `editor_test`
- [ ] The same object linked outside a play-test gives the same Map Entity
- [ ] Linking the working copy and the play-test copy does not make two rows
- [ ] A play-test document whose identity no working copy answers to is still
      refused, and says why in words a player can read
- [ ] No refusal shown to a player is a bare token
- [ ] The stubs know that a play-test duplicates every element into another
      resource and dimension, so this cannot pass in tests and fail in the game

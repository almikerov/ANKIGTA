# 05 — Loaded is what decides, not a switch

**What to build:** the loaded map decides what is in play. The setting that
decided it instead goes away — and so does ANKIGTA's habit of adopting entities
out of the Map Editor's scratch resources.

The map that is running gives the set of cards; `Review mode` chooses within it.
Two questions, asked in that order, and only the second is the player's to answer
twice.

**The switch was answering a question nobody asked.** What it produced was a row
per map in Settings, named by whatever the map is called in the store — which is
how `editor_dump` and `editor_test` came to be offered to the player as things to
switch on and off.

**But it cannot simply be deleted, because it is currently the only thing
narrowing anything.** Study walks every stored Spatial Link and takes every one
whose card is live, so a map that is nowhere in the world contributes its cards
just the same. Removing the switch alone would widen study to every map ANKIGTA
has ever seen.

So the rule the switch stood in for becomes the actual rule: a Map Entity takes
part when its map is loaded. Which maps those are is a question the panel already
answers, to scope the Map Entity list to the map in front of the player; study
asks the same question of the same answer rather than growing a second one that
can disagree with it.

**What follows the same rule.** The session's card set, the counters, the spatial
candidates and the Text Label set. Each is narrowed by the switch today; each
narrows by what is loaded instead. The Text Label set's refusal to label an
entity on an excluded map, and the `map_excluded` reason it reports to the panel
row, go with the switch — an entity on a map that is not loaded has no Runtime
Instance to carry a label anyway.

**Unloading a map still removes nothing.** A Spatial Link is not the map, and
loading the map again brings the link back exactly as it was.

**The scratch maps are the other half.** `editor_dump` and `editor_test` are what
the stock editor calls the throwaway resources it dumps into and play-tests from.
They ended up in ANKIGTA's store as maps, and an entity adopted out of a play-test
is a Spatial Link pointing at a copy that stops existing when the test does.
Hiding the switch does not put them back — they are still in the entity list and
the links against them are still links to nothing.

Not adopting from them again is the fix. What to do about the ones already stored
is a decision, and it is not deletion: a Map Entity carries a link the player made
deliberately and may have made against an object they still have. Report them as
what they are and let the player decide — the entity list already knows how to say
a Map Entity is missing and how to relink it.

**ADR 0025 stays.** The editor is used as it ships and nothing is written into its
resources. Knowing which of its resources are scratch is reading it, not changing
it.

**Blocked by:** 01, 03.

**Status:** ready-for-agent

- [ ] Settings offers no per-map row, and no way to exclude a map
- [ ] A Map Entity on a loaded map is in play
- [ ] A Map Entity on a map that is not loaded is not
- [ ] Loading that map again brings its links back untouched
- [ ] Counters, spatial candidates and Text Labels all narrow by the same
      answer, taken from one place
- [ ] A database holding stored per-map preferences opens without complaint, and
      stops carrying them
- [ ] The panel row no longer has a `map_excluded` state to report
- [ ] An entity is not adopted while an editor scratch resource owns it
- [ ] Working in the Map Editor normally still adopts from the map being edited
- [ ] Entities already stored against a scratch map are identifiable as such
- [ ] The player is told, rather than having rows silently deleted
- [ ] A Spatial Link made against one can be relinked or removed deliberately
- [ ] Nothing is written into any editor resource
- [ ] `Active Map Set` in CONTEXT.md no longer mentions the switch

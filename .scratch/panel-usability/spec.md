# Panel usability

Twenty-two observations from using the panel, folded into five tickets.

They divide by what they are, not by where the code lives:

- **01** is a bug that blocks judging anything else — no decks, no cards.
- **02** is the Map Entity list: what it contains, once each, described
  readably, kept current.
- **03** is everything the interface says and everything a setting does.
- **04** is finding cards, and saying which cards a session uses.
- **05** is one new way to study: the card as text on the object.

## Answers given while breaking this up

**"Unavailable — Runtime"** was the Runtime Instance state: whether the element
exists in the world right now and is streamed in around the player. The column
goes; the state moves into the link column, so a missing object still reads as
missing rather than as an ordinary row.

**"Maximum speed"** was read as a floor and is a ceiling: cards do not open
while the player is moving faster than it, so a card does not appear while
driving past. The behaviour stays; the name changes to say it.

**"Maps included in study"** is whether a map's entities take part in the study
session at all. **"Allow early review"** is whether cards that are not yet due
may be used — a boolean whose name describes neither state, which is why it
becomes a three-valued Review Mode.

**Every object appearing twice** was found in the code while writing these: the
world-candidate scan has no `edfIsRepresentation` guard where
`validatePickEntity` has one, so with the Map Editor running each object is
listed as itself and as the editor's representation of itself.

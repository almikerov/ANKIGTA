# 03 — The interface says what it means, and settings take effect when set

**What to build:** the panel's words, its settings and its connection screen
stop needing explanation.

Covers the reported items 4, 5, 6, 8, 9, 10, 12, 13, 14 and 17.

**Words.** `Filter` becomes `Search`. Every `Close` becomes an `X`. `Take me
there` becomes `Teleport`. `Mute game world` becomes `Mute world while
reviewing`. `Close after rating` becomes `Close cards after rating`.

**Settings apply when changed**, not on a separate confirmation. A value the
schema refuses still says so on its own row and is not applied — refusing is a
result, and the point of applying immediately is that the result is immediate
too.

**Language comes first and the companion port second**; the rest follows.

**Defaults and names that were wrong.** The activation delay defaults to `0`.
The speed setting keeps exactly the behaviour it has — cards do not open while
the player is moving faster than it — and is renamed to say so: `Open cards
when speed lower than:`. It was read as a minimum by its old name, which is the
whole reason to change it. Its default becomes `0`, which with this meaning is
"never open while moving"; if that is not wanted, the default is the thing to
argue about, not the rule.

**The connection screen is a port, a token and the current state.** The token
is already filled in. Everything else on that screen goes.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Every renamed control reads as specified, in both languages
- [ ] Changing a setting takes effect with no further action
- [ ] A refused value is reported on its row and is not applied
- [ ] Language is the first setting and the companion port the second
- [ ] The activation delay defaults to 0
- [ ] The speed setting is named for what it does and behaves as it did
- [ ] The connection screen offers a port, a token and the connection state

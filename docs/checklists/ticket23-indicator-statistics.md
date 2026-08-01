# Ticket 23 — Indicator and statistics manual checklist

Status: not run

Counting rules and indicator selection are covered automatically. What needs a
human is whether the HUD is readable and whether the marker points where the eye
expects.

## Scenarios

- Link one card to three entities. Confirm the HUD counts it once, not three
  times, and that `Total` equals `New + Learning + Due + Early`.
- Confirm `Early` is visible and reads 0 with early review disabled, and starts
  counting once it is enabled.
- Suspend, bury and delete linked cards in Anki; set one entity to Pending Map
  Save; exclude a map from study. Confirm each drops out of the counts.
- Rate a card and confirm the counts refresh without restarting study. Repeat
  after a link change, a map load/unload and a session rebuild.
- Set the indicator to each mode in turn. Confirm: sphere + minimap blip;
  minimap blip only; nothing. Confirm the default is nothing and that no
  sphere-only option exists.
- With the next card linked to several entities, confirm only the nearest
  reachable one is marked.
- Stand where the indicator sphere coincides with a real Activation Zone.
  Confirm one emphasized or pulsing sphere is drawn, not two overlapping, and
  that the Activation Zone's own radius is unchanged afterwards.
- Move to a different interior and dimension from the next card. Confirm the
  marker disappears while the card stays in the queue and in the counts.
- Destroy the next card's entity. Confirm the marker disappears and the counts
  are unchanged.

## Expected evidence

Per scenario: the five counts shown in the HUD beside the same counts read from
Anki; the indicator mode; which entity was marked; and the Activation Zone
radius before and after any overlap.

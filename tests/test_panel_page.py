"""The panel page, executed rather than read.

`test_panel_locale_keys.py` parses `app.js` with regexes precisely because
nothing in this suite ran it. That gap is where the deck dropdown went: the Lua
side put `["2", "Default"]` into the state, every Lua test agreed, and the
player still saw one entry -- because whether the page turns that state into
options is a question no test was asking.

This runs the real file in Node against a DOM stub built from the real
`index.html`, and asserts on what the page did with a state. It cannot prove
anything was *drawn* -- that stays a manual item -- but "the option elements
exist" and "the control sends this action" are exactly the claims that were
being made by inspection.

Skipped where Node is absent, so it never turns into a reason not to run the
suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
PANEL = REPO / "mta" / "ankigta" / "client" / "panel"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node is not installed; the panel page cannot be executed here",
)


#: A DOM with exactly the surface `app.js` uses, and every id the page declares.
#:
#: Built from `index.html` rather than listed here: an id the page stops
#: declaring must break this the way it breaks the panel, and an element
#: invented by the stub would hide exactly that.
HARNESS = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[1] + "/index.html", "utf8");

function mk(tag) {
  return {
    tagName: String(tag || "div").toUpperCase(),
    children: [], attrs: {}, _text: "", listeners: {},
    style: {}, value: "", checked: false, hidden: false, className: "", id: "",
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    closest() { return null; },
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
  };
}

const byId = {};
for (const m of html.matchAll(/\sid="([^"]+)"/g)) byId[m[1]] = mk("div");

const sent = [];
const missing = [];
global.document = {
  documentElement: {},
  getElementById(id) {
    if (!byId[id]) { missing.push(id); byId[id] = mk("div"); }
    return byId[id];
  },
  createElement: mk,
  querySelectorAll: () => [],
  querySelector: () => null,
  addEventListener: () => {},
};
global.window = {
  mta: { triggerEvent(_evt, action, payload) { sent.push([action, JSON.parse(payload)]); } },
};

eval(fs.readFileSync(process.argv[1] + "/app.js", "utf8"));

const script = JSON.parse(process.argv[2]);
for (const step of script) {
  if (step.receive) window.ANKIGTA.receive(step.receive);
  if (step.fire) {
    for (const f of byId[step.fire.id].listeners[step.fire.type] || []) {
      f({ preventDefault() {}, button: 0, target: { closest: () => null } });
    }
  }
  if (step.set) byId[step.set.id].value = step.set.value;
}

console.log(JSON.stringify({
  sent,
  missing,
  options: Object.fromEntries(
    ["deck", "scope"].map((id) => [id, byId[id].children.map((o) => o.value)])
  ),
  searchQuery: byId["search-query"].value,
}));
"""


def run_page(script: list[dict[str, object]]) -> dict[str, object]:
    result = subprocess.run(
        ["node", "-e", HARNESS, "--", str(PANEL), json.dumps(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return dict(json.loads(result.stdout))


def state(**picker: object) -> dict[str, object]:
    """A whole panel state, as Lua pushes one."""
    return {
        "section": "entities",
        "language": "en",
        "locale": {},
        "connection": {"state": "connected"},
        "selected": {"mapId": False, "entityId": False, "cardId": False},
        "study": {"active": False, "resumable": False},
        "settings": {"rows": []},
        "entities": [],
        "history": {},
        "cardPicker": {
            "enabled": True,
            "cards": [],
            "decks": [],
            "deckFilter": False,
            "query": "",
            "scope": "cards",
            **picker,
        },
    }


def test_the_page_binds_every_element_it_reaches_for() -> None:
    """A missing id throws mid-IIFE and leaves the rest of the page dead."""
    answer = run_page([{"receive": state()}])

    assert answer["missing"] == []


def test_the_deck_list_becomes_options_once_a_search_has_answered() -> None:
    """The companion sends the deck list with a search page, not before.

    So an empty dropdown is what an un-searched picker looks like -- which is
    why the deck the owner had was missing until the picker began searching for
    itself.
    """
    answer = run_page(
        [
            {"receive": state()},
            {"receive": state(decks=["2", "Default"])},
        ]
    )

    assert answer["options"]["deck"] == ["", "2", "Default"]


def test_a_redraw_does_not_wipe_the_deck_list() -> None:
    """A state push happens whenever anything at all changes, most of it not
    this."""
    answer = run_page(
        [
            {"receive": state(decks=["2", "Default"])},
            {"receive": state(decks=["2", "Default"])},
        ]
    )

    assert answer["options"]["deck"] == ["", "2", "Default"]


def test_choosing_a_deck_or_a_row_kind_searches_without_a_second_press() -> None:
    """Both dropdowns say what the rows below them are.

    A value that changes nothing until a separate button is pressed reads as a
    filter that does not work.
    """
    chosen = run_page(
        [
            {"receive": state(decks=["2", "Default"])},
            {"set": {"id": "deck", "value": "Default"}},
            {"fire": {"id": "deck", "type": "change"}},
            {"set": {"id": "scope", "value": "notes"}},
            {"fire": {"id": "scope", "type": "change"}},
        ]
    )

    searches = [payload for action, payload in chosen["sent"] if action == "searchCards"]
    assert len(searches) == 2
    assert searches[0]["deck"] == "Default"
    assert searches[1]["scope"] == "notes"


def test_the_expression_keeps_its_button() -> None:
    """Typed text is not a dropdown: a search per keystroke would ask Anki a
    question after every letter."""
    typed = run_page(
        [
            {"receive": state()},
            {"set": {"id": "search-query", "value": "tag:verb"}},
            {"fire": {"id": "search", "type": "submit"}},
        ]
    )

    searches = [payload for action, payload in typed["sent"] if action == "searchCards"]
    assert [s["query"] for s in searches] == ["tag:verb"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

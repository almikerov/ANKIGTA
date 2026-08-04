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
  if (step.type) {
    const box = byId["inspector-fields"].children
      .map((w) => w.children[1])
      .find((b) => b.getAttribute("data-field") === step.type.field);
    box.value = step.type.value;
    for (const f of box.listeners["input"] || []) f({});
  }
  if (step.choose) {
    const option = byId["deck-menu"].children.find(
      (o) => o.getAttribute("data-deck") === step.choose.deck
    );
    for (const f of option.listeners["click"] || []) f({ preventDefault() {} });
  }
}

console.log(JSON.stringify({
  sent,
  missing,
  decks: byId["deck-menu"].children.map((o) => o.getAttribute("data-deck")),
  deckMenuHidden: byId["deck-menu"].hidden,
  deckLabel: byId["deck"].textContent,
  scopeLabel: byId["scope"].textContent,
  searchQuery: byId["search-query"].value,
  saveDisabled: byId["save-note"].disabled,
  inspectorHidden: byId["inspector"].hidden,
  workspaceClass: byId["workspace"].className,
  fieldNames: byId["inspector-fields"].children.map(
    (w) => w.children[1].getAttribute("data-field")
  ),
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


def with_note(**over: object) -> dict[str, object]:
    """A state with a card selected and its note read."""
    base = state()
    base["selected"] = {"mapId": False, "entityId": False, "cardId": "7"}
    base["note"] = {
        "noteId": 3,
        "fields": [{"name": "Front", "value": "你好"}],
        "tags": ["hsk1"],
    }
    base.update(over)
    return base


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

    assert answer["decks"] == ["", "2", "Default"]


def test_a_redraw_does_not_wipe_the_deck_list() -> None:
    """A state push happens whenever anything at all changes, most of it not
    this."""
    answer = run_page(
        [
            {"receive": state(decks=["2", "Default"])},
            {"receive": state(decks=["2", "Default"])},
        ]
    )

    assert answer["decks"] == ["", "2", "Default"]


def test_the_deck_list_is_drawn_in_the_page_and_opens_closed() -> None:
    """Not a native `<select>`.

    MTA blits CEF's popup surface only while it fits inside the browser
    rectangle and drops it whole otherwise, so a native dropdown vanishes
    exactly when it grows -- as soon as a collection has enough decks to need
    one.
    """
    answer = run_page(
        [
            {"receive": state(decks=["2", "Default"])},
        ]
    )

    assert answer["deckMenuHidden"] is True
    opened = run_page(
        [
            {"receive": state(decks=["2", "Default"])},
            {"fire": {"id": "deck", "type": "click"}},
        ]
    )
    assert opened["deckMenuHidden"] is False


def test_choosing_a_deck_or_flipping_the_switch_searches_at_once() -> None:
    """Both say what the rows below them are.

    A value that changes nothing until a separate button is pressed reads as a
    filter that does not work.
    """
    chosen = run_page(
        [
            {"receive": state(decks=["2", "Default"])},
            {"fire": {"id": "deck", "type": "click"}},
            {"choose": {"deck": "Default"}},
            {"fire": {"id": "scope", "type": "click"}},
        ]
    )

    searches = [payload for action, payload in chosen["sent"] if action == "searchCards"]
    assert len(searches) == 2
    assert searches[0]["deck"] == "Default"
    assert searches[1]["scope"] == "notes"
    # And picking one closes the list behind it.
    assert chosen["deckMenuHidden"] is True


def test_the_switch_says_which_of_the_two_it_currently_is() -> None:
    """A toggle whose label is the action rather than the state leaves the
    player guessing which way it is set."""
    answer = run_page(
        [
            {"receive": state()},
            {"fire": {"id": "scope", "type": "click"}},
        ]
    )

    assert answer["scopeLabel"] == "cardPicker.scope.notes"


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


def test_saving_is_offered_only_once_something_has_been_changed() -> None:
    """A Save that is always available says nothing about whether there is
    anything to save."""
    untouched = run_page([{"receive": with_note()}])
    assert untouched["saveDisabled"] is True

    edited = run_page(
        [
            {"receive": with_note()},
            {"type": {"field": "Front", "value": "再见"}},
        ]
    )
    assert edited["saveDisabled"] is False

    # And typing the stored value back is not a change either.
    reverted = run_page(
        [
            {"receive": with_note()},
            {"type": {"field": "Front", "value": "再见"}},
            {"type": {"field": "Front", "value": "你好"}},
        ]
    )
    assert reverted["saveDisabled"] is True


def test_saving_lives_with_the_fields_it_saves() -> None:
    """Save card is the editor's action, so it sits inside the editor.

    The list keeps what the list does with a card -- link it, replace a link
    with it, open the editor on it. Read out of the markup because that is
    where the answer is: which column a control is in is a fact about the page
    and about nothing else.
    """
    html = (PANEL / "index.html").read_text(encoding="utf-8")
    editor = html.split('id="inspector"', 1)[1]
    editor = editor.split("</section>", 1)[0]
    before_editor = html.split('id="inspector"', 1)[0]

    assert 'id="save-note"' in editor
    assert 'id="save-note"' not in before_editor
    # And the list's own row keeps the three that act on the list's selection.
    for control in ('id="link"', 'id="replace"', 'id="toggle-inspector"'):
        assert control in before_editor


def test_opening_the_editor_asks_lua_for_the_room() -> None:
    """The page cannot resize its own window.

    Fitting a third column inside a window sized for two left every column
    cramped; the lists did not ask to be narrower because somebody opened an
    editor. So the page says which shape it is in and Lua widens the panel.
    """
    answer = run_page(
        [
            {"receive": with_note()},
            {"fire": {"id": "toggle-inspector", "type": "click"}},
            {"fire": {"id": "toggle-inspector", "type": "click"}},
        ]
    )

    asked = [payload for action, payload in answer["sent"] if action == "editorVisible"]
    assert [step["open"] for step in asked] == [True, False]


def test_the_editor_stays_shut_until_it_is_asked_for() -> None:
    """Selecting a card is not by itself a request to edit it."""
    selected = run_page([{"receive": with_note()}])

    assert selected["inspectorHidden"] is True
    assert selected["workspaceClass"] == "workspace"

    opened = run_page(
        [
            {"receive": with_note()},
            {"fire": {"id": "toggle-inspector", "type": "click"}},
        ]
    )
    assert opened["inspectorHidden"] is False
    # A third column, beside the card list rather than inside it.
    assert opened["workspaceClass"] == "workspace editing"
    assert opened["fieldNames"] == ["Front"]

    shut = run_page(
        [
            {"receive": with_note()},
            {"fire": {"id": "toggle-inspector", "type": "click"}},
            {"fire": {"id": "toggle-inspector", "type": "click"}},
        ]
    )
    assert shut["inspectorHidden"] is True


def test_an_edit_survives_the_editor_being_shut_and_reopened() -> None:
    """Hiding a form is not discarding what was typed into it."""
    answer = run_page(
        [
            {"receive": with_note()},
            {"fire": {"id": "toggle-inspector", "type": "click"}},
            {"type": {"field": "Front", "value": "再见"}},
            {"fire": {"id": "toggle-inspector", "type": "click"}},
            {"fire": {"id": "toggle-inspector", "type": "click"}},
        ]
    )

    assert answer["saveDisabled"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

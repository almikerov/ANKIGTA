"""The panel page, executed rather than read.

`test_panel_locale_keys.py` parses `app.js` with regexes precisely because
nothing in this suite ran it. That gap is where the deck dropdown went: the Lua
side put `["2", "Default"]` into the state, every Lua test agreed, and the
player still saw one entry -- because whether the page turns that state into
options is a question no test was asking.

This runs the real file in Node against the real `index.html`, parsed into a
tree, and asserts on what the page did with a state. It cannot prove anything
was *drawn* -- that stays a manual item -- but "this control exists, in this
part of the page, and sends this action" are exactly the claims that were being
made by inspection.

Nothing here reads a source file as text. The previous version of this module
split `index.html` on `'id="inspector"'`, which `docs/agents/lua-testing.md`
forbids by name; what it was really asking -- whether Save belongs to the
editor -- is asked below by opening the editor and looking at where the control
is in the tree.

Skipped where Node is absent, so it never turns into a reason not to run the
suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterator

import pytest


REPO = Path(__file__).resolve().parent.parent
PANEL = REPO / "mta" / "ankigta" / "client" / "panel"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node is not installed; the panel page cannot be executed here",
)


#: The real page, in a DOM with exactly the surface `app.js` uses.
#:
#: `index.html` is parsed into a tree rather than mined for ids, so a control
#: sits where the markup puts it and containment is a thing a test can ask
#: about. An element the page stops declaring breaks this the way it breaks the
#: panel; one invented by the stub would hide exactly that.
HARNESS = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[1] + "/index.html", "utf8");

const created = [];
const scrolled = [];

function mk(tag) {
  created.push(String(tag || "div").toUpperCase());
  return {
    tagName: String(tag || "div").toUpperCase(),
    children: [], attrs: {}, _text: "", listeners: {}, parent: null,
    style: {}, _value: "", checked: false, hidden: false, disabled: false,
    className: "", id: "", title: "",
    get value() { return this._value; },
    set value(v) { this._value = String(v); },
    appendChild(c) { c.parent = this; this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    scrollIntoView() { scrolled.push(this.id || this.attrs["data-row"] || ""); },
    /* One fixed box per node. The page only needs somewhere to open from, and
       a real layout is what the stub cannot have. `bottom` is chosen so a list
       has room below it; the test that wants none moves it. */
    getBoundingClientRect() {
      return this._rect || { left: 40, top: 100, right: 180, bottom: 130, width: 140, height: 30 };
    },
    select() {},
    closest(selector) {
      const wanted = selector.split(",").map((s) => s.trim().toUpperCase());
      let node = this;
      while (node) {
        if (wanted.indexOf(node.tagName) !== -1) return node;
        node = node.parent;
      }
      return null;
    },
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
  };
}

/* A tag-soup parser, which is all this page needs: it is hand-written, closes
   what it opens, and quotes every attribute. */
const VOID = ["meta", "link", "input", "br", "hr", "img"];
function parse(source) {
  const text = source
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<![^>]*>/g, "")
    .replace(/<\/?(html|head|title|body)[^>]*>/g, "");
  const body = mk("body");
  const stack = [body];
  const tags = /<\/([a-zA-Z0-9]+)\s*>|<([a-zA-Z0-9]+)((?:"[^"]*"|[^>"])*?)(\/?)>/g;
  let match;
  while ((match = tags.exec(text)) !== null) {
    if (match[1]) {
      if (stack.length > 1) stack.pop();
      continue;
    }
    const node = mk(match[2]);
    const attributes = /([a-zA-Z0-9:_-]+)(?:="([^"]*)")?/g;
    let attribute;
    while ((attribute = attributes.exec(match[3] || "")) !== null) {
      const name = attribute[1];
      const value = attribute[2] === undefined ? "" : attribute[2];
      node.attrs[name] = value;
      if (name === "class") node.className = value;
      if (name === "id") node.id = value;
      if (name === "hidden") node.hidden = true;
      if (name === "value") node.value = value;
      if (name === "type") node.type = value;
      if (name === "placeholder") node.placeholder = value;
      if (name === "title") node.title = value;
    }
    stack[stack.length - 1].appendChild(node);
    if (VOID.indexOf(match[2].toLowerCase()) === -1 && !match[4]) {
      stack.push(node);
    }
  }
  return body;
}

const body = parse(html);
created.length = 0;

function every(node, out) {
  out.push(node);
  for (const child of node.children) every(child, out);
  return out;
}

function matchesSelector(node, selector) {
  const attribute = selector.match(/^\[([a-zA-Z0-9-]+)\]$/);
  if (attribute) return attribute[1] in node.attrs;
  return false;
}

const sent = [];
const missing = [];
const documentListeners = {};
global.document = {
  documentElement: {},
  body: body,
  getElementById(id) {
    for (const node of every(body, [])) if (node.id === id) return node;
    missing.push(id);
    return mk("div");
  },
  createElement: mk,
  querySelectorAll(selector) {
    return every(body, []).filter((n) => matchesSelector(n, selector));
  },
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  },
  addEventListener(type, handler) {
    (documentListeners[type] = documentListeners[type] || []).push(handler);
  },
};
global.window = {
  innerWidth: 1180,
  innerHeight: 700,
  mta: { triggerEvent(_evt, action, payload) { sent.push([action, JSON.parse(payload)]); } },
};

eval(fs.readFileSync(process.argv[1] + "/app.js", "utf8"));

function root(step) {
  return step.under ? document.getElementById(step.under) : body;
}

function locate(step) {
  if (step.id) return document.getElementById(step.id);
  const found = every(root(step), []).find((node) =>
    step.attr ? node.attrs[step.attr] === step.is
      : (" " + node.className + " ").indexOf(" " + step.cls + " ") !== -1
  );
  if (!found) {
    throw new Error("no node for " + JSON.stringify(step));
  }
  return found;
}

function fire(node, type, event) {
  for (const handler of node.listeners[type] || []) handler(event || {
    preventDefault() {}, stopPropagation() {}, button: 0,
    target: { closest: () => null },
  });
}

const script = JSON.parse(process.argv[2]);
for (const step of script) {
  if (step.receive) window.ANKIGTA.receive(step.receive);
  if (step.click) fire(locate(step.click), "click");
  if (step.submit) fire(locate(step.submit), "submit");
  if (step.change) fire(locate(step.change), "change");
  if (step.input) fire(locate(step.input), "input");
  if (step.set) locate(step.set).value = String(step.set.value);
  if (step.check) locate(step.check).checked = step.check.value;
  if (step.rect) locate(step.rect)._rect = step.rect.box;
  if (step.docclick) {
    for (const handler of documentListeners["click"] || []) handler({});
  }
  if (step.key) {
    for (const handler of documentListeners["keydown"] || []) {
      handler({
        key: step.key.key,
        preventDefault() {},
        target: { tagName: step.key.tag || "BODY" },
      });
    }
  }
}

function dump(node) {
  return {
    tag: node.tagName,
    id: node.id,
    cls: node.className,
    text: node._text,
    value: node._value,
    hidden: node.hidden === true,
    disabled: node.disabled === true,
    checked: node.checked === true,
    title: node.title,
    attrs: node.attrs,
    style: node.style,
    children: node.children.map(dump),
  };
}

console.log(JSON.stringify({
  sent, missing, scrolled, created, tree: dump(body),
}));
"""


def run_page(script: list[dict[str, object]]) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "-e", HARNESS, "--", str(PANEL), json.dumps(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return dict(json.loads(result.stdout))


# --- reading the page back ---------------------------------------------------


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node["children"]:
        yield from walk(child)


def node(answer: dict[str, Any], ident: str) -> dict[str, Any]:
    for candidate in walk(answer["tree"]):
        if candidate["id"] == ident:
            return candidate
    raise AssertionError(f"the page has no #{ident}")


def has_class(candidate: dict[str, Any], name: str) -> bool:
    return name in str(candidate["cls"]).split()


def descendants(
    scope: dict[str, Any], *, cls: str | None = None, tag: str | None = None
) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in walk(scope)
        if (cls is None or has_class(candidate, cls))
        and (tag is None or candidate["tag"] == tag)
    ]


def one(scope: dict[str, Any], *, cls: str) -> dict[str, Any]:
    found = descendants(scope, cls=cls)
    assert len(found) == 1, f"{len(found)} nodes with class {cls}"
    return found[0]


def labels(scope: dict[str, Any], *, cls: str) -> list[str]:
    return [candidate["text"] for candidate in descendants(scope, cls=cls)]


def actions(answer: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [payload for action, payload in answer["sent"] if action == name]


# --- the states Lua pushes ---------------------------------------------------


def state(**over: Any) -> dict[str, Any]:
    """A whole panel state, as Lua pushes one."""
    picker = dict(over.pop("picker", {}))
    base: dict[str, Any] = {
        "section": "entities",
        "locale": {},
        "connection": {"state": "connected"},
        "selected": {"mapId": False, "entityId": False, "cardId": False},
        "study": {"active": False, "resumable": False},
        "settings": {"rows": []},
        "entities": [],
        "focusOnSelect": True,
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
    base.update(over)
    return base


def entity(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "mapId": "map-1",
        "entityId": "gate-17",
        "type": "object",
        "name": "Infernus",
        "givenName": "",
        "originalName": False,
        "description": "10.25, -20.50, 3.00 · Ganton",
        "linkState": "Unlinked",
        "radius": 3,
        "radiusInherited": True,
        "showCorona": False,
        "coronaColor": "#3cc8ff",
        "coronaColorInherited": True,
        "coronaOpacity": 0.6,
        "coronaOpacityInherited": True,
        "linkedCard": False,
        "recheckAvailable": False,
        "copyCollision": False,
    }
    row.update(over)
    return row


def selecting(row: dict[str, Any], **over: Any) -> dict[str, Any]:
    """A state with `row` in the list and selected."""
    return state(
        entities=[row],
        selected={
            "mapId": row["mapId"],
            "entityId": row["entityId"],
            "cardId": False,
        },
        **over,
    )


def with_note(**over: Any) -> dict[str, Any]:
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


#: Rows covering every kind the settings list can be handed.
CHOICE_ROW = {
    "kind": "choice",
    "key": "reviewMode",
    "value": "allow_due",
    "options": ["allow_due", "allow_all"],
}
COLOR_ROW = {"kind": "color", "key": "coronaColor", "value": "#38bdf8"}
NUMBER_ROW = {
    "kind": "number",
    "key": "activationRadius",
    "value": 3,
    "min": 0.5,
    "max": 50,
    "step": 0.5,
}
BOOLEAN_ROW = {"kind": "boolean", "key": "muteGameWorld", "value": False}


def settings(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"rows": [dict(row) for row in rows]}


# --- every control is drawn in the page --------------------------------------


def test_the_page_binds_every_element_it_reaches_for() -> None:
    """A missing id throws mid-IIFE and leaves the rest of the page dead."""
    answer = run_page([{"receive": state()}])

    assert answer["missing"] == []


def test_no_control_on_the_page_is_a_native_dropdown() -> None:
    """A `<select>` opens a *native* popup, and this page has nowhere to put one.

    MTA blits CEF's popup surface only while it fits inside the browser
    rectangle and drops it whole otherwise, so the list vanishes exactly when it
    grows -- which is what "clicking a dropdown shows nothing" was.
    """
    answer = run_page(
        [
            {
                "receive": state(
                    picker={"decks": ["Default"]},
                    settings=settings(CHOICE_ROW, COLOR_ROW),
                )
            }
        ]
    )

    assert [n["tag"] for n in walk(answer["tree"]) if n["tag"] == "SELECT"] == []
    # Nor built at runtime, which is where the last one was.
    assert "SELECT" not in answer["created"]


def test_a_dropdown_opens_from_anywhere_on_it_rather_than_from_an_arrow() -> None:
    """The whole control is the button, so there is no part of it that is not.

    What the owner reported is a control that answered only where its arrow
    happened to be drawn.
    """
    shut = run_page([{"receive": state(picker={"decks": ["Default"]})}])
    assert one(node(shut, "deck-picker"), cls="picker-panel")["hidden"] is True

    opened = run_page(
        [
            {"receive": state(picker={"decks": ["Default"]})},
            {"click": {"under": "deck-picker", "attr": "data-picker", "is": "deck"}},
        ]
    )
    picker = node(opened, "deck-picker")
    assert one(picker, cls="picker-panel")["hidden"] is False
    assert one(picker, cls="picker-button")["attrs"]["aria-expanded"] == "true"


def test_the_deck_the_switch_and_a_settings_choice_are_one_control() -> None:
    """Two dropdowns where one is native and one is drawn would look and behave
    differently for no reason a player could name."""
    answer = run_page(
        [
            {
                "receive": state(
                    picker={"decks": ["Default"]}, settings=settings(CHOICE_ROW)
                )
            }
        ]
    )

    for host in ("deck-picker", "scope-picker", "settings-rows"):
        scope = node(answer, host)
        assert descendants(scope, cls="picker-button"), host
        assert descendants(scope, cls="picker-panel"), host
        assert one(scope, cls="picker-panel")["hidden"] is True


def test_the_deck_list_becomes_options_once_a_search_has_answered() -> None:
    """The companion sends the deck list with a search page, not before.

    So an empty dropdown is what an un-searched picker looks like -- which is
    why the deck the owner had was missing until the picker began searching for
    itself.
    """
    answer = run_page(
        [
            {"receive": state()},
            {"receive": state(picker={"decks": ["2", "Default"]})},
        ]
    )

    options = descendants(node(answer, "deck-picker"), cls="picker-option")
    assert [option["attrs"]["data-value"] for option in options] == [
        "",
        "2",
        "Default",
    ]


def test_a_redraw_does_not_wipe_the_deck_list() -> None:
    """A state push happens whenever anything at all changes, most of it not
    this."""
    answer = run_page(
        [
            {"receive": state(picker={"decks": ["2", "Default"]})},
            {"receive": state(picker={"decks": ["2", "Default"]})},
        ]
    )

    options = descendants(node(answer, "deck-picker"), cls="picker-option")
    assert len(options) == 3


def test_a_choice_made_in_the_list_reaches_the_server() -> None:
    """A deck and a row-kind each say what the rows below them are.

    A value that changes nothing until a separate button is pressed reads as a
    filter that does not work.
    """
    answer = run_page(
        [
            {"receive": state(picker={"decks": ["2", "Default"]})},
            {"click": {"under": "deck-picker", "attr": "data-picker", "is": "deck"}},
            {"click": {"under": "deck-picker", "attr": "data-value", "is": "Default"}},
            {"click": {"under": "scope-picker", "attr": "data-value", "is": "notes"}},
        ]
    )

    searches = actions(answer, "searchCards")
    assert len(searches) == 2
    assert searches[0]["deck"] == "Default"
    assert searches[1]["scope"] == "notes"
    # And choosing closes the list behind it.
    assert one(node(answer, "deck-picker"), cls="picker-panel")["hidden"] is True
    assert one(node(answer, "deck-picker"), cls="picker-button")["text"] == "Default"


def test_the_switch_says_which_of_the_two_it_currently_is() -> None:
    """A control whose label is the action rather than the state leaves the
    player guessing which way it is set."""
    answer = run_page(
        [
            {"receive": state(locale={"cardPicker.scope.notes": "Notes"})},
            {"click": {"under": "scope-picker", "attr": "data-value", "is": "notes"}},
        ]
    )

    assert one(node(answer, "scope-picker"), cls="picker-button")["text"] == "Notes"


def test_a_settings_choice_sends_the_value_that_was_chosen() -> None:
    answer = run_page(
        [
            {"receive": state(settings=settings(CHOICE_ROW))},
            {"click": {"under": "settings-rows", "attr": "data-picker", "is": "reviewMode"}},
            {"click": {"under": "settings-rows", "attr": "data-value", "is": "allow_all"}},
        ]
    )

    assert actions(answer, "setSetting") == [
        {"key": "reviewMode", "value": "allow_all"}
    ]


def test_the_expression_keeps_its_button() -> None:
    """Typed text is not a dropdown: a search per keystroke would ask Anki a
    question after every letter."""
    typed = run_page(
        [
            {"receive": state()},
            {"set": {"id": "search-query", "value": "tag:verb"}},
            {"submit": {"id": "search"}},
        ]
    )

    assert [s["query"] for s in actions(typed, "searchCards")] == ["tag:verb"]


# --- a colour is chosen the same way -----------------------------------------


def test_a_colour_is_chosen_from_swatches_drawn_in_the_page() -> None:
    """`<input type="color">` hit the same wall the dropdowns did: a native
    dialog has nowhere to appear over a page rendered offscreen."""
    answer = run_page(
        [
            {"receive": state(settings=settings(COLOR_ROW))},
            {"click": {"under": "settings-rows", "attr": "data-picker", "is": "coronaColor"}},
            {"click": {"under": "settings-rows", "attr": "data-value", "is": "#ef4444"}},
        ]
    )

    assert actions(answer, "setSetting") == [
        {"key": "coronaColor", "value": "#ef4444"}
    ]
    swatches = descendants(node(answer, "settings-rows"), cls="swatch-option")
    assert len(swatches) >= 8
    # Each swatch is the colour it stands for; a hex code is not a colour
    # anybody can see.
    assert swatches[0]["style"]["background"] == swatches[0]["attrs"]["data-value"]


def test_a_colour_can_also_be_typed_and_a_wrong_one_is_refused() -> None:
    """Twelve swatches are not every colour, and half a hex code is not one."""
    typed = run_page(
        [
            {"receive": state(settings=settings(COLOR_ROW))},
            {"set": {"attr": "data-color-hex", "is": "coronaColor", "value": "#0A0B0C"}},
            {"change": {"attr": "data-color-hex", "is": "coronaColor"}},
        ]
    )
    assert actions(typed, "setSetting") == [
        {"key": "coronaColor", "value": "#0a0b0c"}
    ]

    refused = run_page(
        [
            {"receive": state(settings=settings(COLOR_ROW))},
            {"set": {"attr": "data-color-hex", "is": "coronaColor", "value": "#0A0B"}},
            {"change": {"attr": "data-color-hex", "is": "coronaColor"}},
        ]
    )
    assert actions(refused, "setSetting") == []
    box = [
        n
        for n in walk(refused["tree"])
        if n["attrs"].get("data-color-hex") == "coronaColor"
    ][0]
    assert box["attrs"]["aria-invalid"] == "true"


# --- a push does not destroy what the player is doing ------------------------


def test_an_unrelated_push_leaves_an_open_list_open() -> None:
    """Settings rebuilt every row on every push, and a push happens whenever
    anything at all changes -- so an open list was taken down by a redraw about
    something else entirely."""
    answer = run_page(
        [
            {"receive": state(settings=settings(CHOICE_ROW))},
            {"click": {"under": "settings-rows", "attr": "data-picker", "is": "reviewMode"}},
            {"receive": state(settings=settings(CHOICE_ROW), entities=[entity()])},
        ]
    )

    assert one(node(answer, "settings-rows"), cls="picker-panel")["hidden"] is False


def test_an_unrelated_push_does_not_throw_away_what_is_being_typed() -> None:
    """The field is written only when the value Lua reports actually changes."""
    kept = run_page(
        [
            {"receive": state(settings=settings(NUMBER_ROW))},
            {"set": {"id": "set-activationRadius", "value": "12.5"}},
            {"receive": state(settings=settings(NUMBER_ROW), entities=[entity()])},
        ]
    )
    assert node(kept, "set-activationRadius")["value"] == "12.5"

    # And a value that really did change still lands: the guard is about
    # redraws, not about refusing what the server says.
    changed = dict(NUMBER_ROW, value=7)
    moved = run_page(
        [
            {"receive": state(settings=settings(NUMBER_ROW))},
            {"set": {"id": "set-activationRadius", "value": "12.5"}},
            {"receive": state(settings=settings(changed))},
        ]
    )
    assert node(moved, "set-activationRadius")["value"] == "7"


def test_a_settings_row_still_sends_after_a_redraw_that_did_not_rebuild_it() -> None:
    """The control reads the row it was last given rather than the one it was
    built with, or a row kept across a push would send a stale value."""
    flipped = dict(BOOLEAN_ROW, value=True)
    answer = run_page(
        [
            {"receive": state(settings=settings(BOOLEAN_ROW))},
            {"receive": state(settings=settings(flipped))},
            {"click": {"id": "set-muteGameWorld"}},
        ]
    )

    assert actions(answer, "setSetting") == [
        {"key": "muteGameWorld", "value": False}
    ]


# --- the edit pane does not come and go --------------------------------------


def test_the_entity_pane_is_on_screen_with_nothing_selected() -> None:
    """It used to appear with the selection and vanish with it, so this corner
    of the panel jumped every time the player moved down the list."""
    answer = run_page([{"receive": state(entities=[entity()])}])

    assert node(answer, "entity-settings")["hidden"] is False
    assert node(answer, "entity-fields")["hidden"] is False


def test_with_nothing_selected_the_pane_says_so_rather_than_being_blank() -> None:
    empty = run_page(
        [
            {
                "receive": state(
                    entities=[entity()],
                    locale={"f7.noSelection": "Select a Map Entity."},
                )
            }
        ]
    )
    assert node(empty, "entity-empty")["hidden"] is False
    assert node(empty, "entity-empty")["text"] == "Select a Map Entity."
    # And the fields keep their place, gone quiet rather than gone.
    assert node(empty, "entity-name")["disabled"] is True
    assert node(empty, "entity-radius")["disabled"] is True

    chosen = run_page([{"receive": selecting(entity())}])
    assert node(chosen, "entity-empty")["hidden"] is True
    assert node(chosen, "entity-name")["disabled"] is False


def test_the_name_box_holds_the_name_somebody_gave_not_the_model_name() -> None:
    """A box pre-filled with "Infernus" is a box that stores "Infernus" the
    first time anybody touches it."""
    unnamed = run_page([{"receive": selecting(entity(name="Infernus"))}])
    assert node(unnamed, "entity-name")["value"] == ""

    named = run_page(
        [{"receive": selecting(entity(name="North gate", givenName="North gate"))}]
    )
    assert node(named, "entity-name")["value"] == "North gate"


# --- a field that inherits a global shows the global --------------------------


def test_a_field_with_no_override_shows_the_global_in_force() -> None:
    """An empty box was meant to read as "whatever Settings says" and reads as
    no value at all."""
    answer = run_page(
        [{"receive": selecting(entity(radius=10, radiusInherited=True))}]
    )

    assert node(answer, "entity-radius")["value"] == "10"


def test_an_inherited_value_is_visibly_inherited_rather_than_chosen() -> None:
    """A number that came from Settings looks exactly like a number somebody
    chose."""
    following = run_page(
        [
            {
                "receive": selecting(
                    entity(radius=10, radiusInherited=True),
                    locale={"f7.radiusInherited": "following Settings"},
                )
            }
        ]
    )
    assert node(following, "entity-radius")["attrs"]["data-inherited"] == "true"
    mark = node(following, "entity-radius-inherited")
    assert mark["hidden"] is False
    assert mark["text"] == "following Settings"

    chosen = run_page(
        [{"receive": selecting(entity(radius=7.5, radiusInherited=False))}]
    )
    assert node(chosen, "entity-radius")["attrs"]["data-inherited"] == "false"
    assert node(chosen, "entity-radius-inherited")["hidden"] is True


def test_clearing_the_field_asks_to_follow_the_global_again() -> None:
    """Not "no radius", and not a copy of today's global either: following is
    what makes a later change to the global move this entity with it."""
    answer = run_page(
        [
            {"receive": selecting(entity(radius=7.5, radiusInherited=False))},
            {"set": {"id": "entity-radius", "value": ""}},
            {"change": {"id": "entity-radius"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"radius": False}]


# --- how the entity says it is marked ----------------------------------------


def test_the_pane_offers_show_corona_and_no_draw_always() -> None:
    """`Draw always` made a drawn radius permanent, which confused a way of
    looking with a property of the thing. What is on the pane is the second;
    the first is a client setting now."""
    answer = run_page([{"receive": selecting(entity(showCorona=True))}])

    assert node(answer, "entity-show-corona")["checked"] is True
    for gone in ("entity-draw-always", "entity-draw-now"):
        with pytest.raises(AssertionError):
            node(answer, gone)


def test_showing_a_corona_is_sent_to_the_entity() -> None:
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {"check": {"id": "entity-show-corona", "value": True}},
            {"change": {"id": "entity-show-corona"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"showCorona": True}]


def test_a_corona_colour_is_chosen_with_the_picker_the_page_draws() -> None:
    """The same component the Settings rows use: a native colour dialog has
    nowhere to open over a page rendered offscreen into a game window."""
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {
                "click": {
                    "under": "entity-corona-color",
                    "attr": "data-picker",
                    "is": "entityCoronaColor",
                }
            },
            {
                "click": {
                    "under": "entity-corona-color",
                    "attr": "data-value",
                    "is": "#ef4444",
                }
            },
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"coronaColor": "#ef4444"}]


def test_an_inherited_colour_shows_the_one_settings_holds() -> None:
    """A swatch showing nothing would say the corona has no colour, and it has
    one -- the same rule the radius box follows."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(coronaColor="#38bdf8", coronaColorInherited=True),
                    locale={"f7.coronaInherited": "following Settings"},
                )
            }
        ]
    )

    swatch = [
        candidate
        for candidate in walk(node(answer, "entity-corona-color"))
        if candidate["attrs"].get("data-picker") == "entityCoronaColor"
    ][0]
    assert swatch["attrs"]["data-value"] == "#38bdf8"
    mark = node(answer, "entity-corona-color-inherited")
    assert mark["hidden"] is False
    assert mark["text"] == "following Settings"


def test_a_colour_can_be_handed_back_to_settings() -> None:
    """An emptied hex box cannot say it: half a hex code is refused, so `""`
    would be refused too. The picker offers the way back explicitly."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(coronaColor="#ff8000", coronaColorInherited=False)
                )
            },
            {
                "click": {
                    "under": "entity-corona-color",
                    "attr": "data-picker-clear",
                    "is": "entityCoronaColor",
                }
            },
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"coronaColor": False}]


def test_an_emptied_opacity_asks_to_follow_settings_again() -> None:
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(coronaOpacity=0.25, coronaOpacityInherited=False)
                )
            },
            {"set": {"id": "entity-corona-opacity", "value": ""}},
            {"change": {"id": "entity-corona-opacity"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"coronaOpacity": False}]


def test_a_typed_opacity_is_sent_as_the_number_it_is() -> None:
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {"set": {"id": "entity-corona-opacity", "value": "0.25"}},
            {"change": {"id": "entity-corona-opacity"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"coronaOpacity": 0.25}]


def test_with_nothing_selected_the_marks_controls_are_disabled() -> None:
    """The pane keeps its place rather than coming and going, so the fields are
    disabled instead of removed."""
    answer = run_page([{"receive": state()}])

    assert node(answer, "entity-show-corona")["disabled"] is True
    assert node(answer, "entity-corona-opacity")["disabled"] is True
    picker = [
        candidate
        for candidate in walk(node(answer, "entity-corona-color"))
        if candidate["attrs"].get("data-picker") == "entityCoronaColor"
    ][0]
    assert picker["disabled"] is True


def test_a_typed_radius_is_sent_as_the_number_it_is() -> None:
    answer = run_page(
        [
            {"receive": selecting(entity(radius=3, radiusInherited=True))},
            {"set": {"id": "entity-radius", "value": "7.5"}},
            {"change": {"id": "entity-radius"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"radius": 7.5}]


# --- the list stops fighting the player --------------------------------------


def test_a_single_click_on_a_row_selects_it_and_points_the_camera() -> None:
    """Selecting a row and looking at it are the same intention almost every
    time: the reason to select a row is to decide something about the thing it
    names, and that decision needs the thing on screen."""
    answer = run_page(
        [
            {"receive": state(entities=[entity()])},
            {"click": {"under": "rows", "cls": "row"}},
        ]
    )

    assert [action for action, _ in answer["sent"] if action in
            ("select", "focusEntity")] == ["select", "focusEntity"]
    assert actions(answer, "focusEntity") == [
        {"mapId": "map-1", "entityId": "gate-17"}
    ]


def test_a_client_setting_leaves_the_click_selecting_only() -> None:
    """"Almost every time" is not "every time": arrowing through fifty rows
    with the camera flying to each is not a way to read a list."""
    answer = run_page(
        [
            {"receive": state(entities=[entity()], focusOnSelect=False)},
            {"click": {"under": "rows", "cls": "row"}},
        ]
    )

    assert actions(answer, "select") == [{"mapId": "map-1", "entityId": "gate-17"}]
    assert actions(answer, "focusEntity") == []


def test_up_and_down_move_the_selection() -> None:
    """A list reachable only by pointing gets slower the longer it is, and this
    one is meant to grow."""
    rows = [
        entity(entityId="a"),
        entity(entityId="b"),
        entity(entityId="c"),
    ]
    down = run_page(
        [
            {"receive": state(entities=rows)},
            {"key": {"key": "ArrowDown"}},
        ]
    )
    assert actions(down, "select") == [{"mapId": "map-1", "entityId": "a"}]

    onwards = run_page(
        [
            {
                "receive": state(
                    entities=rows,
                    selected={"mapId": "map-1", "entityId": "b", "cardId": False},
                )
            },
            {"key": {"key": "ArrowDown"}},
            {"key": {"key": "ArrowUp"}},
        ]
    )
    assert actions(onwards, "select") == [
        {"mapId": "map-1", "entityId": "c"},
        # The state has not come back yet, so `b` is still the selected row and
        # up from it is `a`. What matters is that each press moves from what the
        # page currently believes is selected.
        {"mapId": "map-1", "entityId": "a"},
    ]


def test_the_selection_stays_on_screen_as_it_moves() -> None:
    """A selection that moves out of view is a selection the player has lost."""
    answer = run_page(
        [
            {"receive": state(entities=[entity(entityId="a"), entity(entityId="b")])},
            {"key": {"key": "ArrowDown"}},
        ]
    )

    assert len(answer["scrolled"]) == 1


def test_the_arrow_keys_leave_a_field_being_typed_in_alone() -> None:
    """Down inside a number box is the box's own, and inside a note field it is
    the next line."""
    answer = run_page(
        [
            {"receive": state(entities=[entity()])},
            {"key": {"key": "ArrowDown", "tag": "INPUT"}},
        ]
    )

    assert actions(answer, "select") == []


def test_a_renamed_row_still_shows_the_name_it_had_before() -> None:
    """The cosmetic name replaces the model name, which is the point -- but it
    also hides the only thing tying the row to what the Map Editor shows."""
    answer = run_page(
        [
            {
                "receive": state(
                    entities=[
                        entity(
                            name="North gate",
                            givenName="North gate",
                            originalName="Infernus",
                        )
                    ],
                    locale={"f7.entity.originalName": "originally %s"},
                )
            }
        ]
    )

    row = one(node(answer, "rows"), cls="row")
    assert [n["text"] for n in descendants(row, tag="STRONG")] == ["North gate"]
    assert [
        candidate["text"] for candidate in descendants(row, cls="original-name")
    ] == ["originally Infernus"]


def test_a_row_nobody_renamed_says_its_name_once() -> None:
    answer = run_page([{"receive": state(entities=[entity(name="Infernus")])}])

    row = one(node(answer, "rows"), cls="row")
    assert descendants(row, cls="original-name") == []


# --- Escape, and the list in front of the panel ------------------------------


def test_escape_closes_an_open_list_before_it_closes_the_panel() -> None:
    """Closing the whole panel out from under someone who only wanted to back
    out of a list is not what they pressed it for."""
    answer = run_page(
        [
            {"receive": state(picker={"decks": ["Default"]})},
            {"click": {"under": "deck-picker", "attr": "data-picker", "is": "deck"}},
            {"key": {"key": "Escape"}},
        ]
    )

    assert actions(answer, "close") == []
    assert one(node(answer, "deck-picker"), cls="picker-panel")["hidden"] is True

    again = run_page(
        [
            {"receive": state(picker={"decks": ["Default"]})},
            {"click": {"under": "deck-picker", "attr": "data-picker", "is": "deck"}},
            {"key": {"key": "Escape"}},
            {"key": {"key": "Escape"}},
        ]
    )
    assert len(actions(again, "close")) == 1


def test_opening_one_list_closes_the_one_already_open() -> None:
    answer = run_page(
        [
            {"receive": state(picker={"decks": ["Default"]})},
            {"click": {"under": "deck-picker", "attr": "data-picker", "is": "deck"}},
            {"click": {"under": "scope-picker", "attr": "data-picker", "is": "scope"}},
        ]
    )

    assert one(node(answer, "deck-picker"), cls="picker-panel")["hidden"] is True
    assert one(node(answer, "scope-picker"), cls="picker-panel")["hidden"] is False


def test_clicking_away_closes_an_open_list() -> None:
    answer = run_page(
        [
            {"receive": state(picker={"decks": ["Default"]})},
            {"click": {"under": "deck-picker", "attr": "data-picker", "is": "deck"}},
            {"docclick": True},
        ]
    )

    assert one(node(answer, "deck-picker"), cls="picker-panel")["hidden"] is True


# --- the card editor ---------------------------------------------------------


def test_saving_is_offered_only_once_something_has_been_changed() -> None:
    """A Save that is always available says nothing about whether there is
    anything to save."""
    untouched = run_page([{"receive": with_note()}])
    assert node(untouched, "save-note")["disabled"] is True

    edited = run_page(
        [
            {"receive": with_note()},
            {"set": {"attr": "data-field", "is": "Front", "value": "再见"}},
            {"input": {"attr": "data-field", "is": "Front"}},
        ]
    )
    assert node(edited, "save-note")["disabled"] is False

    # And typing the stored value back is not a change either.
    reverted = run_page(
        [
            {"receive": with_note()},
            {"set": {"attr": "data-field", "is": "Front", "value": "再见"}},
            {"input": {"attr": "data-field", "is": "Front"}},
            {"set": {"attr": "data-field", "is": "Front", "value": "你好"}},
            {"input": {"attr": "data-field", "is": "Front"}},
        ]
    )
    assert node(reverted, "save-note")["disabled"] is True


def test_saving_lives_with_the_fields_it_saves() -> None:
    """Save card is the editor's action, so it sits inside the editor.

    Read out of the page as it stands rather than out of the file as text:
    which column a control is in is a fact about the rendered page, and asking
    the source is how this test used to break whenever the markup was
    reformatted.
    """
    answer = run_page(
        [
            {"receive": with_note()},
            {"click": {"id": "toggle-inspector"}},
        ]
    )

    editor = node(answer, "inspector")
    assert [n["id"] for n in walk(editor) if n["id"] == "save-note"] == ["save-note"]
    # And the list's own row keeps the three that act on the list's selection.
    inside = {n["id"] for n in walk(editor)}
    assert {"link", "replace", "toggle-inspector"}.isdisjoint(inside)


def test_opening_the_editor_asks_lua_for_the_room() -> None:
    """The page cannot resize its own window.

    Fitting a third column inside a window sized for two left every column
    cramped; the lists did not ask to be narrower because somebody opened an
    editor. So the page says which shape it is in and Lua widens the panel.
    """
    answer = run_page(
        [
            {"receive": with_note()},
            {"click": {"id": "toggle-inspector"}},
            {"click": {"id": "toggle-inspector"}},
        ]
    )

    assert [step["open"] for step in actions(answer, "editorVisible")] == [
        True,
        False,
    ]


def test_the_editor_stays_shut_until_it_is_asked_for() -> None:
    """Selecting a card is not by itself a request to edit it."""
    selected = run_page([{"receive": with_note()}])

    assert node(selected, "inspector")["hidden"] is True
    assert node(selected, "workspace")["cls"] == "workspace"

    opened = run_page(
        [
            {"receive": with_note()},
            {"click": {"id": "toggle-inspector"}},
        ]
    )
    assert node(opened, "inspector")["hidden"] is False
    # A third column, beside the card list rather than inside it.
    assert node(opened, "workspace")["cls"] == "workspace editing"
    assert [
        box["attrs"]["data-field"]
        for box in walk(node(opened, "inspector-fields"))
        if "data-field" in box["attrs"]
    ] == ["Front"]

    shut = run_page(
        [
            {"receive": with_note()},
            {"click": {"id": "toggle-inspector"}},
            {"click": {"id": "toggle-inspector"}},
        ]
    )
    assert node(shut, "inspector")["hidden"] is True


def test_an_edit_survives_the_editor_being_shut_and_reopened() -> None:
    """Hiding a form is not discarding what was typed into it."""
    answer = run_page(
        [
            {"receive": with_note()},
            {"click": {"id": "toggle-inspector"}},
            {"set": {"attr": "data-field", "is": "Front", "value": "再见"}},
            {"input": {"attr": "data-field", "is": "Front"}},
            {"click": {"id": "toggle-inspector"}},
            {"click": {"id": "toggle-inspector"}},
        ]
    )

    assert node(answer, "save-note")["disabled"] is False


# --- an open list is not clipped by whatever it opened inside ----------------


def test_a_list_opens_against_the_window_not_inside_the_scroller() -> None:
    """`.settings-rows` scrolls, and an absolutely positioned list is clipped by
    any scroller between it and its containing block.

    So a choice near the bottom of Settings would have opened a list that was
    cut off -- which is the defect this whole component exists to remove,
    rebuilt in CSS. The list is placed against the window instead.
    """
    answer = run_page(
        [
            {"receive": state(settings=settings(CHOICE_ROW))},
            {"click": {"under": "settings-rows", "attr": "data-picker", "is": "reviewMode"}},
        ]
    )

    panel = one(node(answer, "settings-rows"), cls="picker-panel")
    assert panel["hidden"] is False
    assert panel["style"]["left"] == "40px"
    # Below the control it belongs to, and no taller than the room left there.
    assert panel["style"]["top"] == "132px"
    assert panel["style"]["maxHeight"] == "562px"


def test_a_list_with_no_room_below_it_opens_upwards() -> None:
    """The panel is a window inside a game, so a control near its foot is the
    ordinary case rather than the awkward one."""
    answer = run_page(
        [
            {"receive": state(settings=settings(CHOICE_ROW))},
            {
                "rect": {
                    "under": "settings-rows",
                    "attr": "data-picker",
                    "is": "reviewMode",
                    "box": {
                        "left": 40, "top": 640, "right": 180, "bottom": 670,
                        "width": 140, "height": 30,
                    },
                }
            },
            {"click": {"under": "settings-rows", "attr": "data-picker", "is": "reviewMode"}},
        ]
    )

    panel = one(node(answer, "settings-rows"), cls="picker-panel")
    assert panel["style"]["top"] == ""
    assert panel["style"]["bottom"] == "62px"
    assert panel["style"]["maxHeight"] == "632px"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

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
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


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
  /* Focus travelling into and out of fields, as the document sees it:
     `relatedTarget` on focusout is where the focus went, or null when it left
     for something that takes no keys. */
  if (step.focusin) {
    for (const handler of documentListeners["focusin"] || []) {
      handler({ target: { tagName: step.focusin.tag } });
    }
  }
  if (step.focusout) {
    for (const handler of documentListeners["focusout"] || []) {
      handler({
        target: { tagName: step.focusout.tag },
        relatedTarget: step.focusout.to ? { tagName: step.focusout.to } : null,
      });
    }
  }
  /* `code` as well as `key`: a binding is a physical key, and the page reads
     `event.code` for exactly that reason. A step may send either or both --
     `code` alone is what a captured key really arrives as. */
  if (step.key) {
    for (const handler of documentListeners["keydown"] || []) {
      handler({
        key: step.key.key,
        code: step.key.code,
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


def by_attribute(answer: dict[str, Any], name: str, value: str) -> dict[str, Any]:
    found = [
        candidate
        for candidate in walk(answer["tree"])
        if candidate["attrs"].get(name) == value
    ]
    assert len(found) == 1, f"{name}={value}: {len(found)} nodes"
    return found[0]


def picker_button(answer: dict[str, Any], name: str) -> dict[str, Any]:
    """The button of one drawn list, wherever on the page it was mounted."""
    return by_attribute(answer, "data-picker", name)


def key_button(answer: dict[str, Any], name: str) -> dict[str, Any]:
    """The button of one key control -- the thing that listens for a press."""
    return by_attribute(answer, "data-key-capture", name)


def key_refusal(answer: dict[str, Any], name: str) -> dict[str, Any]:
    """What that control says about the last press it would not take."""
    return by_attribute(answer, "data-key-refused", name)


def restore_button(answer: dict[str, Any], field: str) -> dict[str, Any]:
    """The one control that puts a field back on the global it follows."""
    return by_attribute(answer, "data-restore-global", field)


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
        "showCoronaInherited": True,
        "activationType": "automatic",
        "activationTypeInherited": True,
        "activationKey": "e",
        "activationKeyInherited": True,
        "coronaColor": "#3cc8ff",
        "coronaColorInherited": True,
        "coronaOpacity": 0.6,
        "coronaOpacityInherited": True,
        "textLabelField": "",
        "textLabelFieldInherited": True,
        "textLabelColor": "#ffffff",
        "textLabelColorInherited": True,
        "textLabelSize": 1,
        "textLabelSizeInherited": True,
        "textLabel": False,
        "linkedCard": False,
        "recheckAvailable": False,
        "copyCollision": False,
    }
    row.update(over)
    return row


def text_label(**over: Any) -> dict[str, Any]:
    """What one row's Text Label really shows, as `server/main.lua` reports it."""
    label: dict[str, Any] = {
        "requestedField": "",
        "fieldName": "Front",
        "fallback": False,
        "reason": False,
        "truncated": False,
        "lines": ["hola"],
    }
    label.update(over)
    return label


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
#: The `Activation key` row. It carries no list to choose from -- the key is
#: pressed -- but the two lists a press is judged against: every key MTA can
#: name, and the part of that ANKIGTA is not already answering to. Both are the
#: schema's, and the two tests that read them out of the loaded schema --
#: `test_every_key_the_schema_offers_can_actually_be_pressed` and
#: `test_the_keys_ankigta_reserves_are_refused_by_the_same_press` -- are what
#: holds these short stand-ins honest.
KEY_ROW = {
    "kind": "key",
    "key": "activationKey",
    "value": "e",
    "options": ["e", "q", "F9"],
    "bindableKeys": ["e", "q", "F7", "F9", "escape"],
}


#: A setting a link can override, so the sweep's control is offered beside it.
#: Lua says which those are; the page keeps no list of its own.
SWEEPABLE_ROW = dict(NUMBER_ROW, clearOverrides=True)


def settings(*rows: dict[str, Any], **over: Any) -> dict[str, Any]:
    return {"rows": [dict(row) for row in rows], **over}


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


# --- applying a global to everything -----------------------------------------


def sweep_button(answer: dict[str, Any], key: str) -> dict[str, Any] | None:
    found = [
        candidate
        for candidate in walk(node(answer, "settings-rows"))
        if candidate["attrs"].get("data-apply-all") == key
    ]
    return found[0] if found else None


def test_only_a_setting_a_link_can_override_offers_the_sweep() -> None:
    """Beside the global it is about, and only there. Which globals those are is
    Lua's answer -- the page draws the control for whichever rows say so, so a
    setting that gains an override gains it without this file changing."""
    answer = run_page(
        [{"receive": state(settings=settings(SWEEPABLE_ROW, CHOICE_ROW))}]
    )

    assert sweep_button(answer, "activationRadius") is not None
    assert sweep_button(answer, "reviewMode") is None


def test_pressing_it_asks_rather_than_doing_it() -> None:
    """Clearing overrides across a world is not undone by pressing the control
    again, so the press is a question and nothing else."""
    answer = run_page(
        [
            {"receive": state(settings=settings(SWEEPABLE_ROW))},
            {"click": {"under": "settings-rows", "attr": "data-apply-all",
                       "is": "activationRadius"}},
        ]
    )

    assert actions(answer, "clearEntityOverrides") == [{"key": "activationRadius"}]
    # And the confirmation is not on screen until the answer comes back.
    assert node(answer, "bulk-dialog")["hidden"] is True


def test_the_question_names_how_many_it_will_change() -> None:
    """The number is the server's -- it is the side about to do it -- and the
    page names the setting in the same words its row does."""
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(
                        SWEEPABLE_ROW,
                        pendingClear={"key": "activationRadius", "count": 3},
                    ),
                    locale={
                        "settings.activationRadius": "Activation Zone radius (m)",
                        "settings.applyToAll.question": "%d of them say %s",
                    },
                )
            }
        ]
    )

    assert node(answer, "bulk-dialog")["hidden"] is False
    assert node(answer, "bulk-question")["text"] == (
        "3 of them say Activation Zone radius (m)"
    )
    assert node(answer, "bulk-confirm")["disabled"] is False


def test_nothing_to_clear_says_so_and_offers_no_confirmation() -> None:
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(
                        SWEEPABLE_ROW,
                        pendingClear={"key": "activationRadius", "count": 0},
                    ),
                    locale={"settings.applyToAll.none": "none of them"},
                )
            }
        ]
    )

    assert node(answer, "bulk-question")["text"] == "none of them"
    assert node(answer, "bulk-confirm")["disabled"] is True


def test_confirming_names_the_setting_the_question_was_about() -> None:
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(
                        SWEEPABLE_ROW,
                        pendingClear={"key": "activationRadius", "count": 3},
                    )
                )
            },
            {"click": {"id": "bulk-confirm"}},
        ]
    )

    assert actions(answer, "clearEntityOverrides") == [
        {"key": "activationRadius", "confirmed": True}
    ]


def test_cancelling_is_a_real_answer() -> None:
    """It leaves the world alone, and it says so to Lua rather than only
    hiding the dialog -- the page decides nothing, including this."""
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(
                        SWEEPABLE_ROW,
                        pendingClear={"key": "activationRadius", "count": 3},
                    )
                )
            },
            {"click": {"id": "bulk-cancel"}},
        ]
    )

    assert actions(answer, "cancelClearEntityOverrides") == [{}]
    assert actions(answer, "clearEntityOverrides") == []


def test_apply_to_all_is_on_the_row_of_the_field_it_applies() -> None:
    """Under the field it belongs to, each setting took two rows and the screen
    was twice as tall as it needed to be -- which is half of why Settings could
    not sit beside the list it is about.

    Asked of the tree rather than of the stylesheet, so what it can see is
    order: the cells of a row flow in the order they are appended, and this one
    now comes straight after the field rather than after the sentence that
    belongs under it. Whether the grid then has a third column for it to land in
    is a fact only a rendered page has, and stays on the ticket's manual list.
    """
    # A row with both, because the two used to be the other way round -- the
    # sentence, then the sweep -- and a row without a sentence cannot tell.
    row = dict(SWEEPABLE_ROW, noteKey="settings.activationRadius.note")
    answer = run_page([{"receive": state(settings=settings(row))}])

    drawn = one(node(answer, "settings-rows"), cls="setting")
    order = [child["cls"] for child in drawn["children"]]
    assert "setting-apply-all" in order
    assert "setting-note" in order
    # Label, the field, this. Then what is genuinely below the row: the sentence
    # under the control and the reason a value was refused.
    assert order.index("setting-apply-all") == order.index("setting-label") + 2
    assert order.index("setting-apply-all") < order.index("setting-note")
    assert order.index("setting-apply-all") < order.index("field-error")


# --- the entity pane sits beside the list, not on top of it ------------------
#
# The screen that covered the Map Entity list was the *entity pane* -- the
# fields that edit the selected row -- not the panel's own Settings screen. It
# was a block under the list and grew with every ticket in this wave until it
# took the list's own height. Settings is a screen again, as it was.


def workspace_columns(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        child
        for child in node(answer, "workspace")["children"]
        if has_class(child, "column")
    ]


def test_the_entity_pane_is_a_column_of_the_workspace() -> None:
    """Beside the list rather than under it, and first, so it is to the left of
    the list rather than off past the cards."""
    answer = run_page([{"receive": state(entities=[entity()])}])

    column = node(answer, "entity-column")
    assert column["hidden"] is False
    assert [child["id"] for child in workspace_columns(answer)][0] == "entity-column"
    # And the fields really moved: the pane is inside that column and nowhere
    # else, so nothing is left under the list where it used to be.
    assert node(answer, "entity-settings") in list(walk(column))


def test_the_pane_and_the_list_are_different_columns() -> None:
    """The defect, stated: the pane was inside the list's own column, so the
    taller it got the less of the list there was."""
    answer = run_page([{"receive": state(entities=[entity()])}])

    pane_column = node(answer, "entity-column")
    assert node(answer, "rows") not in list(walk(pane_column))
    # The list is in the column after it, which is what "to the left of the
    # list" means.
    columns = workspace_columns(answer)
    assert node(answer, "rows") in list(walk(columns[1]))


def test_the_entity_list_stays_readable_while_the_pane_is_open() -> None:
    """The whole point: the list does not lose its own column to the fields
    that edit a row of it."""
    answer = run_page([{"receive": state(entities=[entity(), entity(entityId="b")])}])

    assert node(answer, "section-entities")["hidden"] is False
    assert node(answer, "rows")["hidden"] is False
    assert len(descendants(node(answer, "rows"), cls="row")) == 2


def test_the_pane_never_folds_away() -> None:
    """Unlike the card editor's column, which comes and goes: a card is edited
    now and then, and a row is selected in order to be edited -- so the pane
    that edits it has nothing to wait for. There is no control that shuts it and
    no state in which it is not drawn."""
    for step in (
        {"receive": state()},
        {"receive": state(entities=[entity()])},
        {"receive": selecting(entity())},
        {"receive": with_note()},
    ):
        answer = run_page([step])
        assert node(answer, "entity-column")["hidden"] is False, step


def test_settings_is_a_screen_of_its_own_again() -> None:
    """It was moved beside the list by mistake. There is nothing behind the
    window to look at while the panel's own settings are changed, so a screen is
    the right shape for them."""
    answer = run_page([{"receive": state(section="settings")}])

    assert node(answer, "section-settings")["hidden"] is False
    assert node(answer, "section-entities")["hidden"] is True
    # Not a column of the workspace: nothing named one is left behind.
    with pytest.raises(AssertionError):
        node(answer, "settings-column")
    assert [child["id"] for child in workspace_columns(answer)] == [
        "entity-column", "", "", "inspector"
    ]


def test_the_settings_screen_is_asked_for_and_left_by_lua() -> None:
    asked = run_page([{"receive": state()}, {"click": {"id": "settings"}}])
    assert actions(asked, "openSettings") == [{}]
    # Not shown by the click itself: Lua has not answered yet.
    assert node(asked, "section-settings")["hidden"] is True

    shut = run_page(
        [{"receive": state(section="settings")}, {"click": {"id": "close-settings"}}]
    )
    assert actions(shut, "closeSettings") == [{}]


def test_the_editor_still_slides_out_beside_the_three() -> None:
    """The page cannot resize its own window, so it says which shape it is in
    and `client/panel.lua` gives it the room."""
    shut = run_page([{"receive": with_note()}])
    assert str(node(shut, "workspace")["cls"]).split() == ["workspace"]

    out = run_page([{"receive": with_note()}, {"click": {"id": "toggle-inspector"}}])
    assert "editing" in str(node(out, "workspace")["cls"]).split()
    assert [step["open"] for step in actions(out, "editorVisible")] == [True]


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


# --- what per-map settings left behind ---------------------------------------
#
# Ticket 02 removed per-map settings and ticket 03 left their branches here:
# a `heading` and a `note` row kind that only the per-map group used, a
# `per-map` class on a row, and a `mapId` travelling with every change. All four
# have been inert since, and inert code is code the next reader has to decide is
# inert.


@pytest.mark.parametrize("kind", ["boolean", "choice", "color", "number"])
def test_a_change_carries_no_map_with_it(kind: str) -> None:
    """There is no per-map setting for a map to belong to."""
    rows = {
        "boolean": (BOOLEAN_ROW, {"click": {"id": "set-muteGameWorld"}}),
        "choice": (
            CHOICE_ROW,
            {"click": {"under": "settings-rows", "attr": "data-value",
                       "is": "allow_all"}},
        ),
        "color": (
            COLOR_ROW,
            {"click": {"under": "settings-rows", "attr": "data-value",
                       "is": "#ef4444"}},
        ),
        "number": (NUMBER_ROW, {"change": {"id": "set-activationRadius"}}),
    }
    row, act = rows[kind]
    answer = run_page([{"receive": state(settings=settings(row))}, act])

    sent = actions(answer, "setSetting")
    assert sent, kind
    assert all("mapId" not in payload for payload in sent), sent


def test_no_row_claims_to_belong_to_one_map() -> None:
    answer = run_page(
        [{"receive": state(settings=settings(NUMBER_ROW, CHOICE_ROW))}]
    )

    assert descendants(node(answer, "settings-rows"), cls="per-map") == []


def test_a_row_kind_the_schema_cannot_produce_is_not_drawn_as_prose() -> None:
    """`heading` and `note` were the per-map group's own two kinds, and rows are
    derived from the schema -- whose rules are boolean, choice, key, number,
    color, secret and placement. A page that still drew a heading would be
    holding open a door to a room that was demolished."""
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(
                        {"kind": "heading", "key": "group", "labelKey": "x"},
                        {"kind": "note", "key": "aside", "labelKey": "y"},
                    )
                )
            }
        ]
    )

    rows = node(answer, "settings-rows")
    assert descendants(rows, cls="setting-heading") == []
    assert descendants(rows, cls="setting-note") == []


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
                    locale={"f7.inherited": "following Settings"},
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

    assert actions(answer, "setEntityMarks") == [{"radius": "inherit"}]


# --- one way back to the global, and only one --------------------------------
#
# An override was cleared in two different ways: a `Follow Settings` entry
# inside each drawn list, and a second button inside the colour picker's own
# surface. Two spellings of one idea -- and the list entry made "stop having an
# opinion" look like one of the values a setting can hold.

#: Every field on the entity pane that can hold this entity's own answer, and
#: the value each is given so that it does. The pane is written out field by
#: field in `index.html`, so this is written out too: a list derived from the
#: page would agree with the page by construction and prove nothing.
#:
#: What holds it to the schema is
#: `test_a_field_the_schema_lets_an_entity_override_has_the_button`.
OVERRIDABLE_FIELDS = [
    ("radius", 7.5),
    ("activationType", "key"),
    ("activationKey", "q"),
    ("showCorona", True),
    ("coronaColor", "#ff8000"),
    ("coronaOpacity", 0.25),
    ("textLabelField", "Back"),
    ("textLabelColor", "#ff8000"),
    ("textLabelSize", 2),
]


def test_a_field_the_schema_lets_an_entity_override_has_the_button() -> None:
    """"Everywhere one can be set" is the schema's answer, not the page's.

    The pane is hand-written markup, so the nine buttons are hand-written too --
    which is fine right up until a tenth setting gains an override. Its sibling
    `Apply to all` appears by itself, because Lua sends `clearOverrides` off the
    schema; this one would silently never appear, and a Map Entity told
    something months ago could only be told otherwise by emptying a box that
    two of these fields do not have.
    """
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        keys = sandbox.eval("ANKIGTA.Settings.entityOverridableKeys()")
        field_of = sandbox.eval(
            "function(k) return ANKIGTA.Settings.entityOverrideField(k) end"
        )
        overridable = {
            str(field_of(str(keys[index]))) for index in keys.keys()
        }
    finally:
        sandbox.close()

    answer = run_page([{"receive": selecting(entity())}])
    drawn = {
        candidate["attrs"]["data-restore-global"]
        for candidate in walk(answer["tree"])
        if "data-restore-global" in candidate["attrs"]
    }

    assert overridable, "the schema declares no overrides, so this proves nothing"
    assert drawn == overridable
    # And the fixture below covers each of them, so a tenth is not merely drawn.
    assert {field for field, _value in OVERRIDABLE_FIELDS} == overridable


@pytest.mark.parametrize("field,value", OVERRIDABLE_FIELDS)
def test_one_control_clears_an_override_wherever_one_can_be_set(
    field: str, value: Any
) -> None:
    """The same button, named for what it does, on every one of them."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(**{field: value, field + "Inherited": False})
                )
            },
            {"click": {"attr": "data-restore-global", "is": field}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{field: "inherit"}]


def test_it_asks_to_follow_rather_than_storing_a_copy_of_todays_global() -> None:
    """The distinction the whole control exists for: an entity that follows
    moves when the global moves, and one holding a copy of today's value does
    not. Both look identical on screen the day they are set."""
    answer = run_page(
        [
            {"receive": selecting(entity(radius=7.5, radiusInherited=False))},
            {"click": {"attr": "data-restore-global", "is": "radius"}},
        ]
    )

    sent = actions(answer, "setEntityMarks")
    assert sent == [{"radius": "inherit"}]
    # Not the number that was on screen, which is what "clear" would mean if it
    # were read as "set it to what Settings says right now".
    assert sent[0]["radius"] != 7.5


def test_follow_settings_is_gone_from_the_drawn_lists() -> None:
    """A list of the values a setting can hold, and nothing else. "Follows the
    global" is not one of them: it is the absence of an answer."""
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {"receive": state(settings=settings(CHOICE_ROW))},
        ]
    )

    offered = [
        candidate["attrs"].get("data-value")
        for candidate in walk(answer["tree"])
        if has_class(candidate, "picker-option")
    ]
    assert offered, "no drawn list was built at all"
    assert "inherit" not in offered


def test_follow_settings_is_gone_from_the_colour_picker() -> None:
    """The picker chooses a colour. Undoing a choice is the button beside it,
    which is the same button the eight fields around it carry."""
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {"receive": state(settings=settings(COLOR_ROW))},
        ]
    )

    assert [
        candidate
        for candidate in walk(answer["tree"])
        if "data-picker-clear" in candidate["attrs"]
        or has_class(candidate, "picker-clear")
    ] == []


def test_a_field_already_following_has_nothing_to_restore() -> None:
    """The control keeps its place and goes quiet, the way every field on this
    pane does -- offering a change that changes nothing is worse than saying
    there is nothing to change."""
    following = run_page([{"receive": selecting(entity(radiusInherited=True))}])
    assert restore_button(following, "radius")["disabled"] is True

    own = run_page(
        [{"receive": selecting(entity(radius=7.5, radiusInherited=False))}]
    )
    assert restore_button(own, "radius")["disabled"] is False

    # And with no row selected there is nothing whose override to clear.
    nothing = run_page([{"receive": state()}])
    assert restore_button(nothing, "radius")["disabled"] is True


# --- how the entity says it is marked ----------------------------------------


def test_the_pane_offers_show_corona_and_no_draw_always() -> None:
    """`Draw always` made a drawn radius permanent, which confused a way of
    looking with a property of the thing. What is on the pane is the second;
    the first is a client setting now.

    A list rather than a checkbox, because there are three answers: on, off,
    and following the global that ticket 05 put behind it."""
    answer = run_page([{"receive": selecting(entity(showCorona=True))}])

    assert picker_button(answer, "entityShowCorona")["text"] == "settings.value.true"
    for gone in ("entity-draw-always", "entity-draw-now"):
        with pytest.raises(AssertionError):
            node(answer, gone)


def test_showing_a_corona_is_sent_to_the_entity() -> None:
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {
                "click": {
                    "under": "entity-show-corona",
                    "attr": "data-picker",
                    "is": "entityShowCorona",
                }
            },
            {
                "click": {
                    "under": "entity-show-corona",
                    "attr": "data-value",
                    "is": "true",
                }
            },
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"showCorona": True}]


def test_an_entity_can_be_put_back_on_the_global_that_governs_it() -> None:
    """`Restore global`, the one control that does this on every field.

    It used to be the last entry in the list, which made "stop having an
    opinion" look like one of the values `Show corona` can hold."""
    answer = run_page(
        [
            {"receive": selecting(entity(showCorona=True, showCoronaInherited=False))},
            {"click": {"attr": "data-restore-global", "is": "showCorona"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"showCorona": "inherit"}]


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
                    locale={"f7.inherited": "following Settings"},
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
    would be refused too. `Restore global` beside the field says it.

    In the word the store keeps for "nothing of its own", which is the bug this
    replaces rather than only the duplicate control: the picker's own button
    sent `false`, the server understands only `"inherit"`, and clearing a corona
    colour had been refused as `settings.error.not_a_color` since ticket 05."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(coronaColor="#ff8000", coronaColorInherited=False)
                )
            },
            {"click": {"attr": "data-restore-global", "is": "coronaColor"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"coronaColor": "inherit"}]


def test_a_push_does_not_take_a_half_typed_colour_out_from_under_the_player() -> None:
    """A state push happens whenever anything at all changes -- a car streaming
    in will do it -- and the picker owns a hex box somebody may be part-way
    through. The radius box has been guarded since ticket 03; this is the same
    guard, for the same reason."""
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {
                "set": {
                    "attr": "data-color-hex",
                    "is": "entityCoronaColor",
                    "value": "#ff3",
                }
            },
            {"receive": selecting(entity())},
        ]
    )

    box = [
        candidate
        for candidate in walk(answer["tree"])
        if candidate["attrs"].get("data-color-hex") == "entityCoronaColor"
    ][0]
    assert box["value"] == "#ff3"


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

    assert actions(answer, "setEntityMarks") == [{"coronaOpacity": "inherit"}]


def test_a_typed_opacity_is_sent_as_the_number_it_is() -> None:
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {"set": {"id": "entity-corona-opacity", "value": "0.25"}},
            {"change": {"id": "entity-corona-opacity"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"coronaOpacity": 0.25}]


# --- what the object says, in Review mode `Show text` ------------------------


def test_the_pane_offers_the_three_things_a_text_label_is_made_of() -> None:
    """Field, colour and size, each on the row where the overrides are set --
    so a player can set them without changing mode first."""
    answer = run_page([{"receive": selecting(entity())}])

    assert node(answer, "entity-text-label-field")["disabled"] is False
    assert node(answer, "entity-text-label-size")["disabled"] is False
    assert picker_button(answer, "entityTextLabelColor")["disabled"] is False


def test_the_text_label_controls_show_the_values_in_force() -> None:
    """The entity's own where it has one, the global where it has not: a blank
    box would claim the entity has no answer when it plainly has."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(
                        textLabelField="Back",
                        textLabelFieldInherited=False,
                        textLabelSize=2.5,
                        textLabelSizeInherited=False,
                        textLabelColor="#ff8000",
                        textLabelColorInherited=False,
                    )
                )
            }
        ]
    )

    assert node(answer, "entity-text-label-field")["value"] == "Back"
    assert node(answer, "entity-text-label-size")["value"] == "2.5"
    assert (
        picker_button(answer, "entityTextLabelColor")["attrs"]["data-value"]
        == "#ff8000"
    )


def test_a_text_label_setting_that_is_inherited_says_so() -> None:
    following = run_page(
        [
            {
                "receive": selecting(
                    entity(), locale={"f7.inherited": "following Settings"}
                )
            }
        ]
    )
    for control in (
        "entity-text-label-field-inherited",
        "entity-text-label-color-inherited",
        "entity-text-label-size-inherited",
    ):
        assert node(following, control)["hidden"] is False, control
        assert node(following, control)["text"] == "following Settings"

    chosen = run_page(
        [
            {
                "receive": selecting(
                    entity(
                        textLabelField="Back",
                        textLabelFieldInherited=False,
                        textLabelColor="#ff8000",
                        textLabelColorInherited=False,
                        textLabelSize=2.5,
                        textLabelSizeInherited=False,
                    )
                )
            }
        ]
    )
    for control in (
        "entity-text-label-field-inherited",
        "entity-text-label-color-inherited",
        "entity-text-label-size-inherited",
    ):
        assert node(chosen, control)["hidden"] is True, control


def test_a_typed_field_and_size_are_sent_as_this_entitys_own() -> None:
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {"set": {"id": "entity-text-label-field", "value": "Back"}},
            {"change": {"id": "entity-text-label-field"}},
            {"set": {"id": "entity-text-label-size", "value": "2.5"}},
            {"change": {"id": "entity-text-label-size"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [
        {"textLabelField": "Back"},
        {"textLabelSize": 2.5},
    ]


def test_emptying_a_text_label_box_asks_to_follow_settings_again() -> None:
    """The two rules every box on this pane follows, and the word ticket 05
    settled on: `"inherit"`, never `false`."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(
                        textLabelField="Back",
                        textLabelFieldInherited=False,
                        textLabelSize=2.5,
                        textLabelSizeInherited=False,
                    )
                )
            },
            {"set": {"id": "entity-text-label-field", "value": ""}},
            {"change": {"id": "entity-text-label-field"}},
            {"set": {"id": "entity-text-label-size", "value": ""}},
            {"change": {"id": "entity-text-label-size"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [
        {"textLabelField": "inherit"},
        {"textLabelSize": "inherit"},
    ]


def test_the_text_label_colour_is_chosen_in_the_picker_this_panel_already_has(
) -> None:
    """Ticket 03's, the one the corona's colour uses. A native colour dialog
    has nowhere to open over a page rendered into a game window, and a third
    way to choose a colour would be a third thing to keep in step."""
    answer = run_page(
        [
            {"receive": selecting(entity())},
            {
                "click": {
                    "under": "entity-text-label-color",
                    "attr": "data-picker",
                    "is": "entityTextLabelColor",
                }
            },
            {
                "click": {
                    "under": "entity-text-label-color",
                    "attr": "data-value",
                    "is": "#f97316",
                }
            },
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"textLabelColor": "#f97316"}]


def test_the_text_label_colour_can_be_handed_back_to_settings() -> None:
    """By the same button every other field on the pane carries, rather than by
    a second one hidden inside the colour picker's own surface."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(
                        textLabelColor="#ff8000", textLabelColorInherited=False
                    )
                )
            },
            {"click": {"attr": "data-restore-global", "is": "textLabelColor"}},
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"textLabelColor": "inherit"}]


def test_the_row_says_what_the_object_really_shows() -> None:
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(textLabel=text_label(fieldName="Front", lines=["hola"])),
                    locale={"f7.textLabel.showing": "Showing %s: %s"},
                )
            }
        ]
    )

    assert node(answer, "entity-text-label-state")["text"] == "Showing Front: hola"


def test_a_falling_back_label_reads_as_falling_back_rather_than_correct() -> None:
    """The box says `Meaning` and the object says something else. Without this
    the row reads as correct."""
    missing = run_page(
        [
            {
                "receive": selecting(
                    entity(
                        textLabelField="Meaning",
                        textLabelFieldInherited=False,
                        textLabel=text_label(
                            requestedField="Meaning",
                            fieldName="Front",
                            fallback=True,
                            reason="field_missing",
                        ),
                    ),
                    locale={
                        "f7.textLabel.fallbackMissing":
                            'No field "%s", so "%s" is shown: %s'
                    },
                )
            }
        ]
    )
    assert (
        node(missing, "entity-text-label-state")["text"]
        == 'No field "Meaning", so "Front" is shown: hola'
    )

    wordless = run_page(
        [
            {
                "receive": selecting(
                    entity(
                        textLabel=text_label(
                            requestedField="Front",
                            fieldName="Back",
                            fallback=True,
                            reason="field_wordless",
                            lines=["hello"],
                        )
                    ),
                    locale={
                        "f7.textLabel.fallbackWordless":
                            '"%s" holds no words, so "%s" is shown: %s'
                    },
                )
            }
        ]
    )
    assert (
        node(wordless, "entity-text-label-state")["text"]
        == '"Front" holds no words, so "Back" is shown: hello'
    )


def test_a_note_whose_words_look_like_a_pattern_is_drawn_as_written() -> None:
    """`String.replace` reads `$&` out of its *replacement*, and what goes in
    here is a card's own words. A card whose front is `$&` was drawn as the
    sentence around it."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(textLabel=text_label(lines=["$& and $`"])),
                    locale={"f7.textLabel.showing": "Showing %s: %s"},
                )
            }
        ]
    )

    assert (
        node(answer, "entity-text-label-state")["text"]
        == "Showing Front: $& and $`"
    )


def test_a_row_whose_card_is_missing_is_not_told_no_card_is_linked() -> None:
    """A card is linked; Anki no longer has it. The row's own state cell says
    so, and a second line claiming nothing is linked is simply false."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(linkState="Card missing", textLabel=False),
                    locale={"f7.textLabel.notLinked": "No card is linked."},
                )
            }
        ]
    )

    assert node(answer, "entity-text-label-state")["text"] == ""


def test_a_row_with_nothing_cached_or_nothing_linked_says_which() -> None:
    """Silence would be indistinguishable from a note that says nothing."""
    uncached = run_page(
        [
            {
                "receive": selecting(
                    entity(textLabel=text_label(reason="not_cached", lines=[])),
                    locale={"f7.textLabel.notCached": "Not read from Anki yet."},
                )
            }
        ]
    )
    assert (
        node(uncached, "entity-text-label-state")["text"]
        == "Not read from Anki yet."
    )

    unlinked = run_page(
        [
            {
                "receive": selecting(
                    entity(textLabel=False),
                    locale={"f7.textLabel.notLinked": "No card is linked."},
                )
            }
        ]
    )
    assert node(unlinked, "entity-text-label-state")["text"] == "No card is linked."


def test_the_review_mode_row_says_that_reading_does_not_rate() -> None:
    """Where the mode is chosen, rather than left to be discovered. A setting
    gains the sentence by gaining the string; the page keeps no list."""
    answer = run_page(
        [
            {
                "receive": state(
                    section="settings",
                    settings={
                        "rows": [
                            {
                                **CHOICE_ROW,
                                "options": ["allow_due", "allow_all", "show_text"],
                                "noteKey": "settings.reviewMode.note",
                            }
                        ]
                    },
                    locale={
                        "settings.reviewMode.note": "Reading a label rates nothing."
                    },
                )
            }
        ]
    )

    notes = [
        candidate
        for candidate in walk(node(answer, "settings-rows"))
        if candidate["attrs"].get("data-setting-note") == "reviewMode"
    ]
    assert len(notes) == 1
    assert notes[0]["text"] == "Reading a label rates nothing."


def test_a_setting_with_nothing_extra_to_say_carries_no_note() -> None:
    answer = run_page(
        [
            {
                "receive": state(
                    section="settings", settings={"rows": [NUMBER_ROW]}
                )
            }
        ]
    )

    assert (
        [
            candidate
            for candidate in walk(node(answer, "settings-rows"))
            if "data-setting-note" in candidate["attrs"]
        ]
        == []
    )


# --- `Draw radius` is beside `Show corona`, and is still the player's --------


def label_of(answer: dict[str, Any], control_id: str) -> dict[str, Any]:
    """The `<label>` a control sits in, so a test can ask what is next to it."""
    for candidate in walk(node(answer, "entity-fields")):
        if any(child["id"] == control_id for child in walk(candidate)):
            if candidate["tag"] == "LABEL":
                return candidate
    raise AssertionError(f"#{control_id} is not inside a label on the pane")


def test_draw_radius_sits_next_to_show_corona_on_the_entity_pane() -> None:
    """Ticket 04 pulled the two apart correctly -- one is a way of looking and
    the other is a property of the entity -- and then left them on different
    screens. In use that is the wrong seam: both answer "what do I see around
    this row", both are reached while a row is selected, and walking to Settings
    to turn one on and back to the list to turn the other on is two journeys for
    one decision.
    """
    answer = run_page([{"receive": selecting(entity())}])

    rows = node(answer, "entity-fields")["children"]
    drawing = rows.index(label_of(answer, "entity-draw-radius"))
    corona = rows.index(label_of(answer, "entity-show-corona"))
    assert abs(drawing - corona) == 1


def test_draw_radius_is_a_checkbox_rather_than_a_yes_no_button() -> None:
    """Two states is what a checkbox is. It was a button reading `On` or `Off`,
    which is a control whose state has to be read as a word before it can be
    understood -- and a tick is the one control every player already knows.

    Nothing else on this pane can be one: every other field here has a third
    answer, "whatever Settings says"."""
    answer = run_page([{"receive": selecting(entity(), drawRadius=True)}])

    box = node(answer, "entity-draw-radius")
    assert box["tag"] == "INPUT"
    assert box["attrs"]["type"] == "checkbox"
    # Not a drawn list either: those carry a third entry this control has no
    # meaning for.
    assert descendants(label_of(answer, "entity-draw-radius"), cls="picker-option") == []


def test_the_tick_says_which_of_the_two_it_currently_is() -> None:
    """A control whose label is the action rather than the state leaves the
    player guessing which way it is set. A checkbox says it by being ticked."""
    on = run_page([{"receive": selecting(entity(), drawRadius=True)}])
    assert node(on, "entity-draw-radius")["checked"] is True

    off = run_page([{"receive": selecting(entity(), drawRadius=False)}])
    assert node(off, "entity-draw-radius")["checked"] is False


def test_draw_radius_is_sent_as_a_setting_and_never_as_an_override() -> None:
    """It stays the client's own. An entity has nothing to say about a way of
    looking, so nothing about it is written to the entity."""
    answer = run_page(
        [
            {"receive": selecting(entity(), drawRadius=False)},
            {"check": {"id": "entity-draw-radius", "value": True}},
            {"change": {"id": "entity-draw-radius"}},
        ]
    )

    assert actions(answer, "setSetting") == [{"key": "drawRadius", "value": True}]
    assert actions(answer, "setEntityMarks") == []


def test_ticking_it_off_again_says_so() -> None:
    off = run_page(
        [
            {"receive": selecting(entity(), drawRadius=True)},
            {"check": {"id": "entity-draw-radius", "value": False}},
            {"change": {"id": "entity-draw-radius"}},
        ]
    )

    assert actions(off, "setSetting") == [{"key": "drawRadius", "value": False}]


def test_the_tick_follows_what_lua_says_rather_than_the_click() -> None:
    """What is sent is the opposite of what Lua last reported, not the state the
    browser just put the box in -- so a push that disagrees puts the tick back
    rather than leaving the page and the resource saying different things."""
    answer = run_page(
        [
            {"receive": selecting(entity(), drawRadius=False)},
            # The browser ticks the box itself, before anything is sent.
            {"check": {"id": "entity-draw-radius", "value": True}},
            {"change": {"id": "entity-draw-radius"}},
            # The setting was refused, or somebody else changed it back.
            {"receive": selecting(entity(), drawRadius=False)},
        ]
    )

    assert node(answer, "entity-draw-radius")["checked"] is False


def test_draw_radius_stays_usable_with_no_row_selected() -> None:
    """The rest of the pane goes quiet without a selection because it edits the
    selected entity. This one is the player's own answer and outlives any one
    row, so greying it out would say it belonged to the entity."""
    answer = run_page([{"receive": state()}])

    assert node(answer, "entity-draw-radius")["disabled"] is False
    assert node(answer, "entity-radius")["disabled"] is True


def test_with_nothing_selected_the_marks_controls_are_disabled() -> None:
    """The pane keeps its place rather than coming and going, so the fields are
    disabled instead of removed."""
    answer = run_page([{"receive": state()}])

    assert picker_button(answer, "entityShowCorona")["disabled"] is True
    assert picker_button(answer, "entityActivationType")["disabled"] is True
    assert key_button(answer, "entityActivationKey")["disabled"] is True
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


# --- a key is bound, not chosen ----------------------------------------------
#
# It was a dropdown over every key MTA can name, so a player who wanted `E`
# scrolled a hundred entries looking for it -- and the list was the wrong shape
# for the question anyway. The answer is a key, and the way a person says which
# key is to press it.


def press(code: str, key: str | None = None) -> dict[str, Any]:
    """One keydown, as CEF delivers one.

    `code` is the physical key and is what a binding is made of: MTA binds a
    virtual key, so the key marked A binds `a` on a Russian layout too, where
    `event.key` would be `ф`.
    """
    return {"key": {"code": code, "key": key if key is not None else code}}


def start_capture(name: str) -> dict[str, Any]:
    return {"click": {"attr": "data-key-capture", "is": name}}


def test_the_key_control_is_not_a_list_of_a_hundred_names() -> None:
    answer = run_page([{"receive": state(settings=settings(KEY_ROW))}])

    row = node(answer, "settings-rows")
    assert descendants(row, cls="picker-option") == []
    assert key_button(answer, "activationKey")["text"] == "e"


def test_the_globally_set_key_is_answered_by_pressing_it() -> None:
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(KEY_ROW),
                    locale={"f7.pressAKey": "Press a key…"},
                )
            },
            start_capture("activationKey"),
            press("KeyQ", "q"),
        ]
    )

    assert actions(answer, "setSetting") == [
        {"key": "activationKey", "value": "q"}
    ]
    # And it stops listening once it has an answer.
    assert key_button(answer, "activationKey")["attrs"]["aria-pressed"] == "false"
    assert key_button(answer, "activationKey")["text"] == "q"


def test_the_control_says_it_is_waiting_rather_than_looking_unchanged() -> None:
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(KEY_ROW),
                    locale={"f7.pressAKey": "Press a key… (Esc cancels)"},
                )
            },
            start_capture("activationKey"),
        ]
    )

    button = key_button(answer, "activationKey")
    assert button["text"] == "Press a key… (Esc cancels)"
    assert button["attrs"]["aria-pressed"] == "true"


def test_a_per_link_key_is_set_the_same_way() -> None:
    """One control, wherever the question is asked. The entity's is an override
    and the global's is a setting, which is the only difference between them --
    and both judge a press by the same two lists, which arrive on the same
    settings row.
    """
    answer = run_page(
        [
            {"receive": selecting(entity(), settings=settings(KEY_ROW))},
            start_capture("entityActivationKey"),
            press("KeyQ", "q"),
        ]
    )

    assert actions(answer, "setEntityMarks") == [{"activationKey": "q"}]

    refused = run_page(
        [
            {
                "receive": selecting(
                    entity(),
                    settings=settings(KEY_ROW),
                    locale={"settings.error.key_in_use": "already in use"},
                )
            },
            start_capture("entityActivationKey"),
            press("F7"),
        ]
    )
    assert actions(refused, "setEntityMarks") == []
    assert key_refusal(refused, "entityActivationKey")["text"] == "already in use"


def test_a_list_and_a_control_waiting_for_a_key_are_not_both_open() -> None:
    """Only one of them can be what the next click or press is for."""
    listening = run_page(
        [
            {"receive": selecting(entity(), settings=settings(KEY_ROW))},
            {
                "click": {
                    "under": "entity-show-corona",
                    "attr": "data-picker",
                    "is": "entityShowCorona",
                }
            },
            start_capture("entityActivationKey"),
        ]
    )
    assert one(node(listening, "entity-show-corona"), cls="picker-panel")[
        "hidden"
    ] is True

    opened = run_page(
        [
            {"receive": selecting(entity(), settings=settings(KEY_ROW))},
            start_capture("entityActivationKey"),
            {
                "click": {
                    "under": "entity-show-corona",
                    "attr": "data-picker",
                    "is": "entityShowCorona",
                }
            },
            press("KeyQ", "q"),
        ]
    )
    assert actions(opened, "setEntityMarks") == []


@pytest.mark.parametrize(
    "code,name",
    [
        ("KeyE", "e"),
        ("Digit4", "4"),
        ("F9", "F9"),
        ("Numpad3", "num_3"),
        ("NumpadEnter", "num_enter"),
        ("ArrowLeft", "arrow_l"),
        ("PageDown", "pgdn"),
        ("ShiftRight", "rshift"),
        ("Space", "space"),
    ],
)
def test_the_key_that_was_pressed_is_named_the_way_mta_names_it(
    code: str, name: str
) -> None:
    """A stored key is the word `bindKey` takes, so the press has to arrive as
    that word rather than as whatever the keyboard produced."""
    row = dict(KEY_ROW, options=[name], bindableKeys=[name])
    answer = run_page(
        [
            {"receive": state(settings=settings(row))},
            start_capture("activationKey"),
            {"key": {"code": code}},
        ]
    )

    assert actions(answer, "setSetting") == [{"key": "activationKey", "value": name}]


def test_a_key_ankigta_already_answers_to_is_refused_on_the_press() -> None:
    """Refused rather than allowed to shadow: the panel's own key opening a card
    instead is a different feature breaking for a reason nobody could see. The
    reason is said where the press happened, at the moment it happened."""
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(KEY_ROW),
                    locale={
                        "settings.error.key_in_use": "ANKIGTA already uses that key"
                    },
                )
            },
            start_capture("activationKey"),
            press("F7"),
        ]
    )

    assert actions(answer, "setSetting") == []
    refusal = key_refusal(answer, "activationKey")
    assert refusal["hidden"] is False
    assert refusal["text"] == "ANKIGTA already uses that key"
    # Still listening: the answer to "not that one" is another key, and a
    # control that shut itself would have to be found and opened again.
    assert key_button(answer, "activationKey")["attrs"]["aria-pressed"] == "true"
    assert key_button(answer, "activationKey")["text"] != "F7"


def test_a_key_mta_cannot_name_is_refused_rather_than_stored() -> None:
    """`bindKey` refuses a name it does not know, and a refusal there is a
    setting that reads as saved and binds nothing. `F8` is the honest case: MTA
    keeps it for its own console, so it is a real key with no name here."""
    answer = run_page(
        [
            {
                "receive": state(
                    settings=settings(KEY_ROW),
                    locale={
                        "settings.error.not_a_key":
                            "That is not a key ANKIGTA can bind"
                    },
                )
            },
            start_capture("activationKey"),
            press("F8"),
            press("PrintScreen"),
        ]
    )

    assert actions(answer, "setSetting") == []
    refusal = key_refusal(answer, "activationKey")
    assert refusal["hidden"] is False
    assert refusal["text"] == "That is not a key ANKIGTA can bind"


def test_escape_stops_the_control_waiting_rather_than_closing_the_panel() -> None:
    """It is a key ANKIGTA already answers to, so it can never be the answer --
    which leaves it free to be the way out, and a control with no way out of it
    is worse than one that cannot be given `escape`."""
    answer = run_page(
        [
            {"receive": state(settings=settings(KEY_ROW))},
            start_capture("activationKey"),
            {"key": {"key": "Escape", "code": "Escape"}},
        ]
    )

    assert actions(answer, "close") == []
    assert actions(answer, "setSetting") == []
    assert key_button(answer, "activationKey")["attrs"]["aria-pressed"] == "false"


def test_a_control_waiting_for_a_key_takes_the_arrows_too() -> None:
    """Every key on the keyboard is a possible answer here, including the ones
    that walk the Map Entity list."""
    answer = run_page(
        [
            {
                "receive": selecting(
                    entity(), settings=settings(KEY_ROW)
                )
            },
            start_capture("entityActivationKey"),
            press("ArrowDown", "ArrowDown"),
        ]
    )

    # The list did not move: one row was selected before the press and the same
    # row is selected after it.
    assert actions(answer, "select") == []


def test_only_one_control_waits_at_a_time() -> None:
    """Two controls both listening would both take the same press."""
    answer = run_page(
        [
            {"receive": selecting(entity(), settings=settings(KEY_ROW))},
            start_capture("activationKey"),
            start_capture("entityActivationKey"),
            press("KeyQ", "q"),
        ]
    )

    assert actions(answer, "setSetting") == []
    assert actions(answer, "setEntityMarks") == [{"activationKey": "q"}]


def test_clicking_away_stops_a_control_waiting() -> None:
    answer = run_page(
        [
            {"receive": state(settings=settings(KEY_ROW))},
            start_capture("activationKey"),
            {"docclick": True},
            press("KeyQ", "q"),
        ]
    )

    assert actions(answer, "setSetting") == []


#: What a key MTA names is called in a browser keyboard event, for the families
#: that are a rule rather than a list.
#:
#: The inverse of the page's own table, written from the DOM's `code` values
#: rather than from `app.js`: the point of the check below is that the two
#: independently agree, and a table copied out of the page would agree with the
#: page by construction.
DOM_CODES = {
    "space": "Space", "enter": "Enter", "tab": "Tab",
    "backspace": "Backspace", "capslock": "CapsLock",
    "lshift": "ShiftLeft", "rshift": "ShiftRight",
    "lctrl": "ControlLeft", "rctrl": "ControlRight",
    "lalt": "AltLeft", "ralt": "AltRight",
    "insert": "Insert", "delete": "Delete", "home": "Home", "end": "End",
    "pgup": "PageUp", "pgdn": "PageDown",
    "arrow_l": "ArrowLeft", "arrow_u": "ArrowUp",
    "arrow_r": "ArrowRight", "arrow_d": "ArrowDown",
    "num_enter": "NumpadEnter", "escape": "Escape",
}


def dom_code(name: str) -> str:
    """The press that should produce MTA's `name`."""
    if len(name) == 1 and name.isalpha():
        return "Key" + name.upper()
    if len(name) == 1 and name.isdigit():
        return "Digit" + name
    if re.fullmatch(r"F[0-9]{1,2}", name):
        return name
    if re.fullmatch(r"num_[0-9]", name):
        return "Numpad" + name[-1]
    assert name in DOM_CODES, f"no browser code written down for {name}"
    return DOM_CODES[name]


def schema_key_lists() -> tuple[list[str], list[str]]:
    """Every key ANKIGTA can bind, and the part of it still free.

    Out of the loaded schema, because that is the side that decides: the page
    refuses from these two lists and the rule validates against the same ones.
    """
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        bindable = sandbox.eval("ANKIGTA.Settings.bindableKeys")
        offered = sandbox.eval("ANKIGTA.Settings.offeredKeys()")
        return (
            [str(bindable[index]) for index in bindable.keys()],
            [str(offered[index]) for index in offered.keys()],
        )
    finally:
        sandbox.close()


def test_every_key_the_schema_offers_can_actually_be_pressed() -> None:
    """The list is gone, so nothing enumerates the keys on screen any more --
    which makes "can this key be given at all" a question only a press answers.

    A key the schema is willing to bind and the page cannot name is a key no
    player can choose, and it would look exactly like the key simply not
    working.
    """
    bindable, offered = schema_key_lists()
    row = dict(KEY_ROW, options=offered, bindableKeys=bindable)

    script: list[dict[str, Any]] = [{"receive": state(settings=settings(row))}]
    for name in offered:
        script.append(start_capture("activationKey"))
        script.append({"key": {"code": dom_code(name)}})
    answer = run_page(script)

    assert [sent["value"] for sent in actions(answer, "setSetting")] == offered


def test_the_keys_ankigta_reserves_are_refused_by_the_same_press() -> None:
    """The other half: every key the schema keeps is one the page will not take,
    for the reason the schema gives. `escape` is the exception on purpose -- it
    is how a control stops waiting, so it can never reach the refusal."""
    bindable, offered = schema_key_lists()
    row = dict(KEY_ROW, options=offered, bindableKeys=bindable)
    reserved = [name for name in bindable if name not in offered]

    assert reserved, "the schema reserves nothing, so this proves nothing"
    for name in reserved:
        if name == "escape":
            continue
        answer = run_page(
            [
                {"receive": state(settings=settings(row))},
                start_capture("activationKey"),
                {"key": {"code": dom_code(name)}},
            ]
        )
        assert actions(answer, "setSetting") == [], name
        assert (
            key_refusal(answer, "activationKey")["text"]
            == "settings.error.key_in_use"
        ), name


def test_losing_the_selection_stops_the_entity_control_waiting() -> None:
    """A control still listening with no row under it would store the next press
    against whatever happens to be selected by then."""
    answer = run_page(
        [
            {"receive": selecting(entity(), settings=settings(KEY_ROW))},
            start_capture("entityActivationKey"),
            {"receive": state(settings=settings(KEY_ROW))},
            press("KeyQ", "q"),
        ]
    )

    assert actions(answer, "setEntityMarks") == []


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
    """The cosmetic name replaces the Map Editor's, which is the point -- but it
    also hides the only thing tying the row to what the Map Editor shows."""
    answer = run_page(
        [
            {
                "receive": state(
                    entities=[
                        entity(
                            name="North gate",
                            givenName="North gate",
                            originalName="object (gate) (1)",
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
    ] == ["originally object (gate) (1)"]


def test_a_row_nobody_renamed_says_its_name_once() -> None:
    answer = run_page([{"receive": state(entities=[entity(name="object (gate) (1)")])}])

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


# --- ticket 11: a window that gets out of the way ------------------------------


def test_the_reset_layout_button_is_gone() -> None:
    """`Reset UI layout` existed because a window could be put somewhere
    unreachable, and none can be now: F7 opens the panel at its default
    position every time, and the HUD keeps its clamp. Its neighbours stay."""
    answer = run_page([])

    ids = {candidate["id"] for candidate in walk(answer["tree"])}
    assert "reset-layout" not in ids
    assert "edit-hud" in ids
    assert "close-settings" in ids


def test_a_field_taking_focus_reports_typing_and_letting_go_ends_it() -> None:
    """The panel must not fade mid-sentence, and only the page knows where the
    keyboard focus is -- so it says, both ways."""
    answer = run_page(
        [
            {"focusin": {"tag": "INPUT"}},
            {"focusout": {"tag": "INPUT"}},
        ]
    )

    assert actions(answer, "typing") == [{"active": True}, {"active": False}]


def test_focus_hopping_from_one_field_to_another_is_still_typing() -> None:
    """Tab between fields fires focusout before focusin; a false between the
    two would let the panel start fading in the middle of a form."""
    answer = run_page(
        [
            {"focusin": {"tag": "INPUT"}},
            {"focusout": {"tag": "INPUT", "to": "TEXTAREA"}},
            {"focusin": {"tag": "TEXTAREA"}},
        ]
    )

    assert actions(answer, "typing") == [{"active": True}, {"active": True}]


def test_focus_landing_on_a_button_is_not_typing() -> None:
    answer = run_page([{"focusin": {"tag": "BUTTON"}}])

    assert actions(answer, "typing") == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

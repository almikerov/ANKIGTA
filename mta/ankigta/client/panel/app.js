/* ANKIGTA panel — the view.
 *
 * It holds no state and decides nothing. Lua sends a whole state and this
 * renders it; the player acts and this names the action. Keeping the decisions
 * on one side is what stops the panel and the resource from disagreeing about
 * what is on screen.
 */
(function () {
  "use strict";

  var locale = {};

  /** Translate, falling back to the key so a gap is visible rather than blank. */
  function t(key) {
    return Object.prototype.hasOwnProperty.call(locale, key) ? locale[key] : key;
  }

  function send(action, payload) {
    if (window.mta && window.mta.triggerEvent) {
      window.mta.triggerEvent(
        "ankigta:panelAction",
        action,
        JSON.stringify(payload || {})
      );
    }
  }

  function applyLocale() {
    var nodes = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < nodes.length; i += 1) {
      nodes[i].textContent = t(nodes[i].getAttribute("data-i18n"));
    }
    var hints = document.querySelectorAll("[data-i18n-placeholder]");
    for (var j = 0; j < hints.length; j += 1) {
      hints[j].placeholder = t(hints[j].getAttribute("data-i18n-placeholder"));
    }
    var titles = document.querySelectorAll("[data-i18n-title]");
    for (var k = 0; k < titles.length; k += 1) {
      titles[k].title = t(titles[k].getAttribute("data-i18n-title"));
    }
  }

  var selected = {mapId: false, entityId: false, cardId: false};
  var lastConnectionFields = null;
  var HIDDEN_TOKEN = "••••••••";
  /* The last rows rendered, and a readable label for the chosen card. Kept so
   * the replace confirmation can name what it is about to throw away without
   * asking Lua for a state it has already sent. */
  var lastEntities = [];
  var selectedCardLabel = "";

  /* A link state is a stable technical value; only its display comes from the
   * string table, and its tone is set here rather than in that table. */
  var TONES = {
    "Active Spatial Link": "good",
    "Unlinked": "",
    "Not adopted": "",
    "Pending Map Save": "warn",
    "Identity Collision": "bad",
    "Entity missing": "bad",
    "Card missing": "bad"
  };

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /* --- everything that offers a choice is drawn in the page ---------------
   *
   * A `<select>` opens a *native* popup, and this page has nowhere to put one:
   * MTA blits CEF's popup surface only while it fits inside the browser
   * rectangle and drops it whole otherwise, so the list vanishes exactly when
   * it grows. That is what "clicking a dropdown shows nothing" was, and it is
   * the same wall `<input type="color">` hit.
   *
   * So: one component, used by the deck, the Cards/Notes switch and every
   * choice in Settings. Two dropdowns where one is native and one is drawn
   * would look and behave differently for no reason a player could name.
   */

  /* The one popup that is open, if any. Opening a second closes the first, and
   * Escape closes it rather than the panel behind it. */
  var openPopup = null;

  /* How much room a list keeps clear of the window's edge, and how little room
   * below is too little to open into. */
  var MENU_MARGIN = 8;
  var MENU_MIN_ROOM = 120;

  function closeOpenPopup() {
    if (openPopup) openPopup.open(false);
  }

  /* Declared up here because a list opening puts it away, and the control it
   * belongs to is built further down. */
  function stopListeningForAKey() {
    if (listeningCapture) listeningCapture.listen(false);
  }

  /** A button and the surface it opens, drawn inside the page. */
  function drawnPopup(name) {
    var root = element("div", "picker");
    /* The control *is* the button, so a click anywhere on it opens the list.
     * The defect this replaces is one that opened only where a native widget
     * happened to draw its arrow. */
    var button = element("button", "picker-button");
    button.type = "button";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("data-picker", name);
    var panel = element("div", "picker-panel");
    panel.hidden = true;
    root.appendChild(button);
    root.appendChild(panel);

    /* Placed against the window rather than against the button's own box.
     *
     * An absolutely positioned list is clipped by any scroller between it and
     * its containing block, and `.settings-rows` is exactly that — so a choice
     * near the bottom of Settings would have opened a list that was cut off,
     * which is the defect this whole component exists to remove, rebuilt in
     * CSS. `position: fixed` has the window for a containing block, and no
     * ancestor here creates one for it (no transform, filter or contain).
     *
     * It opens downwards where there is room and upwards where there is not:
     * the panel is a window inside a game, so "there is not" is common. */
    function place() {
      if (!button.getBoundingClientRect) return;
      var rect = button.getBoundingClientRect();
      var height = (window.innerHeight || 0);
      var below = height - rect.bottom - MENU_MARGIN;
      var above = rect.top - MENU_MARGIN;
      panel.style.left = rect.left + "px";
      panel.style.minWidth = rect.width + "px";
      if (below < MENU_MIN_ROOM && above > below) {
        panel.style.top = "";
        panel.style.bottom = (height - rect.top + 2) + "px";
        panel.style.maxHeight = above + "px";
      } else {
        panel.style.bottom = "";
        panel.style.top = (rect.bottom + 2) + "px";
        panel.style.maxHeight = below + "px";
      }
    }

    var popup = {
      root: root,
      button: button,
      panel: panel,
      isOpen: function () {
        return panel.hidden !== true;
      },
      open: function (open) {
        if (open && openPopup && openPopup !== popup) closeOpenPopup();
        /* A list and a control waiting for a key are both surfaces the player
         * opened, and only one of them can be what the next click or press is
         * for. Opening either puts the other away. */
        if (open) stopListeningForAKey();
        panel.hidden = !open;
        button.setAttribute("aria-expanded", String(!!open));
        if (open) {
          place();
          openPopup = popup;
        } else if (openPopup === popup) {
          openPopup = null;
        }
      }
    };
    button.addEventListener("click", function (event) {
      if (event && event.stopPropagation) event.stopPropagation();
      popup.open(!popup.isOpen());
    });
    /* A click inside the surface is the choice being made, not a reason to
     * close the thing it is being made in. */
    panel.addEventListener("click", function (event) {
      if (event && event.stopPropagation) event.stopPropagation();
    });
    return popup;
  }

  /** A list of values, drawn in the page. */
  function drawnMenu(spec) {
    var popup = drawnPopup(spec.name);
    popup.panel.className = "picker-panel picker-menu";
    popup.panel.setAttribute("role", "listbox");

    var menu = {
      root: popup.root,
      button: popup.button,
      options: [],
      value: undefined
    };

    function optionNode(option) {
      var node = element("button", "picker-option", option.label);
      node.type = "button";
      node.setAttribute("role", "option");
      node.setAttribute("data-value", String(option.value));
      node.addEventListener("click", function () {
        popup.open(false);
        menu.setValue(option.value);
        spec.onChoose(option.value);
      });
      return node;
    }

    menu.setValue = function (value) {
      menu.value = value;
      var label = spec.emptyLabel === undefined ? "" : spec.emptyLabel;
      for (var i = 0; i < menu.options.length; i += 1) {
        var chosen = menu.options[i].value === value;
        if (chosen) label = menu.options[i].label;
        popup.panel.children[i].setAttribute("aria-selected", String(chosen));
      }
      popup.button.textContent = label;
    };

    /* Rebuilding throws away the surface the player may have open, so callers
     * do it only when the values themselves changed. */
    menu.setOptions = function (options) {
      menu.options = options;
      popup.panel.textContent = "";
      for (var i = 0; i < options.length; i += 1) {
        popup.panel.appendChild(optionNode(options[i]));
      }
      menu.setValue(menu.value);
    };

    return menu;
  }

  /* What one Map Entity says instead of the global, and the one word for
   * saying nothing instead.
   *
   * The value shown by a control on the entity pane is always the one actually
   * in force -- the entity's own, or the global it follows -- because a control
   * showing nothing would claim the entity has no answer when it plainly does.
   *
   * `Follow Settings` used to be the last entry in each of these lists, which
   * made "stop having an opinion" look like one of the values a setting can
   * hold. It is `Restore global` beside the field now: one control, on every
   * field that can hold an override, doing one thing. */
  var INHERIT = "inherit";

  function overrideMenu(spec) {
    return drawnMenu({
      name: spec.name,
      onChoose: function (value) {
        var change = {};
        change[spec.field] = value;
        send("setEntityMarks", change);
      }
    });
  }

  /* Swatches enough to pick from at a glance, and a hex box for everything
   * else. Drawn here for the same reason the lists are: an `<input
   * type="color">` opens a native dialog that has nowhere to appear over a
   * page rendered offscreen into a game window. */
  var SWATCHES = [
    "#ffffff", "#f8fafc", "#94a3b8", "#020617",
    "#38bdf8", "#2563eb", "#22c55e", "#84cc16",
    "#fbbf24", "#f97316", "#ef4444", "#a855f7"
  ];

  function isColor(value) {
    return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value);
  }

  /** A colour, chosen the same way a value from a list is. */
  function colorPicker(spec) {
    var popup = drawnPopup(spec.name);
    popup.panel.className = "picker-panel picker-colors";
    var swatch = element("span", "swatch");
    var shown = element("span", "picker-color-value");
    popup.button.appendChild(swatch);
    popup.button.appendChild(shown);

    var picker = {root: popup.root, button: popup.button, value: false};

    function choose(value) {
      if (!isColor(value)) {
        /* Refused rather than guessed at: half a hex code is not a colour, and
         * a control that quietly picks black on a typo is worse than one that
         * says no. */
        hex.setAttribute("aria-invalid", "true");
        return;
      }
      hex.setAttribute("aria-invalid", "false");
      picker.setValue(value);
      popup.open(false);
      spec.onChoose(picker.value);
    }

    function swatchNode(value) {
      var node = element("button", "swatch-option");
      node.type = "button";
      node.setAttribute("data-value", value);
      node.style.background = value;
      node.addEventListener("click", function () {
        choose(value);
      });
      return node;
    }

    var grid = element("div", "swatch-grid");
    for (var i = 0; i < SWATCHES.length; i += 1) {
      grid.appendChild(swatchNode(SWATCHES[i]));
    }
    popup.panel.appendChild(grid);

    var hexLabel = element("label", "picker-hex");
    hexLabel.appendChild(element("span", null, t("settings.colorHex")));
    var hex = document.createElement("input");
    hex.type = "text";
    hex.setAttribute("data-color-hex", spec.name);
    hex.addEventListener("change", function () {
      choose(hex.value);
    });
    hexLabel.appendChild(hex);
    popup.panel.appendChild(hexLabel);

    picker.setValue = function (value) {
      picker.value = isColor(value) ? String(value).toLowerCase() : false;
      swatch.style.background = picker.value || "transparent";
      shown.textContent = picker.value || t("common.empty");
      if (hex.value !== picker.value) hex.value = picker.value || "";
      popup.button.setAttribute("data-value", picker.value || "");
    };
    picker.setValue(spec.value);
    return picker;
  }

  /* --- a key is answered by pressing it ---------------------------------- */

  /* Which control is waiting for a key, if any. One at a time, the way one
   * drawn list is open at a time: two controls both listening would both take
   * the same press. */
  var listeningCapture = null;

  /* How a press becomes the word MTA stores.
   *
   * Read off `event.code` -- the physical key -- rather than off `event.key`,
   * which is the character the layout produced. A binding is physical: MTA
   * binds a virtual key, so the key marked A binds `a` on a Russian layout too,
   * where `event.key` would hand over `ф`.
   *
   * The letters, digits, function keys and the numeric pad are a rule and are
   * worked out below; what is left is a list, and it is here. Which names are
   * *allowed* is decided nowhere on this page: the schema's own lists arrive
   * with the state and every name this produces is checked against them, so a
   * key this can spell and MTA cannot name is still refused rather than stored.
   */
  var CODE_NAMES = {
    Space: "space", Enter: "enter", Tab: "tab", Backspace: "backspace",
    CapsLock: "capslock",
    ShiftLeft: "lshift", ShiftRight: "rshift",
    ControlLeft: "lctrl", ControlRight: "rctrl",
    AltLeft: "lalt", AltRight: "ralt",
    Insert: "insert", Delete: "delete", Home: "home", End: "end",
    PageUp: "pgup", PageDown: "pgdn",
    ArrowLeft: "arrow_l", ArrowUp: "arrow_u",
    ArrowRight: "arrow_r", ArrowDown: "arrow_d",
    NumpadEnter: "num_enter", Escape: "escape"
  };

  /** What MTA calls the key that was pressed, or "" for one it cannot name. */
  function keyNameOf(event) {
    var code = (event && event.code) || "";
    if (/^Key[A-Z]$/.test(code)) return code.charAt(3).toLowerCase();
    if (/^Digit[0-9]$/.test(code)) return code.charAt(5);
    if (/^Numpad[0-9]$/.test(code)) return "num_" + code.charAt(6);
    if (/^F[0-9]{1,2}$/.test(code)) return code;
    if (Object.prototype.hasOwnProperty.call(CODE_NAMES, code)) {
      return CODE_NAMES[code];
    }
    return "";
  }

  /** A key, taken by pressing it rather than found in a list.
   *
   * The list it replaces held every key MTA can name, so a player who wanted
   * `E` scrolled a hundred entries looking for it -- and the list was the wrong
   * shape for the question anyway. The way a person says which key is to press
   * it.
   *
   * Both refusals are read from lists the schema sent: a name MTA cannot bind,
   * and a name ANKIGTA already answers to. Lua validates again on the way in and
   * the server validates an override -- this is the fast half, so the reason
   * arrives on the press rather than a round trip later. */
  function keyCapture(spec) {
    var root = element("div", "key-capture");
    var button = element("button", "key-button");
    button.type = "button";
    button.setAttribute("data-key-capture", spec.name);
    button.setAttribute("aria-pressed", "false");
    /* Its own, rather than the row's: a state push happens whenever anything at
     * all changes and rewrites the row's reason from what Lua last said, which
     * would take this one off screen a moment after the press earned it. */
    var refusal = element("p", "field-error", "");
    refusal.setAttribute("role", "alert");
    refusal.setAttribute("data-key-refused", spec.name);
    refusal.hidden = true;
    root.appendChild(button);
    root.appendChild(refusal);

    var capture = {
      root: root,
      button: button,
      value: undefined,
      listening: false,
      /* Every key MTA can name, and the part of that still free. Absent until
       * the first state carries them, which is why a press before then is
       * refused rather than sent. */
      bindable: [],
      offered: []
    };

    function draw() {
      button.textContent = capture.listening
        ? t("f7.pressAKey")
        : (capture.value === undefined || capture.value === false
            ? t("common.empty")
            : String(capture.value));
      button.setAttribute("aria-pressed", String(capture.listening));
      button.setAttribute(
        "data-value",
        capture.value === undefined || capture.value === false
          ? ""
          : String(capture.value)
      );
    }

    function say(reason) {
      refusal.textContent = reason ? t(reason) : "";
      refusal.hidden = !reason;
    }

    /* Left listening after a refusal: the answer to "not that one" is another
     * key, and a control that closed itself would have to be found and opened
     * again to give it. */
    capture.listen = function (on) {
      if (on && listeningCapture && listeningCapture !== capture) {
        listeningCapture.listen(false);
      }
      if (on) closeOpenPopup();
      capture.listening = on === true;
      if (capture.listening) {
        say(false);
        listeningCapture = capture;
      } else if (listeningCapture === capture) {
        listeningCapture = null;
      }
      draw();
    };

    capture.setValue = function (value) {
      capture.value = value;
      draw();
    };

    capture.setKeys = function (offered, bindable) {
      capture.offered = offered || [];
      capture.bindable = bindable || [];
    };

    capture.take = function (event) {
      var name = keyNameOf(event);
      if (!name || capture.bindable.indexOf(name) === -1) {
        say("settings.error.not_a_key");
        return;
      }
      if (capture.offered.indexOf(name) === -1) {
        say("settings.error.key_in_use");
        return;
      }
      capture.listen(false);
      capture.setValue(name);
      spec.onChoose(name);
    };

    button.addEventListener("click", function (event) {
      if (event && event.stopPropagation) event.stopPropagation();
      capture.listen(!capture.listening);
    });
    draw();
    return capture;
  }

  /* --- the Map Entity list ---------------------------------------------- */

  /* The rows as they are on screen, in the order they are drawn. Kept so the
   * arrow keys can step from one to the next without asking Lua which row is
   * where. */
  var rowNodes = [];

  /* Whether selecting a row also points the camera at it. The player's, and
   * pushed with the state like everything else here. */
  var focusOnSelect = true;

  function renderRows(entities) {
    var host = document.getElementById("rows");
    host.textContent = "";
    rowNodes = [];
    if (!entities || entities.length === 0) {
      host.appendChild(element("p", "empty", t("panel.entities.empty")));
      return;
    }
    for (var i = 0; i < entities.length; i += 1) {
      var entry = entities[i];
      var row = element("button", "row");
      row.type = "button";
      row.setAttribute("role", "listitem");

      var primary = element("div", "primary-cell");
      primary.appendChild(
        element("strong", null, entry.name)
      );
      primary.appendChild(
        element("span", "sub", entry.description || "")
      );
      /* A cosmetic name replaces the editor's, which is the point — but the
       * editor's is the only thing tying this row to what the player sees in
       * the Map Editor, so the row keeps saying it. */
      if (entry.originalName) {
        primary.appendChild(
          element(
            "span",
            "sub original-name",
            t("f7.entity.originalName").replace("%s", entry.originalName)
          )
        );
      }
      row.appendChild(primary);

      row.appendChild(element("span", "type", entry.type));

      var state = element("span", "state");
      var tone = TONES[entry.linkState];
      if (tone) state.setAttribute("data-tone", tone);
      state.appendChild(element("span", "marker"));
      state.appendChild(
        element("span", "label", t("f7.linkState." + entry.linkState))
      );
      row.appendChild(state);

      if (entry.mapId === selected.mapId && entry.entityId === selected.entityId) {
        row.className = "row selected";
      }
      bindSelect(row, entry);
      rowNodes.push({entry: entry, node: row});
      host.appendChild(row);
    }
  }

  /* Selecting a row and looking at it are the same intention almost every
   * time: the reason to select a row is to decide something about the thing it
   * names, and that decision needs the thing on screen. Because "almost every
   * time" is not "every time", `focusOnSelect` turns the camera half off and
   * leaves the click selecting. */
  function selectRow(entry) {
    send("select", {mapId: entry.mapId, entityId: entry.entityId});
    if (focusOnSelect) {
      send("focusEntity", {mapId: entry.mapId, entityId: entry.entityId});
    }
  }

  /* A row identifies itself by the pair the server knows it by, never by its
   * index: the list re-sorts whenever the snapshot changes, and an index would
   * quietly start pointing at a different Map Entity. */
  function bindSelect(row, entry) {
    row.addEventListener("click", function () {
      selectRow(entry);
    });
  }

  function selectedRowIndex() {
    for (var i = 0; i < rowNodes.length; i += 1) {
      if (rowNodes[i].entry.mapId === selected.mapId
          && rowNodes[i].entry.entityId === selected.entityId) {
        return i;
      }
    }
    return -1;
  }

  /* Up and down move the selection, and the row moved onto is brought back
   * into sight. A list reachable only by pointing gets slower the longer it
   * is, and this one is meant to grow. */
  function moveSelection(step) {
    if (rowNodes.length === 0) return;
    var index = selectedRowIndex();
    var next = index === -1
      ? (step > 0 ? 0 : rowNodes.length - 1)
      : Math.min(rowNodes.length - 1, Math.max(0, index + step));
    var target = rowNodes[next];
    if (target.node.scrollIntoView) {
      target.node.scrollIntoView({block: "nearest"});
    }
    selectRow(target.entry);
  }

  /* --- the Card Picker --------------------------------------------------- */

  /* A deck is chosen, not typed. The chosen value lives here rather than on a
   * control, because the control is a drawn list now. */
  var chosenDeck = "";
  var lastDeckList = null;

  var deckMenu = drawnMenu({
    name: "deck",
    emptyLabel: "",
    onChoose: function (name) {
      chosenDeck = name;
      submitSearch();
    }
  });
  document.getElementById("deck-picker").appendChild(deckMenu.root);

  function renderDecks(picker) {
    var decks = (picker && picker.decks) || [];
    /* The words matter as well as the names: the first state carries both the
     * deck list and the string table, and a signature over the names alone
     * would leave "Every deck" reading as its own key forever. */
    var signature = JSON.stringify([decks, t("cardPicker.anyDeck")]);
    /* Rebuilt only when the list actually changed, so an open menu is not
     * yanked shut by an unrelated redraw. */
    if (signature !== lastDeckList) {
      lastDeckList = signature;
      var options = [{value: "", label: t("cardPicker.anyDeck")}];
      for (var i = 0; i < decks.length; i += 1) {
        options.push({value: decks[i], label: decks[i]});
      }
      deckMenu.setOptions(options);
    }
    /* What the server says the filter is beats what was left in the control:
     * they disagree only when somebody else changed it. */
    chooseDeck((picker && picker.deckFilter) || chosenDeck || "");
  }

  function chooseDeck(name) {
    chosenDeck = name;
    deckMenu.setValue(name);
  }

  /* Cards or notes is one of two, and it is a drawn list for the same reason
   * the deck is: a switch and a dropdown side by side are two controls the
   * player has to learn separately. */
  var chosenScope = "cards";
  var scopeLabels = null;

  var scopeMenu = drawnMenu({
    name: "scope",
    onChoose: function (scope) {
      chooseScope(scope);
      submitSearch();
    }
  });
  document.getElementById("scope-picker").appendChild(scopeMenu.root);

  function refreshScopeOptions() {
    var labels = JSON.stringify([
      t("cardPicker.scope.cards"),
      t("cardPicker.scope.notes")
    ]);
    if (labels === scopeLabels) return;
    scopeLabels = labels;
    scopeMenu.setOptions([
      {value: "cards", label: t("cardPicker.scope.cards")},
      {value: "notes", label: t("cardPicker.scope.notes")}
    ]);
  }

  function chooseScope(scope) {
    chosenScope = scope === "notes" ? "notes" : "cards";
    scopeMenu.setValue(chosenScope);
  }

  /* The expression the rows are an answer to, and whether a row is a card or
   * a note. Both follow the answer rather than the control, and both only when
   * the answer itself changed: a state push happens whenever anything at all
   * changes, and putting the switch back — or wiping a half-typed expression —
   * on an unrelated redraw is how a choice made a moment ago disappears. */
  var lastQuery = null;
  var lastScope = null;

  function renderSearch(picker) {
    var query = (picker && picker.query) || "";
    if (query !== lastQuery) {
      lastQuery = query;
      document.getElementById("search-query").value = query;
    }
    var scope = (picker && picker.scope) || "cards";
    if (scope !== lastScope) {
      lastScope = scope;
      chooseScope(scope);
    }
  }

  function renderCards(picker) {
    selectedCardLabel = "";
    refreshScopeOptions();
    renderSearch(picker);
    renderDecks(picker);
    var host = document.getElementById("cards");
    host.textContent = "";
    var cards = (picker && picker.cards) || [];
    if (cards.length === 0) {
      host.appendChild(element("p", "empty", t("cardPicker.column.card")));
      return;
    }
    for (var i = 0; i < cards.length; i += 1) {
      var card = cards[i];
      var row = element("button", "row card");
      row.type = "button";
      row.setAttribute("role", "listitem");

      var primary = element("div", "primary-cell");
      primary.appendChild(
        element("strong", null, card.sortField || card.cardId)
      );
      primary.appendChild(element("span", "sub", card.deck));
      if (card.foreignMapName) {
        primary.appendChild(
          element(
            "span",
            "sub foreign-map",
            card.foreignMapName
          )
        );
      }
      row.appendChild(primary);
      row.appendChild(element("span", "type", card.state));

      if (card.cardId === selected.cardId) {
        row.className = "row card selected";
        selectedCardLabel = (card.sortField || card.cardId) + " — " + card.deck;
      }
      bindSelectCard(row, card);
      host.appendChild(row);
    }
  }

  function bindSelectCard(row, card) {
    row.addEventListener("click", function () {
      send("selectCard", {
        cardId: card.cardId,
        collectionUuid: card.collectionUuid
      });
    });
  }

  function renderConnection(connection) {
    var status = document.getElementById("status");
    status.setAttribute("data-state", connection.state);
    var key = "connection.status." + (connection.state === "connected"
      ? "connected"
      : connection.state === "connecting"
        ? "connecting"
        : (connection.category || "disconnected"));
    document.getElementById("status-detail").textContent = t(key);

    var fields = JSON.stringify([
      connection.port || false,
      connection.tokenConfigured === true,
      connection.tokenDisabled === true,
      connection.settingsVersion || 0
    ]);
    if (fields !== lastConnectionFields) {
      lastConnectionFields = fields;
      document.getElementById("port").value = connection.port || "";
      var token = document.getElementById("token");
      token.value = connection.tokenConfigured === true &&
        connection.tokenDisabled !== true ? HIDDEN_TOKEN : "";
      token.setAttribute("data-replacement", "false");
    }

    renderConnectionError("port", connection.portError);
    renderConnectionError("token", connection.tokenError);

    var notice = document.getElementById("notice");
    var warning = connection.warningCategory || connection.sessionCategory;
    if (warning) {
      notice.textContent = t("connection.status." + warning);
      notice.className = "notice warning";
      notice.hidden = false;
    } else {
      notice.hidden = true;
    }
  }

  function renderStudy(study) {
    var detail = document.getElementById("study-detail");
    if (study.active) {
      detail.textContent = format(t("study.session"), study.progress, study.total);
    } else if (study.pausedReason) {
      detail.textContent = t("study.paused");
    } else {
      detail.textContent = "";
    }
    document.getElementById("start-study").hidden = !study.resumable;
  }

  /* Lua's string.format lives on the other side, so the two placeholders the
   * session line uses are filled here rather than shipped pre-rendered. */
  function format(template, first, second) {
    var next = [first, second];
    var index = 0;
    return String(template).replace(/%d/g, function () {
      var value = next[index];
      index += 1;
      return value === undefined ? "" : String(value);
    });
  }

  var LINK_CHANGEABLE = {"Active Spatial Link": true, "Card missing": true};

  function findSelected(entities) {
    for (var i = 0; i < (entities || []).length; i += 1) {
      if (entities[i].mapId === selected.mapId
          && entities[i].entityId === selected.entityId) {
        return entities[i];
      }
    }
    return null;
  }

  /* --- the pane that edits the selected Map Entity ----------------------- */

  /* What Lua last reported about the selected row, so a redraw reporting the
   * same thing does not wipe what is half-typed into these boxes. */
  var reportedEntity = null;

  /* The corona's colour, drawn in the page like every other choice here. Built
   * once and kept: rebuilding it on each state push would take away the
   * surface the player has open, which is what "a menu closes while I am
   * choosing from it" was. */
  var coronaColorPicker = colorPicker({
    /* Named apart from the Settings row for the same value: both are on the
     * page at once, and one name for two controls is one control a test -- or
     * a click -- can reach by accident. */
    name: "entityCoronaColor",
    value: false,
    onChoose: function (value) {
      send("setEntityMarks", {coronaColor: value});
    }
  });
  document
    .getElementById("entity-corona-color")
    .appendChild(coronaColorPicker.root);

  /* The two lists in the entity pane, built once for the same reason the colour
   * picker is: rebuilding one on each state push takes away the surface the
   * player has open. Their options are fixed -- two modes and two states -- so
   * they are filled from the first state that carries the words for them and
   * left alone after. */
  var activationTypeMenu = overrideMenu({
    name: "entityActivationType",
    field: "activationType"
  });
  document
    .getElementById("entity-activation-type")
    .appendChild(activationTypeMenu.root);

  /* The key this one entity opens on, pressed rather than chosen. The same
   * control the Settings row uses: one way of answering "which key", wherever
   * the question is asked. */
  var activationKeyCapture = keyCapture({
    name: "entityActivationKey",
    onChoose: function (name) {
      send("setEntityMarks", {activationKey: name});
    }
  });
  document
    .getElementById("entity-activation-key")
    .appendChild(activationKeyCapture.root);

  var showCoronaMenu = overrideMenu({
    name: "entityShowCorona",
    field: "showCorona"
  });
  document
    .getElementById("entity-show-corona")
    .appendChild(showCoronaMenu.root);

  /* The Text Label's colour on this one entity. The same picker the corona
   * uses, for the same reason it exists at all; the way back to the global is
   * the `Restore global` button beside it, like every other field here. */
  var textLabelColorPicker = colorPicker({
    name: "entityTextLabelColor",
    value: false,
    onChoose: function (value) {
      send("setEntityMarks", {textLabelColor: value});
    }
  });
  document
    .getElementById("entity-text-label-color")
    .appendChild(textLabelColorPicker.root);

  /* One way back to the global, on every field that can hold an override.
   *
   * Which fields those are is the markup's answer: the pane is written out
   * field by field, so the buttons are read back the same way rather than
   * listed here a second time and kept in step by hand. It is the single-entity
   * half of `Apply to all` -- that puts every Map Entity back on one setting,
   * this puts one Map Entity back on one setting -- and both say it with the
   * one word the store keeps for "nothing of its own". */
  var restoreControls = [];
  (function () {
    var nodes = document.querySelectorAll("[data-restore-global]");
    for (var i = 0; i < nodes.length; i += 1) {
      restoreControls.push(bindRestoreGlobal(nodes[i]));
    }
  })();

  function bindRestoreGlobal(node) {
    var field = node.getAttribute("data-restore-global");
    node.addEventListener("click", function () {
      var change = {};
      change[field] = INHERIT;
      send("setEntityMarks", change);
    });
    return {node: node, field: field};
  }

  /* `Draw radius` is on this pane and is not the entity's: it is this player's
   * own way of looking, and it draws the selected row's Activation Zone while
   * F7 is open. So it is sent as a setting rather than as an override, and it
   * has two states where every other control here has three -- an entity has
   * nothing to say about it, so there is no global for it to follow.
   *
   * Not disabled with the rest of the pane when nothing is selected, for the
   * same reason: the answer is the player's and outlives any one row. */
  var drawRadius = false;
  var drawRadiusToggle = document.getElementById("entity-draw-radius");
  drawRadiusToggle.addEventListener("click", function () {
    send("setSetting", {key: "drawRadius", value: !drawRadius});
  });

  function renderDrawRadius(value) {
    drawRadius = value === true;
    drawRadiusToggle.textContent = t("settings.value." + String(drawRadius));
    drawRadiusToggle.setAttribute("aria-pressed", String(drawRadius));
  }

  /* What each list was last filled with, so an unrelated redraw does not
   * rebuild it -- which would shut it while it was open. */
  var entityOptionShape = null;

  function fillEntityChoices(settings) {
    var rows = (settings && settings.rows) || [];
    for (var i = 0; i < rows.length; i += 1) {
      if (rows[i].key === "activationKey") {
        /* The two lists the capture refuses from, taken from the same row the
         * Settings screen draws its own capture out of: which keys ANKIGTA can
         * bind and which are still free is the schema's answer, and asking for
         * it twice is two answers that can disagree. */
        activationKeyCapture.setKeys(
          rows[i].options, rows[i].bindableKeys
        );
      }
    }
    /* Every word that ends up on one of the two lists, so a state that carries
     * the string table for the first time -- or a changed one -- fills them,
     * and one that changes nothing leaves an open list open. */
    var shape = JSON.stringify([
      t("settings.value.automatic"),
      t("settings.value.key"),
      t("settings.value.true"),
      t("settings.value.false")
    ]);
    if (shape === entityOptionShape) return;
    entityOptionShape = shape;
    activationTypeMenu.setOptions([
      {value: "automatic", label: t("settings.value.automatic")},
      {value: "key", label: t("settings.value.key")}
    ]);
    showCoronaMenu.setOptions([
      {value: true, label: t("settings.value.true")},
      {value: false, label: t("settings.value.false")}
    ]);
  }

  /* On screen whether or not a row is selected. It used to appear with the
   * selection and vanish with it, so the panel jumped every time the player
   * moved down the list; the fields are disabled rather than removed, which
   * keeps their place, and the pane says why it is empty. */
  /* What the object really shows, in the words of the row rather than in the
   * words of the setting. A label falling back to another field is the case
   * this exists for: the box says `Front` and the object says something else,
   * and without this the row reads as correct. */
  /* Which link states are the row saying "there is no card here" rather than
   * something more specific. Every other state — card missing, entity missing,
   * a collision, a pending map save — is already named in the row's own state
   * cell, and a second line under it claiming nothing is linked would be a
   * claim that is simply false. */
  var UNLINKED_STATES = {"Unlinked": true, "Not adopted": true};

  /* One placeholder filled with a value, never a pattern.
   *
   * `String.replace` reads `$&`, `` $` `` and `$'` out of the *replacement*,
   * and the values going in here are a note's own words and a note type's own
   * field names. A card whose front is `$&` would have been drawn as the
   * template around it. A function replacement is taken literally. */
  function fill(template, value) {
    return String(template).replace("%s", function () {
      return String(value === undefined || value === null ? "" : value);
    });
  }

  function textLabelState(entity) {
    var label = entity.textLabel;
    if (!label) {
      return UNLINKED_STATES[entity.linkState]
        ? t("f7.textLabel.notLinked")
        : "";
    }
    var shown = (label.lines || []).join(" ");
    if (label.reason === "not_cached") return t("f7.textLabel.notCached");
    if (label.reason === "no_words") return t("f7.textLabel.noWords");
    /* Each key written out rather than chosen into a variable: a string is
     * only reachable if a surface asks for it by name, and that is checked by
     * reading this file. */
    if (label.reason === "field_missing") {
      return fill(
        fill(fill(t("f7.textLabel.fallbackMissing"), label.requestedField),
             label.fieldName),
        shown
      );
    }
    if (label.reason === "field_wordless") {
      return fill(
        fill(fill(t("f7.textLabel.fallbackWordless"), label.requestedField),
             label.fieldName),
        shown
      );
    }
    return fill(fill(t("f7.textLabel.showing"), label.fieldName), shown);
  }

  function renderEntityPane(entity) {
    var empty = document.getElementById("entity-empty");
    var name = document.getElementById("entity-name");
    var radius = document.getElementById("entity-radius");
    var mark = document.getElementById("entity-radius-inherited");
    var opacity = document.getElementById("entity-corona-opacity");
    var colorMark = document.getElementById("entity-corona-color-inherited");
    var opacityMark = document.getElementById("entity-corona-opacity-inherited");
    var coronaMark = document.getElementById("entity-show-corona-inherited");
    var typeMark = document.getElementById("entity-activation-type-inherited");
    var keyMark = document.getElementById("entity-activation-key-inherited");
    var labelField = document.getElementById("entity-text-label-field");
    var labelSize = document.getElementById("entity-text-label-size");
    var labelFieldMark =
      document.getElementById("entity-text-label-field-inherited");
    var labelColorMark =
      document.getElementById("entity-text-label-color-inherited");
    var labelSizeMark =
      document.getElementById("entity-text-label-size-inherited");
    var labelState = document.getElementById("entity-text-label-state");

    /* What these say comes from `applyLocale`, like every other fixed word on
     * the page; what this decides is which of them are on screen and whether
     * the fields can be typed into. */
    empty.hidden = !!entity;
    name.disabled = !entity;
    radius.disabled = !entity;
    opacity.disabled = !entity;
    coronaColorPicker.button.disabled = !entity;
    showCoronaMenu.button.disabled = !entity;
    activationTypeMenu.button.disabled = !entity;
    activationKeyCapture.button.disabled = !entity;
    labelField.disabled = !entity;
    labelSize.disabled = !entity;
    textLabelColorPicker.button.disabled = !entity;
    /* Nothing to restore where the field is already following the global, so
     * the button goes quiet rather than offering a change that changes
     * nothing -- and it keeps its place, the way every field here does. */
    for (var i = 0; i < restoreControls.length; i += 1) {
      restoreControls[i].node.disabled = !entity
        || entity[restoreControls[i].field + "Inherited"] === true;
    }

    if (!entity) {
      reportedEntity = null;
      name.value = "";
      radius.value = "";
      radius.setAttribute("data-inherited", "false");
      mark.hidden = true;
      opacity.value = "";
      opacity.setAttribute("data-inherited", "false");
      opacityMark.hidden = true;
      coronaColorPicker.setValue(false);
      colorMark.hidden = true;
      showCoronaMenu.setValue(undefined);
      activationTypeMenu.setValue(undefined);
      /* Stops waiting with the selection it was waiting for: a control still
       * listening for a key with no row under it would store the next press
       * against whatever is selected by then. */
      activationKeyCapture.listen(false);
      activationKeyCapture.setValue(undefined);
      coronaMark.hidden = true;
      typeMark.hidden = true;
      keyMark.hidden = true;
      labelField.value = "";
      labelField.setAttribute("data-inherited", "false");
      labelSize.value = "";
      labelSize.setAttribute("data-inherited", "false");
      textLabelColorPicker.setValue(false);
      labelFieldMark.hidden = true;
      labelColorMark.hidden = true;
      labelSizeMark.hidden = true;
      labelState.textContent = "";
      return;
    }

    var reported = JSON.stringify([
      entity.mapId,
      entity.entityId,
      entity.givenName || "",
      entity.radius,
      entity.radiusInherited === true,
      entity.coronaOpacity,
      entity.coronaOpacityInherited === true,
      entity.coronaColor,
      entity.showCorona === true,
      entity.activationType,
      entity.activationKey,
      entity.textLabelField,
      entity.textLabelColor,
      entity.textLabelSize
    ]);
    if (reported !== reportedEntity) {
      reportedEntity = reported;
      /* The name the player typed, never the editor's standing in for it: a
       * box pre-filled with "ped (1)" is a box that will store "ped (1)" as
       * somebody's cosmetic name the first time anybody touches it. */
      name.value = entity.givenName || "";
      /* The value actually in force, whether it is this entity's own or the
       * global it follows. An empty box was meant to read as "whatever
       * Settings says" and reads as no value at all. */
      radius.value = entity.radius;
      opacity.value = entity.coronaOpacity;
      /* The colour the corona will really be, which for an entity that has
       * chosen none is the one Settings holds. A swatch showing nothing would
       * say the corona has no colour, and it has one.
       *
       * Inside the guard with the other two, because the picker owns a hex box
       * somebody may be halfway through typing into: a state push happens
       * whenever anything at all changes -- a car streaming in will do it --
       * and one that reports the same colour must not take the half-typed code
       * out from under them. */
      coronaColorPicker.setValue(entity.coronaColor);
      /* The value in force, whichever side of the override it came from. The
       * lists carry no half-typed state, but they are set inside the guard
       * with the rest so that a push reporting the same entity leaves an open
       * one open. */
      showCoronaMenu.setValue(entity.showCorona === true);
      activationTypeMenu.setValue(entity.activationType);
      activationKeyCapture.setValue(entity.activationKey);
      /* The three the Text Label is drawn from, each showing the value in
       * force — the entity's own where it has one, the global where it has
       * not — and inside the same guard for the same reason: a push reporting
       * the same entity must not take a half-typed field name away. */
      labelField.value = entity.textLabelField || "";
      labelSize.value = entity.textLabelSize;
      textLabelColorPicker.setValue(entity.textLabelColor);
    }
    /* Outside it: what the object says changes when the note does, and that
     * arrives without any of the three settings above moving. */
    labelState.textContent = textLabelState(entity);
    /* Shown, and said: a number that came from Settings looks exactly like a
     * number somebody chose. */
    radius.setAttribute("data-inherited", String(entity.radiusInherited === true));
    mark.hidden = entity.radiusInherited !== true;
    colorMark.hidden = entity.coronaColorInherited !== true;
    opacity.setAttribute(
      "data-inherited", String(entity.coronaOpacityInherited === true)
    );
    opacityMark.hidden = entity.coronaOpacityInherited !== true;
    coronaMark.hidden = entity.showCoronaInherited !== true;
    typeMark.hidden = entity.activationTypeInherited !== true;
    keyMark.hidden = entity.activationKeyInherited !== true;
    labelField.setAttribute(
      "data-inherited", String(entity.textLabelFieldInherited === true)
    );
    labelFieldMark.hidden = entity.textLabelFieldInherited !== true;
    labelColorMark.hidden = entity.textLabelColorInherited !== true;
    labelSize.setAttribute(
      "data-inherited", String(entity.textLabelSizeInherited === true)
    );
    labelSizeMark.hidden = entity.textLabelSizeInherited !== true;
  }

  /* --- the card editor --------------------------------------------------- */

  /* The note behind the selected card: what it says, and what the player has
   * typed into it. Rebuilt only when a different note arrives, so typing is
   * not thrown away by an unrelated redraw -- a state push happens whenever
   * anything at all changes, and most of it is not this. */
  var shownNote = null;
  /* Whether the editor is slid out. The player's, not the state's: a card
   * being selected is not by itself a request to edit it, and a panel that
   * opens a form every time a row is clicked has decided that for them. */
  var inspectorOpen = false;
  /* The boxes on screen and the note as Anki last reported it. Save is offered
   * against the difference between the two: a Save that is always available
   * says nothing about whether there is anything to save. */
  var noteBoxes = [];
  var noteBaseline = null;

  function noteIsEdited() {
    if (!noteBaseline || noteBoxes.length !== noteBaseline.fields.length) {
      return false;
    }
    for (var i = 0; i < noteBoxes.length; i += 1) {
      if (noteBoxes[i].value !== noteBaseline.fields[i]) return true;
    }
    return document.getElementById("inspector-tags").value !== noteBaseline.tags;
  }

  function refreshSaveState() {
    document.getElementById("save-note").disabled = !noteIsEdited();
  }

  /* Whether the Settings column is out. Lua's, not the page's: the panel's own
   * width follows it, and a page that decided this would be deciding how big
   * its own window is. */
  var settingsOpen = false;

  /* Which columns the workspace is showing.
   *
   * Each of the two that come and go — Settings on the left, the card editor on
   * the right — exists only while it is open, so the two lists have the whole
   * panel the rest of the time. Neither takes its room from the others: Lua
   * widens the window for whichever are out, and this only says which those
   * are. */
  function renderWorkspaceShape() {
    var shape = "workspace";
    if (settingsOpen) shape += " with-settings";
    if (inspectorOpen && selected.cardId) shape += " editing";
    document.getElementById("workspace").className = shape;
    document.getElementById("settings-column").hidden = !settingsOpen;
  }

  function renderInspectorToggle() {
    var button = document.getElementById("toggle-inspector");
    button.disabled = !selected.cardId;
    button.setAttribute("aria-expanded", String(inspectorOpen));
    button.textContent = t(inspectorOpen ? "inspector.close" : "inspector.open");
    renderWorkspaceShape();
  }

  function renderInspector(state) {
    var box = document.getElementById("inspector");
    var error = document.getElementById("inspector-error");
    var status = document.getElementById("inspector-state");

    renderInspectorToggle();
    box.hidden = !selected.cardId || !inspectorOpen;
    if (!selected.cardId) {
      shownNote = null;
      noteBaseline = null;
      noteBoxes = [];
      refreshSaveState();
      return;
    }

    if (state.noteError) {
      error.textContent = t("inspector.unreadable").replace("%s", state.noteError);
      status.textContent = "";
      document.getElementById("inspector-fields").textContent = "";
      shownNote = null;
      noteBaseline = null;
      noteBoxes = [];
      refreshSaveState();
      return;
    }
    error.textContent = "";

    var note = state.note;
    if (!note) {
      status.textContent = t("inspector.loading");
      noteBaseline = null;
      noteBoxes = [];
      refreshSaveState();
      return;
    }
    status.textContent = "";

    var fields = note.fields || [];
    /* What Anki holds, refreshed on every state: a save answers with the note
     * read back, and the button has to go quiet again once it has. */
    noteBaseline = {
      fields: fields.map(function (f) { return f.value; }),
      tags: (note.tags || []).join(" ")
    };

    var signature = JSON.stringify([
      note.noteId,
      fields.map(function (f) { return f.name; })
    ]);
    if (signature !== shownNote) {
      shownNote = signature;
      var host = document.getElementById("inspector-fields");
      host.textContent = "";
      noteBoxes = [];
      for (var i = 0; i < fields.length; i += 1) {
        var wrap = element("label", "inspector-field");
        wrap.appendChild(element("span", null, fields[i].name));
        var input = document.createElement("textarea");
        input.rows = 2;
        input.value = fields[i].value;
        input.setAttribute("data-field", fields[i].name);
        input.addEventListener("input", refreshSaveState);
        wrap.appendChild(input);
        host.appendChild(wrap);
        noteBoxes.push(input);
      }
      document.getElementById("inspector-tags").value = noteBaseline.tags;
    }
    refreshSaveState();
  }

  function renderNotice(notice) {
    var node = document.getElementById("notice");
    if (!notice) { node.hidden = true; return; }
    node.textContent = t(notice.key).replace("%s", notice.detail || "");
    node.className = "notice warning";
    node.hidden = false;
  }

  /* --- settings ---------------------------------------------------------- */

  /* One row per setting, built from what Lua sent rather than from a list kept
   * here: a setting added to the schema appears by existing.
   *
   * Rebuilt only when the *shape* changes. A state push happens whenever
   * anything at all changes, and rebuilding on each of them took an open list
   * down with the row it was in and wiped whatever was half-typed into the
   * field beside it. */
  var settingsShape = null;
  var settingsControls = {};

  function settingsSignature(rows) {
    return JSON.stringify(rows.map(function (row) {
      return [
        row.kind, row.key, row.labelKey || "", row.options || false,
        row.min, row.max, row.step, row.clearOverrides === true,
        row.noteKey || ""
      ];
    }));
  }

  function renderSettings(settings) {
    var rows = (settings && settings.rows) || [];
    var signature = settingsSignature(rows);
    if (signature !== settingsShape) {
      settingsShape = signature;
      settingsControls = {};
      var host = document.getElementById("settings-rows");
      host.textContent = "";
      for (var i = 0; i < rows.length; i += 1) {
        host.appendChild(settingRow(rows[i]));
      }
    } else {
      for (var j = 0; j < rows.length; j += 1) {
        var control = settingsControls[settingId(rows[j])];
        if (control) control.apply(rows[j]);
      }
    }
    /* After the rows, not before: the question names the setting in the words
     * its row uses, and those words are learnt while the row is drawn. */
    renderBulkDialog(settings);
  }

  /* The label of the setting the sweep is about, so the question names it in
   * the words the row above uses rather than by its key. */
  var settingLabels = {};
  /* What the confirmation is currently about. Lua's, pushed with the state --
   * the page decides nothing, including which sweep the button confirms. */
  var lastPendingClear = null;

  function renderBulkDialog(settings) {
    var pending = (settings && settings.pendingClear) || false;
    lastPendingClear = pending || null;
    document.getElementById("bulk-dialog").hidden = !pending;
    if (!pending) return;
    var label = settingLabels[pending.key] || pending.key;
    var count = pending.count || 0;
    document.getElementById("bulk-question").textContent = count === 0
      ? t("settings.applyToAll.none").replace("%s", label)
      : t("settings.applyToAll.question")
          .replace("%d", String(count))
          .replace("%s", label);
    document.getElementById("bulk-confirm").disabled = count === 0;
  }

  function settingId(row) {
    return "set-" + row.key;
  }

  /* Every setting is named by the string table. The one row that carried its
     own text was the per-map switch, which named a map -- the user's words --
     and there is no per-map row any more. Nor a heading, a note, or a class
     saying a row belongs to one map: all four were per-map machinery, inert
     since the setting they served was removed. */
  function settingLabel(row) {
    return t(row.labelKey || "settings." + row.key);
  }

  function settingClass(row) {
    return row.error ? "setting invalid" : "setting";
  }

  function settingRow(row) {
    var wrap = element("div", settingClass(row));
    wrap.setAttribute("data-setting", row.key);
    settingLabels[row.key] = settingLabel(row);
    var label = element("label", "setting-label");
    label.setAttribute("for", settingId(row));
    label.appendChild(element("span", null, settingLabel(row)));
    if (row.kind === "number" && row.min !== undefined) {
      /* The range is helper text, not a secret to be discovered by being
       * refused. */
      label.appendChild(
        element("span", "hint", row.min + " – " + row.max)
      );
    }
    wrap.appendChild(label);

    /* The reason sits under the field it belongs to, and announces itself:
     * a red border is not a message a screen reader receives. */
    var error = element("p", "field-error", "");
    error.setAttribute("role", "alert");

    var control = settingControl(row, wrap, error);
    wrap.appendChild(control.node);
    /* On the field's row, beside the global it is about, because that is the
     * thing it is about: "every Map Entity that was told otherwise goes back to
     * following this". Under the control it took a second row per setting, and
     * a screen twice as tall as it needs to be is half of why Settings could
     * not sit beside the list.
     *
     * Here for every setting a link can override, and Lua says which those are
     * -- the page keeps no list of its own, so a setting that gains an override
     * gains this control without either side being edited. */
    if (row.clearOverrides === true) {
      var sweep = element("button", "setting-apply-all", t("settings.applyToAll"));
      sweep.type = "button";
      sweep.setAttribute("data-apply-all", row.key);
      sweep.addEventListener("click", function () {
        send("clearEntityOverrides", {key: control.row.key});
      });
      wrap.appendChild(sweep);
    }
    /* A sentence under the control, where the name of the setting does not say
     * enough on its own. `Review mode` is the one that needs it: `Show text`
     * writes no repetition, and a player who assumes their reading counted has
     * been told something false by omission. Which rows have one is Lua's
     * answer, out of the string table — the page keeps no list. */
    if (row.noteKey) {
      var note = element("p", "setting-note", t(row.noteKey));
      note.setAttribute("data-setting-note", row.key);
      wrap.appendChild(note);
    }
    wrap.appendChild(error);
    settingsControls[settingId(row)] = control;
    control.apply(row);
    return wrap;
  }

  function settingControl(row, wrap, error) {
    /* The row as last reported. Every handler reads it from here rather than
     * closing over the row it was built with, so a control still sends the
     * current value after a redraw that did not rebuild it. */
    var control = {row: row};

    function applyCommon(next) {
      control.row = next;
      wrap.className = settingClass(next);
      error.textContent = next.error ? t(next.error) : "";
      error.hidden = !next.error;
    }

    if (row.kind === "boolean") {
      var toggle = element("button", "toggle");
      toggle.type = "button";
      toggle.id = settingId(row);
      toggle.addEventListener("click", function () {
        send("setSetting", {key: control.row.key, value: !control.row.value});
      });
      control.node = toggle;
      control.apply = function (next) {
        applyCommon(next);
        toggle.textContent = t("settings.value." + String(next.value));
        toggle.setAttribute("aria-pressed", String(next.value === true));
      };
      return control;
    }

    /* A key is answered by pressing it, and it is named by itself: a key is a
     * stored technical value -- the same word MTA's own `bindKey` takes -- so
     * putting it through the string table would be inventing a translation for
     * an identifier. */
    if (row.kind === "key") {
      var capture = keyCapture({
        name: row.key,
        onChoose: function (name) {
          send("setSetting", {key: control.row.key, value: name});
        }
      });
      capture.button.id = settingId(row);
      control.node = capture.root;
      control.apply = function (next) {
        applyCommon(next);
        capture.setKeys(next.options, next.bindableKeys);
        capture.setValue(next.value);
      };
      return control;
    }

    if (row.kind === "choice") {
      var menu = drawnMenu({
        name: row.key,
        onChoose: function (value) {
          send("setSetting", {key: control.row.key, value: value});
        }
      });
      menu.button.id = settingId(row);
      menu.setOptions((row.options || []).map(function (value) {
        return {value: value, label: t("settings.value." + value)};
      }));
      control.node = menu.root;
      control.apply = function (next) {
        applyCommon(next);
        menu.setValue(next.value);
      };
      return control;
    }

    if (row.kind === "color") {
      var picker = colorPicker({
        name: row.key,
        value: row.value,
        onChoose: function (value) {
          send("setSetting", {key: control.row.key, value: value});
        }
      });
      picker.button.id = settingId(row);
      control.node = picker.root;
      control.apply = function (next) {
        applyCommon(next);
        picker.setValue(next.value);
      };
      return control;
    }

    var input = document.createElement("input");
    input.id = settingId(row);
    input.type = row.kind === "number" ? "number" : "text";
    if (row.kind === "number") {
      input.min = row.min;
      input.max = row.max;
      input.step = row.step;
    }
    /* Validated on blur rather than only on submit: there is no submit here,
     * and finding out on the way out is finding out too late. */
    input.addEventListener("change", function () {
      send("setSetting", {
        key: control.row.key,
        value: control.row.kind === "number"
          ? parseFloat(input.value)
          : input.value
      });
    });
    /* What Lua last reported for this field. A push that reports the same
     * thing leaves the box alone, so typing survives every redraw that is not
     * about this setting. */
    var reported;
    control.node = input;
    control.apply = function (next) {
      applyCommon(next);
      var value = next.value === false || next.value === undefined
        ? ""
        : String(next.value);
      if (value !== reported) {
        reported = value;
        input.value = value;
      }
    };
    return control;
  }

  /* Settings is not one of these any more: it is a column of the workspace,
   * beside the list rather than over it. What is left is the gate and the work,
   * and the gate is a consequence rather than a request -- there is no
   * connection to talk to, so there is nothing else to show. */
  function show(section) {
    document.getElementById("section-connection").hidden = section !== "connection";
    document.getElementById("section-entities").hidden = section !== "entities";
  }

  /** The one entry point Lua calls. A whole state in, a whole render out. */
  function receive(state) {
    locale = state.locale || {};
    applyLocale();
    renderConnection(state.connection || {state: "disconnected"});
    selected = state.selected || {mapId: false, entityId: false, cardId: false};
    settingsOpen = state.settingsOpen === true;
    focusOnSelect = state.focusOnSelect !== false;
    renderDrawRadius(state.drawRadius);
    renderStudy(state.study || {active: false, resumable: false});
    renderSettings(state.settings);
    /* The entity pane's controls are filled from the same rows Settings is
     * drawn from: which keys ANKIGTA can bind is the schema's answer, and
     * asking for it twice is two answers that can disagree. */
    fillEntityChoices(state.settings);
    lastEntities = state.entities || [];
    renderRows(state.entities);
    renderCards(state.cardPicker);
    renderNotice(state.notice);
    document.getElementById("entity-count").textContent = state.entityFilter
      ? t("f7.filterResult")
          .replace("%d", (state.entities || []).length)
          .replace("%d", state.entityTotal)
      : (state.entities || []).length;
    var filter = document.getElementById("filter");
    if (filter.value !== state.entityFilter) filter.value = state.entityFilter || "";

    var history = state.history || {};
    document.getElementById("undo").disabled = !history.canUndo;
    document.getElementById("redo").disabled = !history.canRedo;

    /* Disabled rather than hidden: a control that vanishes is a control the
     * player has to rediscover, and its absence says nothing about why. */
    var entity = findSelected(state.entities);
    document.getElementById("recheck").disabled =
      !entity || !entity.recheckAvailable;
    /* Finding the thing is useful whatever state it is in, so this is enabled
     * for anything selected at all. */
    document.getElementById("teleport").disabled = !entity;
    document.getElementById("unlink").disabled =
      !entity || !LINK_CHANGEABLE[entity.linkState];
    document.getElementById("relink").disabled =
      !entity || entity.linkState !== "Entity missing";
    /* An object picked in the world but not adopted yet has no row to be the
     * selected entity, and linking is exactly what adopts it. */
    document.getElementById("link").disabled =
      (!entity && !selected.adopting) || !selected.cardId;
    document.getElementById("replace").disabled =
      !entity || !selected.cardId || !LINK_CHANGEABLE[entity.linkState];
    document.getElementById("copy-decision").hidden =
      !entity || !entity.copyCollision;

    /* One question at a time, about the first object that left the map. It is
       not a row any more -- that is the point -- so it is asked here rather
       than shown as a state on something the list no longer holds. */
    var deleted = (state.deletedFromMap || [])[0];
    document.getElementById("deleted-decision").hidden = !deleted;
    if (deleted) {
      document.getElementById("deleted-question").textContent =
        t("f7.deleted.question")
          .replace("%s", deleted.name)
          .replace("%s", deleted.mapName);
    }

    /* Offered for every selected row, including one the list is only offering:
     * writing to it is what takes it into the store. A form that appears only
     * after a card has been linked makes naming a thing a statement about a
     * card. */
    renderEntityPane(entity);

    renderInspector(state);
    show(state.section);
  }

  document.getElementById("close").addEventListener("click", function () {
    send("close");
  });
  document.getElementById("settings").addEventListener("click", function () {
    send("openSettings");
  });
  document.getElementById("edit-hud").addEventListener("click", function () {
    var button = document.getElementById("edit-hud");
    var next = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", String(next));
    send("editHud", {value: next});
  });
  document.getElementById("reset-layout").addEventListener("click", function () {
    send("resetLayout");
  });
  document.getElementById("close-settings").addEventListener("click", function () {
    send("closeSettings");
  });
  document.getElementById("start-study").addEventListener("click", function () {
    send("startStudy");
  });
  var SIMPLE = {
    "pick-entity": ["pickEntity", {mode: "pick"}],
    "teleport": ["teleport", {}],
    "recheck": ["recheck", {}],
    "unlink": ["unlink", {}],
    "relink": ["pickEntity", {mode: "relink"}],
    "undo": ["undo", {}],
    "redo": ["redo", {}],
    "link": ["link", {}],

    "copy-original": ["copyDecision", {decision: "original_or_renamed"}],
    "copy-new": ["copyDecision", {decision: "new_copy"}],

    /* The object left the map. Both answers are the player's; neither is
       taken for them. */
    "deleted-forget": ["forgetEntity", {}],
    "deleted-keep": ["keepDeletedEntity", {}]
  };
  Object.keys(SIMPLE).forEach(function (id) {
    document.getElementById(id).addEventListener("click", function () {
      send(SIMPLE[id][0], SIMPLE[id][1]);
    });
  });
  /* Replacing throws away a link the player made, so it asks first and shows
   * both cards while it does. */
  var pendingReplace = null;

  function closeReplace() {
    pendingReplace = null;
    document.getElementById("replace-dialog").hidden = true;
  }

  document.getElementById("replace").addEventListener("click", function () {
    var entity = pendingReplace = findSelected(lastEntities);
    if (!entity) return;
    document.getElementById("replace-old").textContent = entity.linkedCard
      ? t("cardPicker.column.card") + " " + entity.linkedCard
      : t("f7.replaceUnknownCard");
    document.getElementById("replace-new").textContent =
      selectedCardLabel || String(selected.cardId || "");
    document.getElementById("replace-dialog").hidden = false;
  });
  document.getElementById("replace-cancel").addEventListener("click", closeReplace);
  document.getElementById("replace-confirm").addEventListener("click", function () {
    closeReplace();
    send("replaceCard");
  });

  /* The Activation Zone of the selected entity, sent when the field is left
   * rather than on every keystroke: a half-typed number is not a radius.
   * Emptied means "follow Settings again" rather than "no radius": nothing is
   * stored, so a later change to the global moves this entity with it. */
  document.getElementById("entity-radius").addEventListener("change", function () {
    var typed = document.getElementById("entity-radius").value;
    send("setEntityMarks", {
      radius: String(typed) === "" ? INHERIT : parseFloat(typed)
    });
  });
  document.getElementById("entity-name").addEventListener("change", function () {
    send("setEntityName", {
      name: document.getElementById("entity-name").value
    });
  });
  /* Sent when the field is left rather than on every keystroke, and emptied
   * means "follow Settings again" -- the same two rules the radius box has. */
  document
    .getElementById("entity-corona-opacity")
    .addEventListener("change", function () {
      var typed = document.getElementById("entity-corona-opacity").value;
      send("setEntityMarks", {
        coronaOpacity: String(typed) === "" ? INHERIT : parseFloat(typed)
      });
    });
  /* The Text Label's field and size on this one entity, under the two rules
   * every box on this pane follows: sent when the field is left, and emptied
   * means "follow Settings again". */
  document
    .getElementById("entity-text-label-field")
    .addEventListener("change", function () {
      var typed = document.getElementById("entity-text-label-field").value;
      send("setEntityMarks", {
        textLabelField: String(typed) === "" ? INHERIT : String(typed)
      });
    });
  document
    .getElementById("entity-text-label-size")
    .addEventListener("change", function () {
      var typed = document.getElementById("entity-text-label-size").value;
      send("setEntityMarks", {
        textLabelSize: String(typed) === "" ? INHERIT : parseFloat(typed)
      });
    });

  /* The sweep asks before it runs, and the question it asks came from the
   * server -- so Cancel is a real answer and leaves the world untouched. */
  document.getElementById("bulk-cancel").addEventListener("click", function () {
    send("cancelClearEntityOverrides");
  });
  document.getElementById("bulk-confirm").addEventListener("click", function () {
    var pending = lastPendingClear;
    if (!pending) return;
    send("clearEntityOverrides", {key: pending.key, confirmed: true});
  });

  document.getElementById("toggle-inspector").addEventListener("click", function () {
    inspectorOpen = !inspectorOpen;
    renderInspectorToggle();
    document.getElementById("inspector").hidden =
      !selected.cardId || !inspectorOpen;
    /* The page cannot resize its own window, so it says which shape it is in
     * and Lua gives it the room. The editor slides out beside the lists rather
     * than taking a third of the room from them. */
    send("editorVisible", {open: inspectorOpen});
  });
  document.getElementById("inspector-tags").addEventListener(
    "input",
    refreshSaveState
  );
  document.getElementById("save-note").addEventListener("click", function () {
    var fields = [];
    for (var i = 0; i < noteBoxes.length; i += 1) {
      fields.push({
        name: noteBoxes[i].getAttribute("data-field"),
        value: noteBoxes[i].value
      });
    }
    /* Split on whitespace: Anki separates tags by spaces, so what the field
     * holds is a list however it was typed. */
    var typed = document.getElementById("inspector-tags").value;
    var tags = typed.split(/\s+/).filter(function (tag) { return tag !== ""; });
    document.getElementById("inspector-state").textContent = t("inspector.saved");
    send("saveNote", {fields: fields, tags: tags});
  });

  document.getElementById("filter-form").addEventListener("submit", function (e) {
    e.preventDefault();
    send("filter", {text: document.getElementById("filter").value});
  });
  function submitSearch() {
    send("searchCards", {
      query: document.getElementById("search-query").value,
      deck: chosenDeck,
      scope: chosenScope
    });
  }

  document.getElementById("search").addEventListener("submit", function (event) {
    event.preventDefault();
    submitSearch();
  });

  function applyConnection() {
    var portText = document.getElementById("port").value;
    var port = portText === "" ? null : Number(portText);
    var tokenField = document.getElementById("token");
    var replacingToken = tokenField.getAttribute("data-replacement") === "true";
    send("updateConnection", {
      mode: "manual",
      port: port === null || isNaN(port) ? null : port,
      token: replacingToken ? tokenField.value : "",
      keepToken: !replacingToken
    });
    tokenField.setAttribute("data-replacement", "false");
    if (replacingToken) {
      tokenField.value = tokenField.value === "" ? "" : HIDDEN_TOKEN;
    }
  }

  function renderConnectionError(fieldId, reason) {
    var field = document.getElementById(fieldId);
    var error = document.getElementById(fieldId + "-error");
    field.setAttribute("aria-invalid", reason ? "true" : "false");
    error.textContent = reason ? t(reason) : "";
    error.hidden = !reason;
  }
  document.getElementById("port").addEventListener("change", applyConnection);
  document.getElementById("token").addEventListener("focus", function () {
    if (this.value === HIDDEN_TOKEN) this.select();
  });
  document.getElementById("token").addEventListener("input", function () {
    this.setAttribute("data-replacement", "true");
  });
  document.getElementById("token").addEventListener("change", applyConnection);

  /* The page cannot move its own window, so it only reports that a drag began
   * and Lua follows the cursor. Buttons and fields in the bar keep their own
   * clicks: a drag that starts on X is a drag nobody meant. */
  var dragHandle = document.querySelector("[data-window-drag]");
  if (dragHandle) {
    dragHandle.addEventListener("mousedown", function (event) {
      if (event.button !== 0 || event.target.closest("button, input")) return;
      event.preventDefault();
      send("dragStart");
    });
  }
  document.addEventListener("mouseup", function () {
    send("dragEnd");
  });

  /* Clicking away from an open list closes it, the way a native one behaved,
   * and clicking away from a control waiting for a key stops it waiting: both
   * are surfaces the player opened and can leave by looking elsewhere. The
   * list, the button that opens it and the key control stop their own clicks
   * here. */
  document.addEventListener("click", function () {
    closeOpenPopup();
    stopListeningForAKey();
  });

  function typingInto(target) {
    var tag = target && target.tagName;
    return tag === "INPUT" || tag === "TEXTAREA";
  }

  document.addEventListener("keydown", function (event) {
    /* A control waiting for a key takes the press whole, before anything else
     * on this page can read it: every key on the keyboard is a possible answer
     * here, including the arrows that walk the list and the Escape that shuts
     * the panel.
     *
     * Escape is the way out rather than an answer. It is a key ANKIGTA already
     * answers to, so it can never be what is stored, and a control with no way
     * out of it is worse than one that cannot be given `escape`. The button
     * says so while it waits. */
    if (listeningCapture) {
      if (event.preventDefault) event.preventDefault();
      if (event.key === "Escape") {
        listeningCapture.listen(false);
        return;
      }
      listeningCapture.take(event);
      return;
    }
    /* Escape closes, because a panel that traps the cursor and cannot be left
     * is the defect this replaces. An open list is what it closes first:
     * closing the whole panel out from under someone who only wanted to back
     * out of a list is not what they pressed it for. */
    if (event.key === "Escape") {
      if (openPopup) {
        closeOpenPopup();
        return;
      }
      send("close");
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    /* Not while the caret is in a field: down inside a number box is the box's
     * own, and inside a note field it is the next line. */
    if (typingInto(event.target)) return;
    if (document.getElementById("section-entities").hidden) return;
    if (event.preventDefault) event.preventDefault();
    moveSelection(event.key === "ArrowDown" ? 1 : -1);
  });

  window.ANKIGTA = {receive: receive};
  send("ready");
})();

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
  }

  var selected = {mapId: false, entityId: false, cardId: false};
  var lastConnectionFields = null;
  var HIDDEN_TOKEN = "••••••••";
  /* The last rows rendered, and a readable label for the chosen card. Kept so
   * the replace confirmation can name what it is about to throw away without
   * asking Lua for a state it has already sent. */
  var lastEntities = [];
  var selectedCardLabel = "";

  /* A link state is a stable technical value; only its display follows the
   * language, and its tone is set here rather than in the string table. */
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

  function renderRows(entities) {
    var host = document.getElementById("rows");
    host.textContent = "";
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
      host.appendChild(row);
    }
  }

  /* A row identifies itself by the pair the server knows it by, never by its
   * index: the list re-sorts whenever the snapshot changes, and an index would
   * quietly start pointing at a different Map Entity. */
  function bindSelect(row, entry) {
    row.addEventListener("click", function () {
      send("select", {mapId: entry.mapId, entityId: entry.entityId});
    });
    row.addEventListener("dblclick", function () {
      send("focusEntity", {mapId: entry.mapId, entityId: entry.entityId});
    });
  }

  /* A deck is chosen, not typed. Rebuilt only when the list actually changed,
   * so an open dropdown is not yanked shut by an unrelated redraw. */
  var lastDeckList = null;

  function renderDecks(picker) {
    var decks = (picker && picker.decks) || [];
    var signature = JSON.stringify(decks);
    if (signature === lastDeckList) return;
    lastDeckList = signature;

    var select = document.getElementById("deck");
    var chosen = select.value;
    select.textContent = "";
    var any = document.createElement("option");
    any.value = "";
    any.textContent = t("cardPicker.anyDeck");
    select.appendChild(any);
    for (var i = 0; i < decks.length; i += 1) {
      var option = document.createElement("option");
      option.value = decks[i];
      option.textContent = decks[i];
      select.appendChild(option);
    }
    /* What the server says the filter is beats what was left in the control:
     * they disagree only when somebody else changed it. */
    select.value = (picker && picker.deckFilter) || chosen || "";
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
      document.getElementById("scope").value = scope;
    }
  }

  function renderCards(picker) {
    selectedCardLabel = "";
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
      primary.appendChild(element("strong", null, card.question || card.cardId));
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
        selectedCardLabel = (card.question || card.cardId) + " — " + card.deck;
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

  /* The note behind the selected card: what it says, and what the player has
   * typed into it. Rebuilt only when a different note arrives, so typing is
   * not thrown away by an unrelated redraw -- a state push happens whenever
   * anything at all changes, and most of it is not this. */
  var shownNote = null;

  function renderInspector(state) {
    var box = document.getElementById("inspector");
    var error = document.getElementById("inspector-error");
    var status = document.getElementById("inspector-state");

    if (!selected.cardId) {
      box.hidden = true;
      shownNote = null;
      return;
    }
    box.hidden = false;

    if (state.noteError) {
      error.textContent = t("inspector.unreadable").replace("%s", state.noteError);
      status.textContent = "";
      document.getElementById("inspector-fields").textContent = "";
      document.getElementById("save-note").disabled = true;
      shownNote = null;
      return;
    }
    error.textContent = "";

    var note = state.note;
    if (!note) {
      status.textContent = t("inspector.loading");
      document.getElementById("save-note").disabled = true;
      return;
    }
    status.textContent = "";
    document.getElementById("save-note").disabled = false;

    var signature = JSON.stringify([
      note.noteId,
      (note.fields || []).map(function (f) { return f.name; })
    ]);
    if (signature === shownNote) return;
    shownNote = signature;

    var host = document.getElementById("inspector-fields");
    host.textContent = "";
    var fields = note.fields || [];
    for (var i = 0; i < fields.length; i += 1) {
      var wrap = element("label", "inspector-field");
      wrap.appendChild(element("span", null, fields[i].name));
      var input = document.createElement("textarea");
      input.rows = 2;
      input.value = fields[i].value;
      input.setAttribute("data-field", fields[i].name);
      wrap.appendChild(input);
      host.appendChild(wrap);
    }
    document.getElementById("inspector-tags").value =
      (note.tags || []).join(" ");
  }

  function renderNotice(notice) {
    var node = document.getElementById("notice");
    if (!notice) { node.hidden = true; return; }
    node.textContent = t(notice.key).replace("%s", notice.detail || "");
    node.className = "notice warning";
    node.hidden = false;
  }

  /* One row per setting, built from what Lua sent rather than from a list
   * kept here: a setting added to the schema appears by existing. */
  function renderSettings(settings) {
    var host = document.getElementById("settings-rows");
    host.textContent = "";
    var rows = (settings && settings.rows) || [];
    for (var i = 0; i < rows.length; i += 1) {
      host.appendChild(settingRow(rows[i]));
    }
  }

  /* Two rows carry the same setting key when it is per map, so the id is the
   * key and the map together: duplicate ids would point every label at the
   * first control and leave the rest unreachable by their own names. */
  function settingId(row) {
    return "set-" + row.key + (row.mapId ? "-" + row.mapId : "");
  }

  /* A map's own name is the user's words, so it arrives as text rather than as
   * a key to look up. Everything else is named by the string table. */
  function settingLabel(row) {
    return row.labelText !== undefined && row.labelText !== null
      ? row.labelText
      : t(row.labelKey || "settings." + row.key);
  }

  function settingRow(row) {
    /* A group's heading and the line that says there is nothing under it are
     * text, not controls: giving them a label and an empty field would offer
     * something to change where there is nothing. */
    if (row.kind === "heading") {
      return element("h3", "setting-heading", settingLabel(row));
    }
    if (row.kind === "note") {
      return element("p", "setting-note", settingLabel(row));
    }
    var wrap = element("div", row.mapId ? "setting per-map" : "setting");
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
    wrap.appendChild(settingControl(row));

    /* The reason sits under the field it belongs to, and announces itself:
     * a red border is not a message a screen reader receives. */
    var error = element("p", "field-error", row.error ? t(row.error) : "");
    error.setAttribute("role", "alert");
    error.hidden = !row.error;
    wrap.appendChild(error);
    if (row.error) wrap.className += " invalid";
    return wrap;
  }

  function settingControl(row) {
    if (row.kind === "boolean") {
      var toggle = element("button", "toggle");
      toggle.type = "button";
      toggle.id = settingId(row);
      toggle.textContent = t("settings.value." + String(row.value));
      toggle.setAttribute("aria-pressed", String(row.value === true));
      toggle.addEventListener("click", function () {
        /* The map travels with the change: a per-map setting written without
         * one is a global value that nothing reads. */
        send("setSetting", {key: row.key, value: !row.value, mapId: row.mapId});
      });
      return toggle;
    }
    if (row.kind === "choice") {
      var select = document.createElement("select");
      select.id = settingId(row);
      for (var i = 0; i < row.options.length; i += 1) {
        var option = document.createElement("option");
        option.value = row.options[i];
        option.textContent = t("settings.value." + row.options[i]);
        if (row.options[i] === row.value) option.selected = true;
        select.appendChild(option);
      }
      select.addEventListener("change", function () {
        send("setSetting", {key: row.key, value: select.value});
      });
      return select;
    }
    var input = document.createElement("input");
    input.id = settingId(row);
    input.type = row.kind === "number" ? "number" : "text";
    if (row.kind === "number") {
      input.min = row.min;
      input.max = row.max;
      input.step = row.step;
    }
    input.value = row.value === false || row.value === undefined ? "" : row.value;
    /* Validated on blur rather than only on submit: there is no submit here,
     * and finding out on the way out is finding out too late. */
    input.addEventListener("change", function () {
      send("setSetting", {
        key: row.key,
        value: row.kind === "number" ? parseFloat(input.value) : input.value
      });
    });
    return input;
  }

  function show(section) {
    document.getElementById("section-connection").hidden = section !== "connection";
    document.getElementById("section-entities").hidden = section !== "entities";
    document.getElementById("section-settings").hidden = section !== "settings";
  }

  /** The one entry point Lua calls. A whole state in, a whole render out. */
  function receive(state) {
    locale = state.locale || {};
    document.documentElement.lang = state.language || "en";
    applyLocale();
    renderConnection(state.connection || {state: "disconnected"});
    selected = state.selected || {mapId: false, entityId: false, cardId: false};
    renderStudy(state.study || {active: false, resumable: false});
    renderSettings(state.settings);
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

    /* Only a row the store holds has an Activation Zone: an offer has nothing
     * to write one on yet. */
    var settings = document.getElementById("entity-settings");
    settings.hidden = !entity || entity.adoptable === true;
    if (!settings.hidden) {
      document.getElementById("entity-name").value = entity.name || "";
      document.getElementById("entity-radius").value = entity.radius;
      document.getElementById("entity-show-radius").checked =
        entity.showRadius === true;
    }

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
    "copy-new": ["copyDecision", {decision: "new_copy"}]
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
   * rather than on every keystroke: a half-typed number is not a radius. */
  document.getElementById("entity-radius").addEventListener("change", function () {
    send("setEntityRadius", {
      radius: parseFloat(document.getElementById("entity-radius").value)
    });
  });
  document.getElementById("entity-name").addEventListener("change", function () {
    send("setEntityName", {
      name: document.getElementById("entity-name").value
    });
  });
  document.getElementById("entity-show-radius").addEventListener("change", function () {
    send("setEntityRadius", {
      showRadius: document.getElementById("entity-show-radius").checked
    });
  });

  document.getElementById("save-note").addEventListener("click", function () {
    var fields = [];
    var boxes = document.querySelectorAll("#inspector-fields [data-field]");
    for (var i = 0; i < boxes.length; i += 1) {
      fields.push({
        name: boxes[i].getAttribute("data-field"),
        value: boxes[i].value
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
  document.getElementById("search").addEventListener("submit", function (event) {
    event.preventDefault();
    send("searchCards", {
      query: document.getElementById("search-query").value,
      deck: document.getElementById("deck").value,
      scope: document.getElementById("scope").value
    });
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

  /* Escape closes, because a panel that traps the cursor and cannot be left is
   * the defect this replaces. */
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") send("close");
  });

  window.ANKIGTA = {receive: receive};
  send("ready");
})();

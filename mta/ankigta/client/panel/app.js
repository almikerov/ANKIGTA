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

  /* A link state is a stable technical value; only its display follows the
   * language, and its tone is set here rather than in the string table. */
  var TONES = {
    "Active Spatial Link": "good",
    "Unlinked": "",
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
        element("strong", null, entry.name || entry.entityId)
      );
      primary.appendChild(
        element("span", "sub", entry.mapId + " / " + entry.entityId)
      );
      row.appendChild(primary);

      row.appendChild(element("span", "type", entry.type));
      row.appendChild(element("span", "runtime", t(entry.runtimeKey)));

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
  }

  function renderCards(picker) {
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
      row.appendChild(primary);
      row.appendChild(element("span", "type", card.state));

      if (card.cardId === selected.cardId) row.className = "row card selected";
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

  function renderNotice(notice) {
    var node = document.getElementById("notice");
    if (!notice) { node.hidden = true; return; }
    node.textContent = t(notice.key).replace("%s", notice.detail || "");
    node.className = "notice warning";
    node.hidden = false;
  }

  function show(section) {
    document.getElementById("section-connection").hidden = section !== "connection";
    document.getElementById("section-entities").hidden = section !== "entities";
  }

  /** The one entry point Lua calls. A whole state in, a whole render out. */
  function receive(state) {
    locale = state.locale || {};
    document.documentElement.lang = state.language || "en";
    applyLocale();
    renderConnection(state.connection || {state: "disconnected"});
    selected = state.selected || {mapId: false, entityId: false, cardId: false};
    renderStudy(state.study || {active: false, resumable: false});
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
    document.getElementById("unlink").disabled =
      !entity || !LINK_CHANGEABLE[entity.linkState];
    document.getElementById("relink").disabled =
      !entity || entity.linkState !== "Entity missing";
    document.getElementById("link").disabled = !entity || !selected.cardId;
    document.getElementById("replace").disabled =
      !entity || !selected.cardId || !LINK_CHANGEABLE[entity.linkState];
    document.getElementById("copy-decision").hidden =
      !entity || !entity.copyCollision;

    show(state.section);
  }

  document.getElementById("close").addEventListener("click", function () {
    send("close");
  });
  document.getElementById("settings").addEventListener("click", function () {
    send("openSettings");
  });
  document.getElementById("connect").addEventListener("click", function () {
    send("connect");
  });
  document.getElementById("start-study").addEventListener("click", function () {
    send("startStudy");
  });
  var SIMPLE = {
    "pick-entity": ["pickEntity", {mode: "pick"}],
    "recheck": ["recheck", {}],
    "unlink": ["unlink", {}],
    "relink": ["pickEntity", {mode: "relink"}],
    "undo": ["undo", {}],
    "redo": ["redo", {}],
    "link": ["link", {}],
    "replace": ["replaceCard", {}],
    "copy-original": ["copyDecision", {decision: "original_or_renamed"}],
    "copy-new": ["copyDecision", {decision: "new_copy"}]
  };
  Object.keys(SIMPLE).forEach(function (id) {
    document.getElementById(id).addEventListener("click", function () {
      send(SIMPLE[id][0], SIMPLE[id][1]);
    });
  });
  document.getElementById("filter-form").addEventListener("submit", function (e) {
    e.preventDefault();
    send("filter", {text: document.getElementById("filter").value});
  });
  document.getElementById("search").addEventListener("submit", function (event) {
    event.preventDefault();
    send("searchCards", {query: "", deck: document.getElementById("deck").value});
  });
  document.getElementById("save-connection").addEventListener("click", function () {
    var port = parseInt(document.getElementById("port").value, 10);
    var token = document.getElementById("token").value;
    send("updateConnection", {
      mode: "manual",
      port: isNaN(port) ? null : port,
      token: token,
      keepToken: token === ""
    });
  });

  /* Escape closes, because a panel that traps the cursor and cannot be left is
   * the defect this replaces. */
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") send("close");
  });

  window.ANKIGTA = {receive: receive};
  send("ready");
})();

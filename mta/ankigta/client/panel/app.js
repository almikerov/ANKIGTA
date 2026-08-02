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
  }

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

      var state = element("span", "state");
      var tone = TONES[entry.linkState];
      if (tone) state.setAttribute("data-tone", tone);
      state.appendChild(element("span", "marker"));
      state.appendChild(
        element("span", "label", t("f7.linkState." + entry.linkState))
      );
      row.appendChild(state);

      host.appendChild(row);
    }
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
    renderRows(state.entities);
    document.getElementById("entity-count").textContent =
      (state.entities || []).length;
    show(state.section);
  }

  document.getElementById("close").addEventListener("click", function () {
    send("close");
  });
  document.getElementById("connect").addEventListener("click", function () {
    send("connect");
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

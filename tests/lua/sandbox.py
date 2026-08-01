"""Run ANKIGTA's server-side Lua against a real Lua 5.1 interpreter.

The MTA resource scripts were previously covered only by substring searches over
their own source text, which proved nothing about behavior and broke whenever a
later ticket edited the file. This sandbox loads the real scripts into Lua 5.1 —
the version MTA embeds, including `setfenv` and `loadstring` — and backs the MTA
API with recording stubs, so tests can call the code and assert on what it did.

Stub fidelity is taken from the MTA server source, not from memory:

- `dbPoll(handle, timeout)` returns `rows, affectedRows, lastInsertId` on
  success and `false, errorCode, errorMessage` on failure
  (`CLuaDatabaseDefs::DbPoll`).
- Result rows are a 1-based array of tables keyed by column name, where INTEGER
  and REAL arrive as numbers, TEXT and BLOB as strings, and **SQL NULL arrives
  as boolean `false`** rather than nil (`PushRegistryResultTable`).
- `sha256` returns **uppercase** hex (`ConvertDataToHexString`).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lupa.lua51 import LuaRuntime, lua_type


RESOURCE_ROOT = Path(__file__).resolve().parents[2] / "mta" / "ankigta"


class LuaError(AssertionError):
    """A Lua script failed to load or run."""


@dataclass
class Timer:
    """A timer registered through `setTimer`."""

    callback: Any
    interval_ms: int
    repeats: int
    args: tuple[Any, ...]
    cancelled: bool = False


@dataclass
class DebugLine:
    message: str
    level: int


@dataclass
class TriggeredEvent:
    name: str
    source: Any
    args: tuple[Any, ...]


@dataclass
class Recorder:
    """Everything the sandbox observed, for tests to assert against."""

    debug: list[DebugLine] = field(default_factory=list)
    timers: list[Timer] = field(default_factory=list)
    client_events: list[TriggeredEvent] = field(default_factory=list)
    server_events: list[TriggeredEvent] = field(default_factory=list)
    local_events: list[TriggeredEvent] = field(default_factory=list)
    remote_fetches: list[dict[str, Any]] = field(default_factory=list)

    def debug_messages(self) -> list[str]:
        return [line.message for line in self.debug]


class _Connection:
    """Stands in for the element `dbConnect` returns."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.raw = sqlite3.connect(path)
        self.raw.isolation_level = None  # the Lua code drives its own BEGIN
        self.destroyed = False

    def close(self) -> None:
        if not self.destroyed:
            self.raw.close()
            self.destroyed = True


class _QueryHandle:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None,
        affected: int,
        last_insert_id: int,
        error: tuple[int, str] | None,
    ) -> None:
        self.rows = rows
        self.affected = affected
        self.last_insert_id = last_insert_id
        self.error = error
        self.polled = False


class MtaSandbox:
    """A Lua 5.1 environment with MTA's server API stubbed out."""

    def __init__(self, *, database_path: str = ":memory:") -> None:
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.recorder = Recorder()
        self.database_path = database_path
        self._tick = 0
        self._connections: list[_Connection] = []
        self._elements: set[int] = set()
        self._handlers: dict[str, list[Any]] = {}
        self._exports: dict[str, Any] = {}
        # Client-side observable state, for tests to assert against.
        self.controls: dict[str, bool] = {}
        self.cursor_visible = False
        self.camera_target: Any = None
        self.radio_channel = 0
        self.bound_keys: dict[tuple[str, str], list[Any]] = {}
        self.browsers: list[Any] = []
        self.loaded_urls: list[str] = []
        self.requested_domains: list[str] = []
        self.browser_available = True
        self.browser_volume = 1.0
        self.world_sound_enabled = True
        self.damage_proof: dict[str, bool] = {}
        self.occupied_vehicle: Any = False
        self._install_globals()

    # ---------------------------------------------------------------- loading

    def load(self, relative_path: str) -> None:
        """Load a resource script, e.g. `server/store.lua`."""
        path = RESOURCE_ROOT / relative_path
        source = path.read_text(encoding="utf-8")
        chunk = self.lua.eval("loadstring")(source, f"@{relative_path}")
        if chunk is None:
            raise LuaError(f"could not compile {relative_path}")
        # pcall returns just `true` when the chunk returns nothing.
        result = self.lua.eval("pcall")(chunk)
        if isinstance(result, tuple):
            ok, error = result[0], result[1]
        else:
            ok, error = result, None
        if not ok:
            raise LuaError(f"{relative_path} failed to load: {error}")

    def globals(self) -> Any:
        return self.lua.globals()

    def eval(self, expression: str) -> Any:
        return self.lua.eval(expression)

    def execute(self, statement: str) -> Any:
        return self.lua.execute(statement)

    def table(self, mapping: dict[str, Any]) -> Any:
        """Build a Lua table from a Python mapping."""
        return self.lua.table_from(mapping)

    # ----------------------------------------------------------------- clocks

    def advance(self, milliseconds: int) -> None:
        """Move the fake clock forward without firing timers."""
        self._tick += milliseconds

    def fire_timers(self, *, max_rounds: int = 100) -> int:
        """Run every pending timer once, in registration order.

        Repeating timers stay registered. Returns how many callbacks ran.
        """
        fired = 0
        for _ in range(max_rounds):
            pending = [
                timer
                for timer in self.recorder.timers
                if not timer.cancelled and timer.repeats != 0
            ]
            if not pending:
                break
            for timer in pending:
                if timer.cancelled:
                    continue
                self._tick += timer.interval_ms
                timer.callback(*timer.args)
                fired += 1
                if timer.repeats > 0:
                    timer.repeats -= 1
                else:
                    # An endless timer would loop forever; run it once.
                    timer.cancelled = True
            break
        return fired

    # ---------------------------------------------------------------- events

    def trigger(self, event: str, source: Any = None, *args: Any) -> None:
        """Invoke every handler registered for an event.

        MTA exposes the event's source as a global during dispatch, and handlers
        legitimately branch on it, so set it the same way.
        """
        for handler in self._handlers.get(event, []):
            self._dispatch(handler, source, args)

    def _dispatch(self, handler: Any, source: Any, args: tuple[Any, ...]) -> None:
        g = self.lua.globals()
        previous = g.source
        g.source = source
        try:
            handler(*args)
        finally:
            g.source = previous

    def handlers(self, event: str) -> list[Any]:
        return list(self._handlers.get(event, []))

    # ----------------------------------------------------------------- http

    def complete_fetch(
        self,
        index: int = -1,
        *,
        body: str = "",
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Deliver a response to a recorded `fetchRemote` call."""
        fetch = self.recorder.remote_fetches[index]
        callback = fetch["callback"]
        if callback is None:
            raise LuaError("fetchRemote was called without a callback")
        info = self.lua.table_from(
            {
                "statusCode": status,
                "success": status == 200,
                "headers": self.lua.table_from(
                    headers
                    if headers is not None
                    else {"Content-Type": "application/json; charset=utf-8"}
                ),
            }
        )
        callback(body, info, *fetch["args"])

    # --------------------------------------------------------------- globals

    def _install_globals(self) -> None:
        g = self.lua.globals()

        # --- database -------------------------------------------------------
        def db_connect(
            kind: str,
            path: str,
            _user: str = "",
            _password: str = "",
            _options: str = "",
        ) -> Any:
            if kind != "sqlite":
                return False
            target = self.database_path if path else self.database_path
            connection = _Connection(target)
            self._connections.append(connection)
            self._elements.add(id(connection))
            return connection

        def db_query(connection: Any, statement: str, *params: Any) -> Any:
            if not isinstance(connection, _Connection) or connection.destroyed:
                return False
            bindings = [self._to_sqlite(value) for value in params]
            try:
                cursor = connection.raw.execute(statement, bindings)
            except sqlite3.Error as error:
                return _QueryHandle(None, 0, 0, (1, str(error)))
            rows: list[dict[str, Any]] | None = None
            if cursor.description is not None:
                names = [column[0] for column in cursor.description]
                rows = [dict(zip(names, record)) for record in cursor.fetchall()]
            return _QueryHandle(
                rows if rows is not None else [],
                cursor.rowcount if cursor.rowcount >= 0 else 0,
                cursor.lastrowid or 0,
                None,
            )

        def db_poll(handle: Any, _timeout: int) -> Any:
            if not isinstance(handle, _QueryHandle):
                return False
            if handle.error is not None:
                code, message = handle.error
                return False, code, message
            handle.polled = True
            return (
                self._rows_to_lua(handle.rows or []),
                handle.affected,
                handle.last_insert_id,
            )

        def db_free(handle: Any) -> bool:
            return isinstance(handle, _QueryHandle)

        g.dbConnect = db_connect
        g.dbQuery = db_query
        g.dbPoll = db_poll
        g.dbFree = db_free

        # --- elements -------------------------------------------------------
        def is_element(value: Any) -> bool:
            if isinstance(value, _Connection):
                return not value.destroyed
            if lua_type(value) == "table":
                return value["__element"] is True and value["__destroyed"] is not True
            return id(value) in self._elements

        def destroy_element(value: Any) -> bool:
            if isinstance(value, _Connection):
                value.close()
                self._elements.discard(id(value))
                return True
            if lua_type(value) == "table" and value["__element"] is True:
                value["__destroyed"] = True
                return True
            if id(value) in self._elements:
                self._elements.discard(id(value))
                return True
            return False

        g.isElement = is_element
        g.destroyElement = destroy_element

        # --- crypto and serialisation --------------------------------------
        def sha256(data: str) -> str:
            return hashlib.sha256(str(data).encode("utf-8")).hexdigest().upper()

        def to_json(value: Any, _compact: Any = None, *_rest: Any) -> str:
            return json.dumps(self._from_lua(value), ensure_ascii=False)

        def from_json(text: str) -> Any:
            try:
                decoded = json.loads(text)
            except (TypeError, ValueError):
                return False
            return self._to_lua(decoded)

        g.sha256 = sha256
        g.toJSON = to_json
        g.fromJSON = from_json

        # --- runtime --------------------------------------------------------
        def get_tick_count() -> int:
            self._tick += 1
            return self._tick

        def output_debug_string(message: str, level: int = 3, *_rest: Any) -> bool:
            self.recorder.debug.append(DebugLine(str(message), int(level)))
            return True

        def set_timer(
            callback: Any,
            interval_ms: float,
            repeats: float,
            *args: Any,
        ) -> Any:
            timer = Timer(
                callback,
                int(interval_ms),
                int(repeats) if int(repeats) > 0 else -1,
                tuple(args),
            )
            self.recorder.timers.append(timer)
            self._elements.add(id(timer))
            return timer

        def kill_timer(timer: Any) -> bool:
            if isinstance(timer, Timer):
                timer.cancelled = True
                self._elements.discard(id(timer))
                return True
            return False

        def is_timer(timer: Any) -> bool:
            return isinstance(timer, Timer) and not timer.cancelled

        g.getTickCount = get_tick_count
        g.outputDebugString = output_debug_string
        g.setTimer = set_timer
        g.killTimer = kill_timer
        g.isTimer = is_timer

        # --- events ---------------------------------------------------------
        def add_event(_name: str, _remote: Any = None) -> bool:
            return True

        def add_event_handler(
            name: str,
            _attached_to: Any,
            handler: Any,
            *_rest: Any,
        ) -> bool:
            self._handlers.setdefault(str(name), []).append(handler)
            return True

        def trigger_event(name: str, source: Any = None, *args: Any) -> bool:
            self.recorder.local_events.append(
                TriggeredEvent(str(name), source, tuple(args))
            )
            for handler in self._handlers.get(str(name), []):
                self._dispatch(handler, source, args)
            return True

        def trigger_client_event(*args: Any) -> bool:
            # triggerClientEvent([player,] name, source, ...)
            if args and isinstance(args[0], str):
                name, source, rest = args[0], args[1] if len(args) > 1 else None, args[2:]
            else:
                name = args[1] if len(args) > 1 else ""
                source = args[2] if len(args) > 2 else None
                rest = args[3:]
            self.recorder.client_events.append(
                TriggeredEvent(str(name), source, tuple(rest))
            )
            return True

        def trigger_server_event(name: str, source: Any = None, *args: Any) -> bool:
            self.recorder.server_events.append(
                TriggeredEvent(str(name), source, tuple(args))
            )
            return True

        g.addEvent = add_event
        g.addEventHandler = add_event_handler
        g.removeEventHandler = lambda *_args: True
        g.triggerEvent = trigger_event
        g.triggerClientEvent = trigger_client_event
        g.triggerServerEvent = trigger_server_event

        # --- resource identity ---------------------------------------------
        resource = self.lua.table_from({"name": "ankigta"})
        resource_root = self.lua.table_from(
            {"__element": True, "type": "resourceRoot"}
        )
        g.resource = resource
        g.resourceRoot = resource_root
        g.root = self.lua.table_from({"type": "root"})
        g.getResourceName = lambda _resource=None: "ankigta"
        g.getThisResource = lambda: resource
        g.getResourceRootElement = lambda _resource=None: resource_root

        # --- http -----------------------------------------------------------
        def fetch_remote(
            url: str,
            options: Any = None,
            callback: Any = None,
            callback_args: Any = None,
        ) -> Any:
            # MTA forwards the callback-arguments table by iterating it with
            # lua_next, so record the values the same way.
            forwarded: tuple[Any, ...] = ()
            if lua_type(callback_args) == "table":
                forwarded = tuple(callback_args[key] for key in callback_args.keys())
            handle = object()
            self._elements.add(id(handle))
            self.recorder.remote_fetches.append(
                {
                    "url": str(url),
                    "options": self._from_lua(options),
                    "callback": callback,
                    "args": forwarded,
                    "handle": handle,
                }
            )
            return handle

        g.fetchRemote = fetch_remote
        g.abortRemoteRequest = lambda _handle=None: True

        self._install_client_globals(g)

    def _install_client_globals(self, g: Any) -> None:
        """Client-side surface: input, drawing and the CEF browser."""

        # --- input state ----------------------------------------------------
        def toggle_control(control: str, enabled: Any = True) -> bool:
            self.controls[str(control)] = enabled is True
            return True

        def is_control_enabled(control: str) -> bool:
            return self.controls.get(str(control), True)

        def show_cursor(visible: Any = True, *_rest: Any) -> bool:
            self.cursor_visible = visible is True
            return True

        g.toggleControl = toggle_control
        g.isControlEnabled = is_control_enabled
        g.showCursor = show_cursor
        g.isCursorShowing = lambda: self.cursor_visible
        g.bindKey = lambda key, state, handler, *_rest: self.bound_keys.setdefault(
            (str(key), str(state)), []
        ).append(handler) or True
        g.unbindKey = lambda key, state=None, handler=None: True

        # --- camera, radio ---------------------------------------------------
        g.getCameraTarget = lambda *_args: self.camera_target
        g.setCameraTarget = lambda target, *_rest: (
            setattr(self, "camera_target", target) or True
        )
        g.getRadioChannel = lambda: self.radio_channel
        g.setRadioChannel = lambda channel: (
            setattr(self, "radio_channel", int(channel)) or True
        )

        # --- drawing ---------------------------------------------------------
        g.guiGetScreenSize = lambda: (1920.0, 1080.0)
        g.dxDrawRectangle = lambda *_args, **_kwargs: True
        g.dxDrawText = lambda *_args, **_kwargs: True
        g.dxDrawImage = lambda *_args, **_kwargs: True
        g.tocolor = lambda r=0, gr=0, b=0, a=255: (
            (int(a) << 24) | (int(r) << 16) | (int(gr) << 8) | int(b)
        )

        # --- browser ---------------------------------------------------------
        def create_browser(
            width: float,
            height: float,
            is_local: Any = False,
            transparent: Any = False,
        ) -> Any:
            if not self.browser_available:
                return False
            browser = self.lua.table_from(
                {
                    "__element": True,
                    "type": "browser",
                    "width": float(width),
                    "height": float(height),
                    "isLocal": is_local is True,
                }
            )
            self.browsers.append(browser)
            return browser

        def load_browser_url(browser: Any, url: str, *_rest: Any) -> bool:
            self.loaded_urls.append(str(url))
            return True

        def request_browser_domains(domains: Any, *_rest: Any) -> bool:
            if lua_type(domains) == "table":
                self.requested_domains.extend(
                    str(domains[key]) for key in domains.keys()
                )
            return True

        g.createBrowser = create_browser
        g.loadBrowserURL = load_browser_url
        g.requestBrowserDomains = request_browser_domains
        def set_browser_volume(_browser: Any, volume: float) -> bool:
            self.browser_volume = float(volume)
            return True

        def set_world_sound_enabled(group: int, enabled: Any, *_rest: Any) -> bool:
            self.world_sound_enabled = enabled is True
            return True

        def set_damage_proof(element: Any, proof: Any) -> bool:
            key = "vehicle" if lua_type(element) == "table" else "player"
            self.damage_proof[key] = proof is True
            return True

        def is_damage_proof(element: Any) -> bool:
            key = "vehicle" if lua_type(element) == "table" else "player"
            return self.damage_proof.get(key, False)

        g.setElementDamageProof = set_damage_proof
        g.isElementDamageProof = is_damage_proof
        g.localPlayer = "localPlayer"
        g.getPedOccupiedVehicle = lambda _ped=None: self.occupied_vehicle
        g.setBrowserVolume = set_browser_volume
        g.setWorldSoundEnabled = set_world_sound_enabled
        g.focusBrowser = lambda _browser=None: True
        g.isBrowserFocused = lambda _browser=None: True
        g.cancelEvent = lambda *_args: True

    # ------------------------------------------------------------ conversion

    def _rows_to_lua(self, rows: list[dict[str, Any]]) -> Any:
        """Marshal SQLite rows the way MTA's PushRegistryResultTable does."""
        converted = []
        for row in rows:
            # SQL NULL becomes boolean false in MTA, not nil, so the key stays
            # present in the Lua table.
            converted.append(
                self.lua.table_from(
                    {
                        name: (False if value is None else value)
                        for name, value in row.items()
                    }
                )
            )
        return self.lua.table_from(converted)

    @staticmethod
    def _to_sqlite(value: Any) -> Any:
        if value is True or value is False:
            return int(value)
        return value

    def _to_lua(self, value: Any) -> Any:
        if isinstance(value, dict):
            return self.lua.table_from(
                {key: self._to_lua(item) for key, item in value.items()}
            )
        if isinstance(value, list):
            return self.lua.table_from([self._to_lua(item) for item in value])
        if value is None:
            return False
        return value

    def _from_lua(self, value: Any) -> Any:
        if value is None:
            return None
        # Attribute access on a Lua table indexes the table, so the type has to
        # come from lupa rather than from a probe like `value.lua_type`.
        if lua_type(value) != "table":
            return value
        keys = list(value.keys())
        if keys and all(isinstance(key, int) for key in keys):
            ordered = sorted(keys)
            if ordered == list(range(1, len(ordered) + 1)):
                return [self._from_lua(value[key]) for key in ordered]
        return {str(key): self._from_lua(value[key]) for key in keys}

    # --------------------------------------------------------------- cleanup

    @property
    def connection(self) -> _Connection:
        """The store's currently open SQLite connection."""
        for candidate in reversed(self._connections):
            if not candidate.destroyed:
                return candidate
        raise LuaError("no open database connection")

    def close(self) -> None:
        for connection in self._connections:
            connection.close()

    def __enter__(self) -> MtaSandbox:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

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
- `fileOpen` opens with `rb`/`rb+` and so **fails on a missing file**, while
  `fileCreate` opens `wb+` and truncates; `fileRename` fails when the
  destination already exists (`CScriptFile::Load`, `CLuaFileDefs::fileRename`).
- `fileCopy(source, destination[, overwrite = false])` refuses a missing source
  and, unless told to overwrite, an existing destination; it creates the
  destination's directory (`CLuaFileDefs::fileCopy`).
- `getRealTime()` reports `month` 0-11 and `year` as years since 1900, next to
  a `timestamp` in seconds (`CLuaUtilDefs::GetCTime`).
- `xmlNodeGetAttribute` returns **`false`** for an attribute that is not set,
  and `xmlLoadFile` `false` for a file that is not there (`CLuaXMLDefs`). Both
  read the same files `fileOpen` does, so one fixture map is one document to
  both APIs, and every load is recorded in `xml_loads`.

Resource files live in a real directory rather than in memory, because a
database is a file: a backup that copies bytes and is then opened as SQLite
cannot be proven against a dictionary. `dbConnect` resolves its path in the
same directory, so `backups/ankigta-3.sqlite` is one file to both APIs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping
from xml.etree import ElementTree

from lupa.lua51 import LuaRuntime, lua_type


RESOURCE_ROOT = Path(__file__).resolve().parents[2] / "mta" / "ankigta"

IN_MEMORY = ":memory:"

#: What the client-side `localPlayer` global is in this harness. MTA hands out
#: a player element; here it is a sentinel the world accessors recognise, so a
#: test moves the player by setting `sandbox.player_position` rather than by
#: reaching into a Lua table.
LOCAL_PLAYER = "localPlayer"


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


class _FileStore:
    """The resource's files, as a mapping backed by a real directory.

    Keys are resource-relative paths exactly as the scripts write them, so a
    client-private `@name` and a server-side `name` stay distinct, and
    `backups/x.sqlite` is a real file in a real subdirectory — which is what
    lets `dbConnect` open a copy the file API produced.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, path: str) -> Path:
        parts = str(path).split("/")
        if parts and parts[0].startswith(":"):
            # MTA's `:otherResource/file` reaches into another resource. It is
            # a real path here so that `fileOpen` and `xmlLoadFile` read the
            # same bytes, but a leading colon is not a legal Windows directory
            # name, so the resource name is spelt out instead.
            parts[0] = "__resource__" + parts[0][1:]
        resolved = self.root.joinpath(*parts)
        # A resource cannot write above its own directory.
        if self.root not in resolved.parents and resolved != self.root:
            raise LuaError(f"path escapes the resource directory: {path}")
        return resolved

    def __contains__(self, path: object) -> bool:
        return self.resolve(str(path)).is_file()

    def __getitem__(self, path: str) -> bytes:
        target = self.resolve(path)
        if not target.is_file():
            raise KeyError(path)
        return target.read_bytes()

    def __setitem__(self, path: str, data: bytes) -> None:
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get(self, path: str, default: bytes = b"") -> bytes:
        try:
            return self[path]
        except KeyError:
            return default

    def pop(self, path: str, default: bytes | None = None) -> bytes | None:
        try:
            data = self[path]
        except KeyError:
            return default
        self.resolve(path).unlink()
        return data

    def update(self, mapping: Mapping[str, bytes] | _FileStore) -> None:
        source = (
            {path: mapping[path] for path in mapping.keys()}
            if isinstance(mapping, _FileStore)
            else mapping
        )
        for path, data in source.items():
            self[path] = data

    def items(self) -> Iterator[tuple[str, bytes]]:
        for path in self.keys():
            yield path, self[path]

    def rename(self, source: str, destination: str) -> None:
        target = self.resolve(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        # `os.rename` refuses an existing destination on Windows, which is the
        # same answer MTA's fileRename gives everywhere.
        os.rename(self.resolve(source), target)

    def copy(self, source: str, destination: str, *, prefix: int | None = None) -> None:
        target = self.resolve(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        if prefix is None:
            shutil.copyfile(self.resolve(source), target)
            return
        target.write_bytes(self[source][:prefix])

    def keys(self) -> Iterator[str]:
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(self.root).as_posix()
                # Spelt back the way the script wrote it, so a key read out
                # here is a key `resolve` accepts again.
                if relative.startswith("__resource__"):
                    relative = ":" + relative[len("__resource__") :]
                yield relative


class Faults:
    """Failures injected at the MTA API boundary.

    A crash halfway through a backup, a migration, a rotation or a restore is
    not something a test can wish for: it has to arrive as the answer some MTA
    call actually gives when the disk, the process or the power goes. So the
    stubs count their calls and start refusing at the point a test names.
    """

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        #: operation -> how many calls still succeed before it starts failing.
        self._after: dict[str, int] = {}
        #: how many bytes `fileCopy` writes before it gives up, if told to.
        self.copy_prefix: int | None = None
        #: (substring, remaining successes) for `dbQuery`.
        self._sql: list[tuple[str, int]] = []

    def fail_after(self, operation: str, successes: int = 0) -> None:
        """Let `successes` more calls through, then fail this one and all after."""
        self._after[operation] = successes

    def fail_sql_after(self, contains: str, successes: int = 0) -> None:
        self._sql.append((contains, successes))

    def partial_copy(self, prefix_bytes: int, *, successes: int = 0) -> None:
        """Copy only the first bytes and report failure, as a full disk does."""
        self.copy_prefix = prefix_bytes
        self.fail_after("fileCopy", successes)

    def trips(self, operation: str) -> bool:
        self.calls[operation] += 1
        remaining = self._after.get(operation)
        if remaining is None:
            return False
        if remaining > 0:
            self._after[operation] = remaining - 1
            return False
        return True

    def sql_trips(self, statement: str) -> bool:
        for index, (contains, remaining) in enumerate(self._sql):
            if contains not in statement:
                continue
            if remaining > 0:
                self._sql[index] = (contains, remaining - 1)
                return False
            return True
        return False


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


class _ScriptFile:
    """Stands in for the element `fileOpen`/`fileCreate` returns.

    MTA opens `rb` (read-only), `rb+` (read-write) or `wb+` (create), so the
    write pointer starts at 0 on an opened file and a write overlays existing
    bytes rather than appending.
    """

    def __init__(self, store: dict[str, bytes], path: str, *, read_only: bool):
        self.store = store
        self.path = path
        self.read_only = read_only
        self.position = 0
        self.closed = False


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


@dataclass
class _Resource:
    """One resource as `getResources` reports it.

    `state` is what `getResourceState` answers, because that is what a script
    has to check before it may call into another resource: `exports.name:m()`
    on a resource that is not running is a script error, not `false`.
    """

    name: str
    table: Any
    root: Any
    state: str = "running"


@dataclass
class Widget:
    """One CEGUI control, with the text the resource actually wrote into it.

    MTA's grid list indexes rows from 0 and columns from 1
    (`CLuaGUIDefs::GUIGridListAddRow` / `AddColumn`), and reports no selection
    as `-1`, so tests that read a row back read the same numbers the resource
    passed in.
    """

    kind: str
    text: str = ""
    #: Index of the owning control, so destroying a window takes its children
    #: with it the way CEGUI does. Lupa hands out a fresh wrapper per crossing,
    #: so the handle's Python identity is not something to key on.
    parent: int | None = None
    #: Where the control was created, and where dragging it leaves it. Only a
    #: window is ever moved, but every control carries the pair so the position
    #: calls do not have to care which kind they were handed.
    x: float = 0.0
    y: float = 0.0
    #: The Lua handle this widget was created as, so a test that found a control
    #: by its text has something it can click.
    handle: Any = None
    enabled: bool = True
    selected: bool = False
    masked: bool = False
    destroyed: bool = False
    columns: list[str] = field(default_factory=list)
    rows: list[dict[int, str]] = field(default_factory=list)
    selected_row: int = -1
    selected_column: int = -1
    #: Absolute geometry, as the resource passed it. A control created inside a
    #: window carries the coordinates relative to that window, the way CEGUI
    #: reads them back.
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    #: `guiWindowSetMovable` / `guiWindowSetSizable`. CEGUI's FrameWindow ships
    #: with both enabled (`CGUIWindow_Impl`), so that is what they start as.
    movable: bool = True
    sizable: bool = True


class MtaSandbox:
    """A Lua 5.1 environment with MTA's server API stubbed out."""

    def __init__(self, *, database_path: str = IN_MEMORY) -> None:
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.recorder = Recorder()
        self.database_path = database_path
        #: Milliseconds a test has pushed the tick clock forward by hand.
        self._tick_offset = 0
        self._tick_origin = time.perf_counter()
        #: The last tick handed out, so the clock never goes backwards or
        #: repeats -- MTA's is a millisecond counter, and two calls inside
        #: one millisecond must still be distinguishable.
        self._tick_floor = 0
        #: Wall clock `getRealTime` reports, which tests move a day at a time.
        self._real_time = float(time.time())
        self._connections: list[_Connection] = []
        self._elements: set[int] = set()
        self._handlers: dict[str, list[Any]] = {}
        #: Handlers attached to one control, as `(widget index, handler)`.
        self._gui_handlers: dict[str, list[tuple[int, Any]]] = {}
        self._exports: dict[str, Any] = {}
        #: Every resource `getResources` reports, by name, in registration
        #: order. `ankigta` is registered while the globals are installed.
        self._resources: dict[str, _Resource] = {}
        #: Which map the stock Map Editor has open, and the dimension it works
        #: in — what `editor_main` answers when it is running. Deleted elements
        #: are parked in `working dimension + 1`, which is why a test needs to
        #: be able to say what that dimension is.
        self.editor_map_name: str | None = None
        self.editor_working_dimension: int | None = None
        #: What `getZoneName` reports for any position.
        self.zone_name = "Ganton"
        # The resource directory. A caller that named a database file gets that
        # file's directory, so `ankigta.sqlite` resolves to the path it passed.
        self._owned_directory: tempfile.TemporaryDirectory[str] | None = None
        if database_path == IN_MEMORY:
            self._owned_directory = tempfile.TemporaryDirectory(prefix="ankigta-")
            root = Path(self._owned_directory.name)
        else:
            root = Path(database_path).resolve().parent
        #: Resource files, keyed by the path the script passes to fileOpen.
        self.files = _FileStore(root)
        #: Every path `xmlLoadFile` was asked for, in call order. A document
        #: parsed once per entity and a document parsed once look identical
        #: from their answers, and only differ here.
        self.xml_loads: list[str] = []
        #: Parsed nodes, so a Lua handle can index back to its element.
        self._xml_nodes: list[ElementTree.Element] = []
        #: Failures to inject at the MTA API boundary.
        self.faults = Faults()
        #: When set, `fileCreate` fails the way a read-only directory makes it.
        self.file_writes_fail = False
        # Client-side observable state, for tests to assert against.
        self.controls: dict[str, bool] = {}
        #: What this resource has asked for, and what everyone has asked for.
        #: Separate because MTA keeps them separate, and the difference is the
        #: whole reason two windows can strand a cursor on screen.
        self._cursor_wanted_here = False
        self._cursor_requests = 0
        self.camera_target: Any = None
        #: What `CModelNames` holds: object models, and nothing else. Peds and
        #: vehicles are absent from it in MTA, which is the whole point.
        self.model_names: dict[int, str] = {1337: "gate_model"}
        #: Warnings MTA's script debugging would have logged. A stub that
        #: answered silently would hide the call that produced them.
        self.script_warnings: list[str] = []
        self.camera_matrix: tuple[float, ...] = (0.0, 0.0, 10.0, 0.0, 0.0, 0.0)
        self.camera_interior = 0
        self.radio_channel = 0
        self.bound_keys: dict[tuple[str, str], list[Any]] = {}
        self.commands: dict[str, list[Any]] = {}
        self.chat: list[str] = []
        self.acl_rights: dict[str, bool] = {}
        self.browsers: list[Any] = []
        self.loaded_urls: list[str] = []
        self.requested_domains: list[str] = []
        self.browser_available = True
        self.browser_volume = 1.0
        self.world_sound_enabled = True
        self.damage_proof: dict[str, bool] = {}
        self.frozen: dict[str, bool] = {}
        self.occupied_vehicle: Any = False
        #: seat index -> occupant, exactly as MTA reports it (0 is the driver).
        self.vehicle_occupants: dict[int, Any] = {}
        self.moved: list[dict[str, Any]] = []
        self.world_elements: list[Any] = []
        #: Where the client-side player is, what world context they are in, and
        #: how fast they are moving. Velocity is in GTA's own units per physics
        #: step, which is what `getElementVelocity` reports.
        self.player_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.player_interior = 0
        self.player_dimension = 0
        self.player_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.blips: list[Any] = []
        #: Every control the resource created, in creation order.
        self.widgets: list[Widget] = []
        #: What `getLocalization()` reports, as MTA's `{code, name}`.
        self.localization = {"code": "en-US", "name": "English"}
        #: Every string handed to `dxDrawText`, in draw order.
        self.drawn_text: list[str] = []
        #: Every script Lua asked the panel page to run, in order.
        self.browser_javascript: list[str] = []
        #: Names passed to `addEvent`. MTA calls no handler for anything else.
        self._added_events: set[str] = set()
        #: Cursor position as MTA reports it: a fraction of the screen.
        self.cursor_position: tuple[float, float] = (0.5, 0.5)
        #: Which keys are held, for the loops that watch a button rather than
        #: waiting for an event that may land outside the page.
        self.key_states: dict[str, bool] = {}
        #: The same strings with the box they were drawn into, for the surfaces
        #: that have no CEGUI control to read geometry off.
        self.drawn_text_boxes: list[dict[str, Any]] = []
        self.drawn_rectangles: list[dict[str, float]] = []
        self.drawn_images: list[dict[str, float]] = []
        #: What `guiGetScreenSize()` reports. Tests move it to run the same
        #: layout at 1280x720, 1920x1080 and 3840x2160.
        self.screen_width = 1920.0
        self.screen_height = 1080.0
        self.position_read_fails = False
        self.vanish_after_position_read: Any = None
        self._install_globals()

    # ---------------------------------------------------------------- loading

    def load(self, relative_path: str, *, root: Path | None = None) -> None:
        """Load a resource script, e.g. `server/store.lua`.

        `root` names a different copy of the resource to load it from, which is
        how the certification suite runs the unpacked artifact rather than the
        working tree it was built from.
        """
        path = (root or RESOURCE_ROOT) / relative_path
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
        """Move the tick clock forward without firing timers."""
        self._tick_offset += milliseconds

    def advance_days(self, days: float) -> None:
        """Move the wall clock `getRealTime` reports, leaving ticks alone."""
        self._real_time += days * 86400.0

    @property
    def real_time(self) -> float:
        return self._real_time

    @real_time.setter
    def real_time(self, value: float) -> None:
        self._real_time = float(value)

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
                self._tick_offset += timer.interval_ms
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

    def trigger(
        self,
        event: str,
        source: Any = None,
        *args: Any,
        client: Any = None,
    ) -> None:
        """Invoke every handler registered for an event.

        MTA exposes the event's source as a global during dispatch, and handlers
        legitimately branch on it, so set it the same way. For an event a player
        triggered with `triggerServerEvent` it also sets `client` to that
        player, and leaves it nil otherwise -- server code checks that global to
        tell a remote request from a local one.
        """
        for handler in self._handlers.get(event, []):
            self._dispatch(handler, source, args, client)

    def _dispatch(
        self,
        handler: Any,
        source: Any,
        args: tuple[Any, ...],
        client: Any = None,
    ) -> None:
        g = self.lua.globals()
        previous_source, previous_client = g.source, g.client
        g.source = source
        g.client = client
        try:
            handler(*args)
        finally:
            g.source = previous_source
            g.client = previous_client

    def handlers(self, event: str) -> list[Any]:
        """Handlers attached to something other than one control.

        A handler hung on a control is not here: MTA calls it only for that
        control, so it is dispatched through `click_widget` instead.
        """
        return list(self._handlers.get(event, []))

    def widget_named(self, text: str, kind: str = "button") -> Any:
        """The one live control of this kind showing this text, or `None`.

        Tests use it to find a control the way a player would -- by reading the
        screen -- rather than by reaching into the module that drew it.
        """
        found = [
            widget
            for widget in self.widgets
            if widget.kind == kind
            and widget.text == text
            and not widget.destroyed
        ]
        if len(found) != 1:
            return None
        return found[0].handle

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
            connection = _Connection(self.database_file(str(path)))
            self._connections.append(connection)
            self._elements.add(id(connection))
            return connection

        def db_query(connection: Any, statement: str, *params: Any) -> Any:
            if not isinstance(connection, _Connection) or connection.destroyed:
                return False
            if self.faults.sql_trips(str(statement)):
                # SQLITE_IOERR is what a disk that stopped answering produces.
                return _QueryHandle(None, 0, 0, (10, "disk I/O error"))
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
            # `localPlayer` is a CClientPlayer and so always an element. It
            # crosses this boundary as a string sentinel rather than a table,
            # and lupa hands out a fresh Python string each time, so it is
            # recognized by value rather than by identity.
            if value == LOCAL_PLAYER:
                return True
            return id(value) in self._elements

        def destroy_element(value: Any) -> bool:
            if isinstance(value, _Connection):
                value.close()
                self._elements.discard(id(value))
                return True
            if lua_type(value) == "table" and value["__element"] is True:
                value["__destroyed"] = True
                index = value["__widget"]
                if index is not None:
                    self._destroy_widget(int(index))
                return True
            if id(value) in self._elements:
                self._elements.discard(id(value))
                return True
            return False

        # --- accounts and rights --------------------------------------------
        # MTA always hands back an account element; an unlogged player gets the
        # guest one, so `false` is not an answer this function gives.
        def get_player_account(player: Any = None) -> Any:
            # Keyed inside the Lua table: lupa hands out a fresh wrapper object
            # per crossing, so the Python identity of an element is not stable.
            if lua_type(player) == "table" and player["__account"] is not None:
                return player["__account"]
            return self.lua.table_from(
                {"__element": True, "type": "account", "guest": True}
            )

        g.getPlayerAccount = get_player_account
        g.isGuestAccount = lambda account=None: (
            lua_type(account) != "table" or account["guest"] is True
        )
        g.hasObjectPermissionTo = lambda _object, right, default=False: (
            self.acl_rights.get(str(right), default is True)
        )

        g.isElement = is_element
        g.destroyElement = destroy_element
        g.getElementByID = lambda element_id, *_rest: next(
            (
                element
                for element in self.world_elements
                if lua_type(element) == "table"
                and (element["__id"] or element["id"]) == str(element_id)
            ),
            False,
        )

        # --- crypto and serialisation --------------------------------------
        def sha256(data: str) -> str:
            return hashlib.sha256(str(data).encode("utf-8")).hexdigest().upper()

        def to_json(value: Any, _compact: Any = None, *_rest: Any) -> str:
            # MTA serialises its *argument list*, so one table comes out
            # wrapped: `toJSON({a = 1})` is `[{"a":1}]`, not `{"a":1}`. A
            # double that returns the bare object is how the panel shipped
            # pushing `[state]` into a page that reads `state` -- green suite,
            # blank window. See the test-double rule in
            # docs/design/remaining-work-plan.md.
            return json.dumps([self._from_lua(value)], ensure_ascii=False)

        def from_json(text: str) -> Any:
            try:
                decoded = json.loads(text)
            except (TypeError, ValueError):
                return False
            # The other half of the argument-list symmetry: `toJSON` packs its
            # arguments into a list and `fromJSON` unpacks them again, one Lua
            # return value each. Every consumer here assigns to a single name,
            # which takes the first -- so a top-level list yields its head, and
            # `toJSON` round-trips back to the table that went in. An object,
            # such as a payload from `JSON.stringify` on the page, is not a
            # list and passes through untouched.
            if isinstance(decoded, list):
                decoded = decoded[0] if decoded else None
            return self._to_lua(decoded)

        def mta_hash(algorithm: str, data: str, *_rest: Any) -> Any:
            # `hash()` lowercases its hex (CLuaCryptDefs::Hash), where the older
            # `sha256()` uppercases it. Getting this backwards would silently
            # break every digest comparison in the connection config.
            try:
                digest = hashlib.new(str(algorithm).replace("-", ""))
            except ValueError:
                return False
            digest.update(str(data).encode("utf-8"))
            return digest.hexdigest().lower()

        g.sha256 = sha256
        g.hash = mta_hash
        g.toJSON = to_json
        g.fromJSON = from_json

        # --- runtime --------------------------------------------------------
        def get_tick_count() -> int:
            # Real elapsed milliseconds plus whatever a test pushed it by.
            # A counter that only ever adds one per call reads like a clock and
            # is not one: code that times its own work with it -- which the F7
            # snapshot and the Card Picker both now do -- would report the
            # number of calls it made rather than how long it took, and the
            # instrumentation would be untestable here.
            elapsed = int((time.perf_counter() - self._tick_origin) * 1000)
            value = elapsed + self._tick_offset
            if value <= self._tick_floor:
                value = self._tick_floor + 1
            self._tick_floor = value
            return value

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

        def get_real_time(seconds: Any = None, _local: Any = True) -> Any:
            # `month` is 0-11 and `year` is years since 1900, straight out of
            # `tm`. Anything keying a calendar day off this has to say so.
            moment = time.localtime(
                float(seconds) if seconds is not None else self._real_time
            )
            return self.lua.table_from(
                {
                    "second": moment.tm_sec,
                    "minute": moment.tm_min,
                    "hour": moment.tm_hour,
                    "monthday": moment.tm_mday,
                    "month": moment.tm_mon - 1,
                    "year": moment.tm_year - 1900,
                    "weekday": moment.tm_wday,
                    "yearday": moment.tm_yday,
                    "isdst": 1 if moment.tm_isdst > 0 else 0,
                    "timestamp": float(
                        seconds if seconds is not None else self._real_time
                    ),
                }
            )

        g.getTickCount = get_tick_count
        g.getRealTime = get_real_time
        g.outputDebugString = output_debug_string
        g.setTimer = set_timer
        g.killTimer = kill_timer
        g.isTimer = is_timer

        # --- events ---------------------------------------------------------
        def add_event(name: str, _remote: Any = None) -> bool:
            self._added_events.add(str(name))
            return True

        def add_event_handler(
            name: str,
            attached_to: Any,
            handler: Any,
            *_rest: Any,
        ) -> bool:
            # A handler attached to a control is kept apart from the rest.
            # MTA calls it only for that control (`CClientGUIElement::
            # CallEvent`), so putting it in the by-name list would have every
            # window's buttons answer another window's click.
            index = (
                attached_to["__widget"]
                if lua_type(attached_to) == "table"
                else None
            )
            if index is not None:
                self._gui_handlers.setdefault(str(name), []).append(
                    (int(index), handler)
                )
                return True
            self._handlers.setdefault(str(name), []).append(handler)
            return True

        def trigger_event(name: str, source: Any = None, *args: Any) -> bool:
            self.recorder.local_events.append(
                TriggeredEvent(str(name), source, tuple(args))
            )
            # `CStaticFunctionDefinitions::TriggerEvent` is
            # `if (m_pEvents->Exists(szName))` and nothing else: a name nobody
            # passed to `addEvent` calls no handler and returns false, without
            # a word in the log. Handlers alone are not registration, and a
            # double that dispatches on a handler is how `pickEntityStart`
            # shipped handled-but-unregistered -- the button closed the panel
            # and then did nothing.
            if not self._is_registered_event(str(name)):
                return False
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
        # Kept for `add_world_element`, which parents what it builds here
        # so the ownership walk finds a resource that owns it.
        self._resource_root = resource_root
        g.root = self.lua.table_from({"type": "root"})
        self._resources["ankigta"] = _Resource(
            name="ankigta", table=resource, root=resource_root, state="running"
        )
        g.getThisResource = lambda: resource

        def resource_named(name: Any) -> _Resource | None:
            return self._resources.get(str(name))

        def resource_of(handle: Any) -> _Resource | None:
            if lua_type(handle) != "table" or not handle["name"]:
                return None
            return resource_named(handle["name"])

        g.getResourceName = lambda handle=None: (
            str(handle["name"])
            if lua_type(handle) == "table" and handle["name"]
            else "ankigta"
        )
        g.getResourceFromName = lambda name=None: (
            resource_named(name).table if resource_named(name) else False
        )
        g.getResourceState = lambda handle=None: (
            resource_of(handle).state if resource_of(handle) else False
        )
        g.getResourceInfo = lambda handle=None, key="": (
            handle[str(key)]
            if lua_type(handle) == "table" and handle[str(key)] is not None
            else False
        )
        g.getResources = lambda: self.lua.table_from(
            [entry.table for entry in self._resources.values()]
        )
        g.getResourceRootElement = lambda handle=None: (
            resource_of(handle).root if resource_of(handle) else resource_root
        )
        self._install_export_globals()

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

        # XML, over the same files `fileOpen` reads, so a fixture map is one
        # document to both APIs. A path with nothing behind it still answers
        # `false`, which is what MTA returns for a map file that is not there.
        def xml_load_file(path: str = "", _readonly: Any = None) -> Any:
            self.xml_loads.append(str(path))
            try:
                data = self.files[str(path)]
            except KeyError:
                return False
            try:
                root = ElementTree.fromstring(data.decode("utf-8"))
            except ElementTree.ParseError:
                return False
            return self._xml_node(root)

        def xml_node_get_children(node: Any = None, index: Any = None) -> Any:
            element = self._xml_element(node)
            if element is None:
                return False
            children = list(element)
            if index is not None:
                # MTA's second argument picks one child, zero-based.
                position = int(index)
                if not 0 <= position < len(children):
                    return False
                return self._xml_node(children[position])
            return self.lua.table_from(
                [self._xml_node(child) for child in children]
            )

        def xml_node_get_name(node: Any = None) -> Any:
            element = self._xml_element(node)
            return element.tag if element is not None else False

        def xml_node_get_attribute(node: Any = None, name: str = "") -> Any:
            element = self._xml_element(node)
            if element is None:
                return False
            # MTA answers `false` for an attribute that is not set.
            return element.get(str(name), False)

        g.xmlLoadFile = xml_load_file
        g.xmlUnloadFile = lambda _node=None: True
        g.xmlNodeGetChildren = xml_node_get_children
        g.xmlNodeGetName = xml_node_get_name
        g.xmlNodeGetAttribute = xml_node_get_attribute

        self._install_file_globals(g)
        self._install_client_globals(g)

    def _install_export_globals(self) -> None:
        """Install the small public surface ANKIGTA uses from other resources.

        Lua's ``resource:method(value)`` call passes the resource table as the
        first argument.  Keeping that convention here matters: a Python double
        that accepts only ``value`` makes every real colon call observe the
        export table instead of the element it was given.
        """
        g = self.lua.globals()

        def export_argument(args: tuple[Any, ...], index: int) -> Any:
            return args[index + 1] if len(args) > index + 1 else None

        def edf_is_representation(*args: Any) -> bool:
            element = export_argument(args, 0)
            return (
                lua_type(element) == "table"
                and element["__edf_representation"] is True
            )

        def edf_set_element_property(*args: Any) -> bool:
            element = export_argument(args, 0)
            key = export_argument(args, 1)
            value = export_argument(args, 2)
            if lua_type(element) != "table" or key is None:
                return False
            element[str(key)] = value
            return True

        def edf_create_element(*args: Any) -> Any:
            kind = export_argument(args, 0)
            properties = export_argument(args, 3)
            if not isinstance(kind, str) or not kind:
                return False
            element = self.lua.table_from(
                {"__element": True, "type": kind, "__parent": False}
            )
            if lua_type(properties) == "table":
                for key in properties.keys():
                    element[str(key)] = properties[key]
            self.world_elements.append(element)
            return element

        def editor_current_map(*_args: Any) -> Any:
            return self.editor_map_name or False

        def editor_working_dimension(*_args: Any) -> Any:
            if self.editor_working_dimension is None:
                return False
            return self.editor_working_dimension

        edf = self.lua.table_from(
            {
                "edfIsRepresentation": edf_is_representation,
                "edfSetElementProperty": edf_set_element_property,
                "edfCreateElement": edf_create_element,
            }
        )
        editor_main = self.lua.table_from(
            {
                "getCurrentMapName": editor_current_map,
                "getWorkingDimension": editor_working_dimension,
                "getSelectedElement": lambda *_args: False,
                "import": lambda *_args: True,
            }
        )
        g.exports = self.lua.table_from(
            {"edf": edf, "editor_main": editor_main}
        )

    def _xml_node(self, element: ElementTree.Element) -> Any:
        """A Lua handle for one parsed XML element.

        Kept as an index rather than as the element itself, because lupa hands
        out a fresh wrapper per crossing and the identity of a Python object
        that went through Lua is not something to key on.
        """
        self._xml_nodes.append(element)
        return self.lua.table_from(
            {
                "__element": True,
                "type": "xml-node",
                "__xml": len(self._xml_nodes) - 1,
            }
        )

    def _xml_element(self, node: Any) -> ElementTree.Element | None:
        if lua_type(node) != "table":
            return None
        index = node["__xml"]
        if index is None:
            return None
        return self._xml_nodes[int(index)]

    def write_map_file(self, virtual_path: str, entities: Mapping[str, str]) -> None:
        """Write a saved map the way the Map Editor leaves one.

        `entities` maps an `ankigtaEntityId` to the element type it was saved
        as. The map's own identity element is written from the path's map id,
        which the caller passes as the `ankigta_map_identity` key.
        """
        parts = [
            f'  <{kind} ankigtaEntityId="{entity_id}" />'
            if kind != "ankigta_map_identity"
            else f'  <ankigta_map_identity ankigtaMapId="{entity_id}" />'
            for entity_id, kind in entities.items()
        ]
        self.files[virtual_path] = (
            "<map>\n" + "\n".join(parts) + "\n</map>\n"
        ).encode("utf-8")

    def database_file(self, path: str) -> str:
        """Where `dbConnect("sqlite", path)` actually opens.

        A sandbox told to stay in memory keeps every connection in memory, the
        way it always did. One given a real database file resolves every path
        inside that file's directory, so a backup the file API wrote is the
        same file SQLite then opens.
        """
        if self.database_path == IN_MEMORY:
            return IN_MEMORY
        target = self.files.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        return str(target)

    def _install_file_globals(self, g: Any) -> None:
        """The resource file API, backed by `self.files`.

        Paths are resource-relative exactly as the scripts write them, so a
        client-private `@name` and a server-side `name` stay distinct keys.
        """

        def file_exists(path: str) -> bool:
            return str(path) in self.files

        def file_open(path: str, read_only: Any = False) -> Any:
            # `rb`/`rb+`: opening a file that is not there fails.
            if str(path) not in self.files:
                return False
            return _ScriptFile(self.files, str(path), read_only=read_only is True)

        def file_create(path: str) -> Any:
            if self.file_writes_fail or self.faults.trips("fileCreate"):
                # MTA returns false when the file cannot be created -- a
                # read-only directory, or a name the client refuses.
                return False
            # `wb+`: creates, or truncates what was there.
            self.files[str(path)] = b""
            return _ScriptFile(self.files, str(path), read_only=False)

        def file_copy(source: str, destination: str, overwrite: Any = False) -> bool:
            # "Source file doesn't exist", then "Destination file already
            # exists" unless overwrite was asked for.
            if str(source) not in self.files:
                return False
            if str(destination) in self.files and overwrite is not True:
                return False
            if self.faults.trips("fileCopy"):
                if self.faults.copy_prefix is not None:
                    # A copy that stopped partway leaves what it had written.
                    self.files.copy(
                        str(source),
                        str(destination),
                        prefix=self.faults.copy_prefix,
                    )
                return False
            self.files.copy(str(source), str(destination))
            return True

        def file_read(handle: Any, count: float) -> Any:
            if not isinstance(handle, _ScriptFile) or handle.closed:
                return None
            data = handle.store.get(handle.path, b"")
            chunk = data[handle.position : handle.position + int(count)]
            handle.position += len(chunk)
            return chunk.decode("utf-8", errors="surrogateescape")

        def file_write(handle: Any, *parts: Any) -> Any:
            if not isinstance(handle, _ScriptFile) or handle.closed:
                return False
            if handle.read_only:
                return False
            if self.faults.trips("fileWrite"):
                return False
            written = 0
            data = bytearray(handle.store.get(handle.path, b""))
            for part in parts:
                encoded = str(part).encode("utf-8", errors="surrogateescape")
                end = handle.position + len(encoded)
                if end > len(data):
                    data.extend(b"\0" * (end - len(data)))
                data[handle.position : end] = encoded
                handle.position = end
                written += len(encoded)
            handle.store[handle.path] = bytes(data)
            return written

        def file_get_size(handle: Any) -> Any:
            if not isinstance(handle, _ScriptFile) or handle.closed:
                return False
            return len(handle.store.get(handle.path, b""))

        def file_close(handle: Any) -> bool:
            if not isinstance(handle, _ScriptFile) or handle.closed:
                return False
            handle.closed = True
            return True

        def file_delete(path: str) -> bool:
            if self.faults.trips("fileDelete"):
                return False
            return self.files.pop(str(path), None) is not None

        def file_rename(source: str, destination: str) -> bool:
            # "fileRename failed; destination file already exists".
            if str(source) not in self.files or str(destination) in self.files:
                return False
            if self.faults.trips("fileRename"):
                return False
            self.files.rename(str(source), str(destination))
            return True

        g.fileExists = file_exists
        g.fileOpen = file_open
        g.fileCreate = file_create
        g.fileCopy = file_copy
        g.fileRead = file_read
        g.fileWrite = file_write
        g.fileGetSize = file_get_size
        g.fileClose = file_close
        g.fileFlush = lambda handle=None: isinstance(handle, _ScriptFile)
        g.fileDelete = file_delete
        g.fileRename = file_rename

    def add_study_player(self, *, right: str = "resource.ankigta.study") -> Any:
        """A logged-in player holding the study right, as the resource expects."""
        player = self.lua.table_from(
            {
                "__element": True,
                "type": "player",
                "name": "study-player",
                "interior": 0,
                "dimension": 0,
            }
        )
        player["__account"] = self.lua.table_from(
            {"__element": True, "type": "account", "guest": False}
        )
        self.world_elements.append(player)
        self.acl_rights[right] = True
        return player

    def add_world_element(
        self,
        kind: str = "object",
        *,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        interior: int = 0,
        dimension: int = 0,
        streamed: bool = True,
        map_id: str = "",
        model: int = 1337,
        **element_data: Any,
    ) -> Any:
        """A Map Editor-created element the client can find and read.

        Element data is set the way EDF sets it, so a lookup by
        `ankigtaEntityId` finds the same thing the resource would find.
        """
        element = self.lua.table_from(
            {
                "__element": True,
                "__streamed": streamed,
                # The `id` a `.map` file gave it, which `getElementID` returns.
                "__id": str(map_id or ""),
                "__parent": getattr(self, "_resource_root", None) or False,
                "type": kind,
                "x": float(x),
                "y": float(y),
                "z": float(z),
                "rotX": 0,
                "rotY": 0,
                "rotZ": 0,
                "model": int(model),
                "interior": int(interior),
                "dimension": int(dimension),
            }
        )
        for key, value in element_data.items():
            element[key] = value
        self.world_elements.append(element)
        self._elements.add(id(element))
        return element

    def to_python(self, value: Any) -> Any:
        """Convert a Lua value the scripts produced into plain Python.

        Useful for handing one side's real payload to the other side, instead
        of writing a second guess at its shape.
        """
        return self._from_lua(value)

    def write_file(self, path: str, contents: str) -> None:
        """Seed a resource file, as the companion add-on would publish one."""
        self.files[path] = contents.encode("utf-8")

    def read_file(self, path: str) -> str:
        return self.files[path].decode("utf-8")

    def _install_client_globals(self, g: Any) -> None:
        """Client-side surface: input, drawing and the CEF browser."""

        # --- input state ----------------------------------------------------
        def toggle_control(control: str, enabled: Any = True) -> bool:
            self.controls[str(control)] = enabled is True
            return True

        def is_control_enabled(control: str) -> bool:
            return self.controls.get(str(control), True)

        def show_cursor(visible: Any = True, *_rest: Any) -> bool:
            # `CResource::ShowCursor` keeps a per-resource flag and a *shared*
            # count -- `static int m_iShowingCursor` -- and the cursor is on
            # while the count is above zero. A double that stores one boolean
            # cannot see the bug that costs: read `isCursorShowing()` on the
            # way in, hand it back on the way out, and this resource never lets
            # go while another one is holding it.
            wanted = visible is True
            if wanted != self._cursor_wanted_here:
                self._cursor_requests += 1 if wanted else -1
                self._cursor_wanted_here = wanted
            return True

        g.toggleControl = toggle_control
        g.isControlEnabled = is_control_enabled
        g.showCursor = show_cursor
        g.isCursorShowing = lambda: self.cursor_visible
        g.getCursorPosition = lambda: (
            self.cursor_position if self.cursor_visible else (False, False)
        )
        g.getKeyState = lambda key: self.key_states.get(str(key), False)
        g.bindKey = lambda key, state, handler, *_rest: self.bound_keys.setdefault(
            (str(key), str(state)), []
        ).append(handler) or True
        g.unbindKey = lambda key, state=None, handler=None: True
        g.addCommandHandler = lambda name, handler, *_rest: (
            self.commands.setdefault(str(name), []).append(handler) or True
        )
        g.outputChatBox = lambda message, *_rest: (
            self.chat.append(str(message)) or True
        )

        # --- model names -----------------------------------------------------
        def engine_get_model_name_from_id(model: Any = None, *_rest: Any) -> Any:
            # `CLuaEngineDefs::EngineGetModelNameFromID` looks the id up in
            # `CModelNames` and, finding nothing, answers `false` *and* logs
            # "Expected valid model ID" rather than raising. A double that
            # answered `false` quietly would hide the caller that asked about a
            # ped -- which is the defect this exists to catch.
            try:
                key = int(model)
            except (TypeError, ValueError):
                key = None
            name = self.model_names.get(key) if key is not None else None
            if not name:
                self.script_warnings.append(
                    "Bad usage @ 'engineGetModelNameFromID' "
                    "[Expected valid model ID at argument 1]"
                )
                return False
            return name

        g.engineGetModelNameFromID = engine_get_model_name_from_id

        # --- camera, radio ---------------------------------------------------
        g.getCameraTarget = lambda *_args: self.camera_target
        g.setCameraTarget = lambda target, *_rest: (
            setattr(self, "camera_target", target) or True
        )
        g.getCameraMatrix = lambda *_args: self.camera_matrix
        g.setCameraMatrix = lambda *values: (
            setattr(self, "camera_matrix", tuple(float(value) for value in values))
            or True
        )
        g.getCameraInterior = lambda *_args: self.camera_interior
        g.setCameraInterior = lambda value, *_rest: (
            setattr(self, "camera_interior", int(value)) or True
        )
        g.getRadioChannel = lambda: self.radio_channel
        g.setRadioChannel = lambda channel: (
            setattr(self, "radio_channel", int(channel)) or True
        )

        # --- drawing ---------------------------------------------------------
        g.guiGetScreenSize = lambda: (
            float(self.screen_width),
            float(self.screen_height),
        )

        def dx_draw_rectangle(
            x: float = 0,
            y: float = 0,
            width: float = 0,
            height: float = 0,
            *_rest: Any,
            **_kwargs: Any,
        ) -> bool:
            self.drawn_rectangles.append(
                {
                    "x": float(x),
                    "y": float(y),
                    "width": float(width),
                    "height": float(height),
                }
            )
            return True

        g.dxDrawRectangle = dx_draw_rectangle

        def dx_draw_text(
            text: Any = "",
            left: float = 0,
            top: float = 0,
            right: float = 0,
            bottom: float = 0,
            _color: Any = None,
            scale: float = 1,
            *_rest: Any,
            **_kwargs: Any,
        ) -> bool:
            self.drawn_text.append(str(text))
            self.drawn_text_boxes.append(
                {
                    "text": str(text),
                    "left": float(left),
                    "top": float(top),
                    "right": float(right),
                    "bottom": float(bottom),
                    "scale": float(scale),
                }
            )
            return True

        g.dxDrawText = dx_draw_text

        def dx_draw_image(
            x: float = 0,
            y: float = 0,
            width: float = 0,
            height: float = 0,
            *_rest: Any,
            **_kwargs: Any,
        ) -> bool:
            self.drawn_images.append(
                {
                    "x": float(x),
                    "y": float(y),
                    "width": float(width),
                    "height": float(height),
                }
            )
            return True

        g.dxDrawImage = dx_draw_image
        g.getLocalization = lambda: self.lua.table_from(self.localization)
        self._install_gui_globals(g)
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

        def execute_browser_javascript(_browser: Any, code: str) -> bool:
            """Record what Lua asked the page to run.

            The page itself is not executed here. What a test can honestly
            assert is the call the resource made -- the view is HTML, and its
            behaviour is a manual checklist item.
            """
            self.browser_javascript.append(str(code))
            return True

        g.createBrowser = create_browser
        g.executeBrowserJavascript = execute_browser_javascript
        g.isBrowserLoading = lambda _browser=None: False
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

        def set_element_frozen(element: Any, frozen: Any) -> bool:
            key = "vehicle" if lua_type(element) == "table" else "player"
            self.frozen[key] = frozen is True
            return True

        def is_element_frozen(element: Any) -> bool:
            key = "vehicle" if lua_type(element) == "table" else "player"
            return self.frozen.get(key, False)

        g.setElementDamageProof = set_damage_proof
        g.isElementDamageProof = is_damage_proof
        g.setElementFrozen = set_element_frozen
        g.isElementFrozen = is_element_frozen
        g.localPlayer = LOCAL_PLAYER
        g.getPedOccupiedVehicle = lambda _ped=None: self.occupied_vehicle
        # --- world manipulation ---------------------------------------------
        def get_element_position(element: Any) -> Any:
            if self.position_read_fails:
                return False
            if element == LOCAL_PLAYER:
                return self.player_position
            if (
                self.vanish_after_position_read is not None
                and element is not None
                and lua_type(element) == "table"
                and element["type"] == self.vanish_after_position_read["type"]
            ):
                # Simulate the element being destroyed mid-read.
                element["__destroyed"] = True
            if lua_type(element) != "table":
                return False
            return element["x"], element["y"], element["z"]

        def get_element_velocity(element: Any) -> Any:
            # Units per physics step, the way GTA stores it -- see
            # `CTimer::ms_fTimeStep` in `Client/game_sa/CGameSA.cpp`. MTA
            # exposes no speed accessor, so the caller converts.
            if element == LOCAL_PLAYER:
                return self.player_velocity
            if lua_type(element) != "table":
                return False
            return (
                element["vx"] or 0.0,
                element["vy"] or 0.0,
                element["vz"] or 0.0,
            )

        def is_element_streamed_in(element: Any) -> bool:
            if lua_type(element) != "table":
                return False
            return element["__streamed"] is not False

        def set_element_position(element: Any, x: float, y: float, z: float, *_r: Any) -> bool:
            self._record_move(element, position=(float(x), float(y), float(z)))
            return True

        def set_element_interior(element: Any, interior: float, *_rest: Any) -> bool:
            self._record_move(element, interior=int(interior))
            return True

        def set_element_dimension(element: Any, dimension: float) -> bool:
            self._record_move(element, dimension=int(dimension))
            return True

        g.getElementPosition = get_element_position
        g.getElementVelocity = get_element_velocity
        g.getDistanceBetweenPoints3D = (
            lambda x1, y1, z1, x2, y2, z2: (
                (float(x2) - float(x1)) ** 2
                + (float(y2) - float(y1)) ** 2
                + (float(z2) - float(z1)) ** 2
            )
            ** 0.5
        )
        g.isElementStreamedIn = is_element_streamed_in
        g.getElementInterior = lambda e=None: (
            e["interior"]
            if lua_type(e) == "table"
            else (self.player_interior if e == LOCAL_PLAYER else 0)
        )
        g.getElementDimension = lambda e=None: (
            e["dimension"]
            if lua_type(e) == "table"
            else (self.player_dimension if e == LOCAL_PLAYER else 0)
        )
        g.getElementModel = lambda e=None, *_r: (
            e["model"] if lua_type(e) == "table" else 0
        ) or 0
        g.getElementRotation = lambda e=None, *_r: (
            (e["rotX"] or 0, e["rotY"] or 0, e["rotZ"] or 0)
            if lua_type(e) == "table"
            else (0, 0, 0)
        )
        g.getZoneName = lambda *_args: self.zone_name
        g.setElementData = lambda e, key, value, *_r: (
            e.__setitem__(str(key), value) if lua_type(e) == "table" else None
        ) or True
        g.setElementPosition = set_element_position
        g.setElementInterior = set_element_interior
        g.setElementDimension = set_element_dimension
        g.getElementType = lambda e=None: (
            str(e["type"]) if lua_type(e) == "table" and e["type"] else "unknown"
        )
        def get_vehicle_occupants(_vehicle: Any = None) -> Any:
            # MTA keys this by SEAT, starting at 0 (the driver), and skips
            # empty seats -- see CLuaVehicleDefs::GetVehicleOccupants, which
            # loops `for ucSeat = 0; ucSeat <= ucMaxPassengers` and only sets a
            # key when that seat holds a ped. A dense 1-based table is the one
            # shape it never returns, so building one here would let `ipairs`
            # bugs pass.
            table = self.lua.eval("{}")
            for seat, occupant in self.vehicle_occupants.items():
                table[seat] = occupant
            return table

        g.getVehicleOccupants = get_vehicle_occupants
        g.getElementsByType = lambda kind, *_rest: self.lua.table_from(
            [e for e in self.world_elements if str(e["type"]) == str(kind)]
        )
        g.getElementData = lambda element, key, *_rest: (
            element[str(key)] if lua_type(element) == "table" else False
        )
        # The `id` attribute a `.map` file gave the element. MTA fills it when
        # it loads the map, and it is the identity that survives a restart for
        # an object nobody is editing -- unlike `me:ID`, which the stock Map
        # Editor only writes while the map is open in it.
        g.getElementID = lambda element, *_rest: (
            element["__id"] if lua_type(element) == "table" else False
        ) or ""
        g.getElementParent = lambda element, *_rest: (
            element["__parent"] if lua_type(element) == "table" else False
        ) or False
        def create_blip(x: float, y: float, z: float, *_rest: Any) -> Any:
            blip = self.lua.table_from(
                {"__element": True, "type": "blip", "x": x, "y": y, "z": z}
            )
            self.blips.append(blip)
            return blip

        g.createBlip = create_blip
        g.dxDrawMaterialLine3D = lambda *_a, **_k: True
        g.setBrowserVolume = set_browser_volume
        g.setWorldSoundEnabled = set_world_sound_enabled
        g.focusBrowser = lambda _browser=None: True
        g.isBrowserFocused = lambda _browser=None: True
        g.cancelEvent = lambda *_args: True

    def _install_gui_globals(self, g: Any) -> None:
        """CEGUI controls, recorded with the text the resource wrote.

        Only the calls the resource makes are stubbed, and they keep MTA's
        indexing: `guiGridListAddRow` returns a 0-based row, `AddColumn` a
        1-based column, and `guiGridListGetSelectedItem` reports `-1, -1` when
        nothing is selected.
        """

        def parent_index(parent: Any) -> int | None:
            if lua_type(parent) != "table":
                return None
            index = parent["__widget"]
            return None if index is None else int(index)

        def register(
            kind: str,
            text: Any = "",
            parent: Any = None,
            geometry: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
        ) -> Any:
            widget = Widget(
                kind=kind,
                text=str(text),
                parent=parent_index(parent),
                x=float(geometry[0]),
                y=float(geometry[1]),
                width=float(geometry[2]),
                height=float(geometry[3]),
            )
            self.widgets.append(widget)
            handle = self.lua.table_from(
                {
                    "__element": True,
                    "type": "gui-" + kind,
                    "__widget": len(self.widgets) - 1,
                }
            )
            widget.handle = handle
            return handle

        def widget_of(handle: Any) -> Widget | None:
            if lua_type(handle) != "table":
                return None
            index = handle["__widget"]
            if index is None:
                return None
            return self.widgets[int(index)]

        def create_window(
            x: float, y: float, w: float, h: float,
            title: Any = "", _relative: Any = False, parent: Any = None,
        ) -> Any:
            return register("window", title, parent, (x, y, w, h))

        def create_label(
            x: float, y: float, w: float, h: float,
            text: Any = "", _relative: Any = False, parent: Any = None,
        ) -> Any:
            return register("label", text, parent, (x, y, w, h))

        def create_button(
            x: float, y: float, w: float, h: float,
            text: Any = "", _relative: Any = False, parent: Any = None,
        ) -> Any:
            return register("button", text, parent, (x, y, w, h))

        def create_edit(
            x: float, y: float, w: float, h: float,
            text: Any = "", _relative: Any = False, parent: Any = None,
        ) -> Any:
            return register("edit", text, parent, (x, y, w, h))

        def create_check_box(
            x: float, y: float, w: float, h: float,
            text: Any = "", selected: Any = False,
            _relative: Any = False, parent: Any = None,
        ) -> Any:
            handle = register("checkbox", text, parent, (x, y, w, h))
            widget = widget_of(handle)
            if widget is not None:
                widget.selected = selected is True
            return handle

        def create_grid_list(
            x: float, y: float, w: float, h: float,
            _relative: Any = False, parent: Any = None,
        ) -> Any:
            return register("gridlist", "", parent, (x, y, w, h))

        def create_gui_browser(
            x: float, y: float, w: float, h: float,
            is_local: Any = False, transparent: Any = False,
            _relative: Any = False, parent: Any = None,
        ) -> Any:
            """`guiCreateBrowser` wraps a browser in a GUI element.

            Only a local browser has its `window.mta` bridge honoured by the
            browser process (prototype 0006), so `isLocal` is recorded rather
            than ignored: a panel created remote would look identical here and
            be dead in the game.
            """
            if not self.browser_available:
                return False
            handle = register("browser", "", parent, (x, y, w, h))
            browser = self.lua.table_from(
                {
                    "__element": True,
                    "type": "browser",
                    "width": float(w),
                    "height": float(h),
                    "isLocal": is_local is True,
                    "transparent": transparent is True,
                }
            )
            self.browsers.append(browser)
            handle["__browser"] = browser
            return handle

        def get_gui_browser(handle: Any) -> Any:
            if lua_type(handle) != "table":
                return False
            return handle["__browser"] or False

        def set_position(
            handle: Any, x: float, y: float, _relative: Any = False
        ) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.x, widget.y = float(x), float(y)
            # CEGUI raises its Moved event whether the move came from a drag or
            # from a script, and MTA turns that into `onClientGUIMove`
            # (`CClientGame::OnMove`). A resource that guards against its own
            # repositioning has to be given something to guard against.
            self._dispatch_gui_event("onClientGUIMove", handle)
            return True

        def get_position(handle: Any, _relative: Any = False) -> Any:
            widget = widget_of(handle)
            if widget is None:
                return False
            return widget.x, widget.y

        def set_size(
            handle: Any, width: float, height: float, _relative: Any = False
        ) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.width, widget.height = float(width), float(height)
            self._dispatch_gui_event("onClientGUISize", handle)
            return True

        def get_size(handle: Any, _relative: Any = False) -> Any:
            widget = widget_of(handle)
            if widget is None:
                return False
            return widget.width, widget.height

        def set_movable(handle: Any, movable: Any = True) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.movable = movable is True
            return True

        def set_sizable(handle: Any, sizable: Any = True) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.sizable = sizable is True
            return True

        def set_text(handle: Any, text: Any) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.text = str(text)
            return True

        def get_text(handle: Any) -> Any:
            widget = widget_of(handle)
            return widget.text if widget is not None else False

        def set_enabled(handle: Any, enabled: Any) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.enabled = enabled is True
            return True

        def add_column(handle: Any, title: Any, _width: float) -> Any:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.columns.append(str(title))
            return len(widget.columns)

        def add_row(handle: Any, *_args: Any) -> Any:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.rows.append({})
            return len(widget.rows) - 1

        def set_item_text(
            handle: Any, row: float, column: float, text: Any, *_rest: Any
        ) -> bool:
            widget = widget_of(handle)
            if widget is None or not 0 <= int(row) < len(widget.rows):
                return False
            widget.rows[int(row)][int(column)] = str(text)
            return True

        def get_item_text(handle: Any, row: float, column: float) -> Any:
            widget = widget_of(handle)
            if widget is None or not 0 <= int(row) < len(widget.rows):
                return False
            return widget.rows[int(row)].get(int(column), "")

        def get_selected_item(handle: Any) -> Any:
            widget = widget_of(handle)
            if widget is None:
                return (-1, -1)
            return (widget.selected_row, widget.selected_column)

        def set_selected_item(handle: Any, row: float, column: float) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.selected_row = int(row)
            widget.selected_column = int(column)
            return True

        def clear_grid(handle: Any) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.rows = []
            widget.selected_row = -1
            widget.selected_column = -1
            return True

        g.guiCreateWindow = create_window
        g.guiCreateLabel = create_label
        g.guiCreateButton = create_button
        g.guiCreateEdit = create_edit
        g.guiCreateCheckBox = create_check_box
        g.guiCreateGridList = create_grid_list
        g.guiCreateBrowser = create_gui_browser
        g.guiGetBrowser = get_gui_browser
        def get_position(handle: Any, _relative: Any = False) -> Any:
            widget = widget_of(handle)
            if widget is None:
                return False
            return widget.x, widget.y

        def set_position(
            handle: Any, x: float, y: float, _relative: Any = False
        ) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.x = float(x)
            widget.y = float(y)
            return True

        g.guiGetPosition = get_position
        g.guiSetPosition = set_position
        g.guiSetText = set_text
        g.guiGetText = get_text
        def get_enabled(handle: Any) -> bool:
            widget = widget_of(handle)
            return widget.enabled if widget is not None else False

        def set_masked(handle: Any, masked: Any = True) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.masked = masked is True
            return True

        def get_selected(handle: Any) -> bool:
            widget = widget_of(handle)
            return widget.selected if widget is not None else False

        def set_selected(handle: Any, selected: Any) -> bool:
            widget = widget_of(handle)
            if widget is None:
                return False
            widget.selected = selected is True
            return True

        def row_count(handle: Any) -> int:
            widget = widget_of(handle)
            return len(widget.rows) if widget is not None else 0

        g.guiSetEnabled = set_enabled
        g.guiGetEnabled = get_enabled
        g.guiSetProperty = lambda *_args: True
        g.guiSetVisible = lambda *_args: True
        g.guiEditSetMasked = set_masked
        g.guiCheckBoxGetSelected = get_selected
        g.guiCheckBoxSetSelected = set_selected
        g.guiGridListAddColumn = add_column
        g.guiGridListAddRow = add_row
        g.guiGridListClear = clear_grid
        g.guiGridListSetItemText = set_item_text
        g.guiGridListGetItemText = get_item_text
        g.guiGridListGetSelectedItem = get_selected_item
        g.guiGridListSetSelectedItem = set_selected_item
        g.guiGridListGetRowCount = row_count
        g.guiSetPosition = set_position
        g.guiGetPosition = get_position
        g.guiSetSize = set_size
        g.guiGetSize = get_size
        g.guiWindowSetMovable = set_movable
        g.guiWindowSetSizable = set_sizable
        g.guiBringToFront = lambda *_args: True

    def _destroy_widget(self, index: int) -> None:
        """Destroy a control and everything parented to it, as CEGUI does."""
        self.widgets[index].destroyed = True
        for child, widget in enumerate(self.widgets):
            if widget.parent == index and not widget.destroyed:
                self._destroy_widget(child)

    @property
    def cursor_visible(self) -> bool:
        """On while anybody is asking for it, which is MTA's own rule."""
        return self._cursor_requests > 0

    def another_resource_shows_cursor(self) -> None:
        """Somebody else opened a window that wants the cursor.

        There is no second Lua state here, and there does not need to be: what
        another resource contributes is one more request on the shared count.
        """
        self._cursor_requests += 1

    def another_resource_hides_cursor(self) -> None:
        self._cursor_requests -= 1

    def widget_texts(self, kind: str | None = None) -> list[str]:
        """Text of every live control, i.e. what the player would read now."""
        return [
            widget.text
            for widget in self.widgets
            if not widget.destroyed and (kind is None or widget.kind == kind)
        ]

    #: The call `push` writes, with the state as its one captured group.
    _PANEL_PUSH = re.compile(r"ANKIGTA\.receive\((.*)\);\s*$", re.S)

    def _is_registered_event(self, name: str) -> bool:
        """Would MTA's event registry know this name?

        Two ways in: the engine registers its own, which are the `on...`
        family, and a script registers the rest with `addEvent`. Anything else
        is a name nobody declared, and MTA quietly calls nothing.
        """
        return name.startswith("on") or name in self._added_events

    def pushed_panel_states(self) -> list[dict[str, Any]]:
        """Every whole state Lua pushed into the panel page, in order.

        Decoded the way the page decodes it, wrapper and all. Reading the JSON
        out of the call by hand is what let `[state]` reach a page expecting
        `state`: four tests each had their own parser, and every one of them
        was happy to hand back the list. One reader here, and it asserts the
        shape rather than shrugging at one it does not recognise.
        """
        states = []
        for code in self.browser_javascript:
            found = self._PANEL_PUSH.search(code)
            if not found:
                continue
            argument = found.group(1)
            # What `push` writes: the `toJSON` list, indexed back to the table.
            assert argument.endswith(")[0]"), (
                "the panel must unwrap toJSON's argument list before the page "
                f"sees it, and this call does not: {argument[:80]}"
            )
            decoded = json.loads(argument[1:-4])
            assert isinstance(decoded, list) and len(decoded) == 1, (
                "toJSON wraps one table in a one-item list, got "
                f"{decoded!r:.80}"
            )
            states.append(dict(decoded[0]))
        return states

    def pushed_panel_state(self) -> dict[str, Any]:
        """The last whole state Lua pushed into the panel page."""
        states = self.pushed_panel_states()
        assert states, "the panel pushed no state"
        return states[-1]

    # ------------------------------------------------------------- controls

    def _dispatch_gui_event(self, name: str, handle: Any, *args: Any) -> bool:
        """Call the handlers attached to exactly this control.

        Returns whether any handler ran, so a test can tell "the control has no
        handler for this" from "the handler ran and did nothing".
        """
        if lua_type(handle) != "table":
            return False
        index = handle["__widget"]
        if index is None:
            return False
        index = int(index)
        if self.widgets[index].destroyed:
            return False
        fired = False
        for attached, handler in list(self._gui_handlers.get(name, [])):
            if attached == index:
                self._dispatch(handler, handle, args)
                fired = True
        return fired

    def widget_handle(self, index: int) -> Any:
        """A handle for a recorded control, the shape the resource holds."""
        widget = self.widgets[index]
        handle = {
            "__element": True,
            "type": "gui-" + widget.kind,
            "__widget": index,
        }
        if widget.destroyed:
            handle["__destroyed"] = True
        return self.lua.table_from(handle)

    def find_widget(self, text: str, kind: str | None = None) -> int:
        """Index of the live control reading exactly this, newest first.

        Newest first because a window is rebuilt rather than relabelled: after
        a language or scale change the older control with the same text is
        still recorded, and it is the destroyed one.
        """
        for index in reversed(range(len(self.widgets))):
            widget = self.widgets[index]
            if widget.destroyed or widget.text != text:
                continue
            if kind is not None and widget.kind != kind:
                continue
            return index
        raise LuaError(f"no live control reading {text!r}")

    def live_widgets(self, kind: str) -> list[int]:
        """Indices of every control of this kind that still exists."""
        return [
            index
            for index, widget in enumerate(self.widgets)
            if widget.kind == kind and not widget.destroyed
        ]

    def click(self, handle: Any, *args: Any) -> bool:
        """Click a control by the handle the resource holds."""
        return self.trigger_on("onClientGUIClick", handle, *args)

    def click_gui(self, element: Any, event: str = "onClientGUIClick") -> None:
        """Click one control, reaching only the handlers hung on it."""
        self.trigger_on(event, element)

    def trigger_on(self, event: str, element: Any, *args: Any) -> bool:
        """Invoke only the handlers attached to `element`."""
        return self._dispatch_gui_event(event, element, *args)

    def click_widget(self, target: str | int, kind: str | None = None) -> None:
        """Click a control by its text or its index, as `onClientGUIClick`
        does."""
        index = target if isinstance(target, int) else self.find_widget(target, kind)
        self._dispatch_gui_event(
            "onClientGUIClick", self.widget_handle(index), "left", "up"
        )

    def drag_window(self, index: int, x: float, y: float) -> None:
        """Move a window the way the player dragging its title bar does.

        CEGUI moves the window itself and then raises the event, so the
        resource reads the new position back rather than being handed it.
        """
        widget = self.widgets[index]
        widget.x, widget.y = float(x), float(y)
        self._dispatch_gui_event("onClientGUIMove", self.widget_handle(index))

    def widget_rect(self, index: int) -> tuple[float, float, float, float]:
        widget = self.widgets[index]
        return widget.x, widget.y, widget.width, widget.height

    def grid_texts(self) -> list[str]:
        """Every grid column heading and cell, in the order they were written."""
        written: list[str] = []
        for widget in self.widgets:
            if widget.destroyed or widget.kind != "gridlist":
                continue
            written.extend(widget.columns)
            for row in widget.rows:
                written.extend(row[column] for column in sorted(row))
        return written

    def _record_move(self, element: Any, **fields: Any) -> None:
        """Collect setElement* calls per element, so tests read one entry."""
        kind = (
            str(element["type"])
            if lua_type(element) == "table" and element["type"]
            else "unknown"
        )
        name = (
            str(element["name"])
            if lua_type(element) == "table" and element["name"]
            else kind
        )
        for entry in self.moved:
            if entry["key"] == (kind, name):
                entry.update(fields)
                return
        entry = {"key": (kind, name), "type": kind, "element": element}
        entry.update(fields)
        self.moved.append(entry)

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
            # JSON `null` is `nil`, not `false`. `CLuaArgument::
            # ReadFromJSONObject` reads `json_type_null` as `LUA_TNIL`, and
            # `CLuaArguments::PushAsTable` settables that nil, so the key is
            # simply absent from the decoded table. A double that answered
            # `false` here is how the gateway shipped validators written
            # against `false` -- and rejected every real answer that carried a
            # null. See the test-double rule in
            # docs/design/remaining-work-plan.md.
            return None
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
        if self._owned_directory is not None:
            self._owned_directory.cleanup()
            self._owned_directory = None

    def __enter__(self) -> MtaSandbox:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

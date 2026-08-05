"""Every schema shape ANKIGTA has shipped, as a database a test can build.

Migrating "from version N" against an empty database proves almost nothing: the
statements that break are the ones that move rows, and a table with no rows has
none to lose. So each shape here is written out as the SQL that version really
had, and each is filled with the data that version really held — maps, Map
Entities, Spatial Links, Map Entity metadata, Change History and user settings,
whichever of them existed by then.

The shapes are reconstructed from the migration steps in `server/store.lua`,
each of which is the inverse of a shipped shape:

- **v1** — Map Entities carried a single `authored_heading`; `migrateVersionOne`
  is what turned it into `rotation_x/y/z`.
- **v2** — rotation columns, still no `spatial_links` and no
  `identity_collisions`; `migrateVersionTwo` adds both.
- **v3 legacy** — `map_entities` still restricted to `entity_type = 'object'`,
  from before vehicles and peds; the shape `needsEntityTypeMigration` detects.
- **v3** — the three entity types, `spatial_links` still restricted to
  `state = 'active'`.
- **v4** — `card_missing` admitted on a Spatial Link.
- **v5** — `map_entities` widened again so a card can hang on a marker.
- **v6** — v5's tables; what changed is a row, the `allowEarlyReview` boolean
  rewritten as the `reviewMode` it meant.
- **v7** — the current shape. `map_preferences` is gone: which maps take part
  in study is not a stored preference any more, so the table and the Change
  History entries that replayed into it go with it.

`history=True` adds the tables ticket 11 introduced. They are created by
`ensureChangeHistorySchema` on every open regardless of version, so any database
a build after ticket 11 has touched carries them — including one still sitting
at an older schema version, which is exactly the case where a migration that
renames `map_entities` can cascade a metadata row into nothing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


UUID = "11111111-1111-4111-8111-111111111111"
MAP_SHA = "A" * 64

#: Every shape a released ANKIGTA could have left on disk.
SHIPPED_VERSIONS = ("v1", "v2", "v3legacy", "v3", "v4", "v5", "v6", "v7")

#: The lowest version a database may be on once the store has opened it.
#:
#: A floor, never the current value (`docs/agents/lua-testing.md`). Reading the
#: number out of `store.lua` would put both sides of every assertion on the
#: same line of source, so a version bumped with no migration behind it would
#: still pass. `Store.open()` returning true is the strong claim -- it refuses
#: any database not at exactly the current version -- and this guards the
#: direction: raise it in the ticket whose migration raises the schema.
MIGRATED_SCHEMA_FLOOR = 8


_MAPS = """
CREATE TABLE maps (
    map_id TEXT PRIMARY KEY,
    resource_name TEXT NOT NULL,
    map_name TEXT NOT NULL
)
"""

_ENTITIES_V1 = """
CREATE TABLE map_entities (
    map_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type = 'object'),
    model INTEGER NOT NULL,
    authored_x REAL NOT NULL,
    authored_y REAL NOT NULL,
    authored_z REAL NOT NULL,
    authored_heading REAL NOT NULL,
    interior INTEGER NOT NULL,
    dimension INTEGER NOT NULL,
    PRIMARY KEY (map_id, entity_id),
    FOREIGN KEY (map_id) REFERENCES maps(map_id) ON DELETE CASCADE
)
"""

_ENTITIES_V2 = """
CREATE TABLE map_entities (
    map_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type = 'object'),
    model INTEGER NOT NULL,
    authored_x REAL NOT NULL,
    authored_y REAL NOT NULL,
    authored_z REAL NOT NULL,
    authored_heading REAL NOT NULL,
    rotation_x REAL NOT NULL DEFAULT 0,
    rotation_y REAL NOT NULL DEFAULT 0,
    rotation_z REAL NOT NULL DEFAULT 0,
    interior INTEGER NOT NULL,
    dimension INTEGER NOT NULL,
    PRIMARY KEY (map_id, entity_id),
    FOREIGN KEY (map_id) REFERENCES maps(map_id) ON DELETE CASCADE
)
"""

_ENTITIES_V3 = """
CREATE TABLE map_entities (
    map_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('object', 'vehicle', 'ped')),
    model INTEGER NOT NULL,
    authored_x REAL NOT NULL,
    authored_y REAL NOT NULL,
    authored_z REAL NOT NULL,
    rotation_x REAL NOT NULL,
    rotation_y REAL NOT NULL,
    rotation_z REAL NOT NULL,
    interior INTEGER NOT NULL,
    dimension INTEGER NOT NULL,
    PRIMARY KEY (map_id, entity_id),
    FOREIGN KEY (map_id) REFERENCES maps(map_id) ON DELETE CASCADE
)
"""

#: v5 widened the type so a card can hang on a marker.
_ENTITIES_CURRENT = _ENTITIES_V3.replace(
    "IN ('object', 'vehicle', 'ped')",
    "IN ('object', 'vehicle', 'ped', 'marker')",
)


_LINKS_V3 = """
CREATE TABLE spatial_links (
    map_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    collection_uuid TEXT NOT NULL,
    card_id INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state = 'active'),
    verified_map_sha256 TEXT NOT NULL,
    PRIMARY KEY (map_id, entity_id),
    FOREIGN KEY (map_id, entity_id)
        REFERENCES map_entities(map_id, entity_id) ON DELETE CASCADE
)
"""

_LINKS_V4 = """
CREATE TABLE spatial_links (
    map_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    collection_uuid TEXT NOT NULL,
    card_id INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active', 'card_missing')),
    verified_map_sha256 TEXT NOT NULL,
    PRIMARY KEY (map_id, entity_id),
    FOREIGN KEY (map_id, entity_id)
        REFERENCES map_entities(map_id, entity_id) ON DELETE CASCADE
)
"""

_COLLISIONS = """
CREATE TABLE identity_collisions (
    map_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    detected_at INTEGER NOT NULL,
    PRIMARY KEY (map_id, entity_id),
    FOREIGN KEY (map_id, entity_id)
        REFERENCES map_entities(map_id, entity_id) ON DELETE CASCADE
)
"""

#: The per-map switch, which every shape up to v6 carried.
_MAP_PREFERENCES = """
CREATE TABLE map_preferences (
    map_id TEXT PRIMARY KEY,
    include_in_study INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (map_id) REFERENCES maps(map_id) ON DELETE CASCADE
)
"""

_HISTORY = [
    """
    CREATE TABLE change_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation TEXT NOT NULL,
        target TEXT NOT NULL,
        before_json TEXT NOT NULL,
        after_json TEXT NOT NULL,
        created_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE change_history_state (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        cursor_id INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE map_entity_metadata (
        map_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        entity_tag TEXT NOT NULL DEFAULT '',
        radius REAL NOT NULL DEFAULT 3,
        show_radius INTEGER NOT NULL DEFAULT 0,
        presence_state TEXT NOT NULL DEFAULT 'identified'
            CHECK (presence_state IN ('identified', 'entity_missing')),
        PRIMARY KEY (map_id, entity_id),
        FOREIGN KEY (map_id, entity_id)
            REFERENCES map_entities(map_id, entity_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE user_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL
    )
    """,
]


#: The Map Entities every shape carries. Only `object` is legal before v3.
ENTITIES = [
    ("study-map", "gate", "object", 1337, 10.5, -20.25, 4.75, 135.0, 3, 17),
    ("study-map", "shed", "object", 3095, 1.0, 2.0, 3.0, 45.0, 0, 0),
    ("second-map", "kerb", "object", 1226, -5.5, 6.25, 0.5, 270.0, 1, 2),
]

#: Added on top for shapes that admit vehicles and peds.
TYPED_ENTITIES = [
    ("study-map", "van", "vehicle", 411, 12.0, 20.0, 3.0, 90.0, 0, 0),
    ("study-map", "guide", "ped", 7, 14.0, 20.0, 3.0, 180.0, 0, 0),
]

#: Spatial Links, for the shapes that have the table.
LINKS = [
    ("study-map", "gate", UUID, 101, "active", MAP_SHA),
    ("second-map", "kerb", UUID, 202, "active", MAP_SHA),
]

#: Map Entity metadata, for the shapes that have the table.
METADATA = [
    ("study-map", "gate", "Ворота склада", "склад", 7.5, 1, "identified"),
    ("study-map", "shed", "Shed", "yard", 3.0, 0, "entity_missing"),
    ("second-map", "kerb", "Kerb", "", 12.0, 1, "identified"),
]

SETTINGS = [
    ("activationRadius", "7"),
    ("maxActivationSpeedKmh", "25"),
]

#: The boolean that became `reviewMode`, stored the way the store writes one:
#: `toJSON` serialises its argument *list*, so a lone value comes back wrapped.
#: A migration that only understood the bare form would leave every database
#: the resource itself wrote un-migrated.
_EARLY_REVIEW_SETTING = ("allowEarlyReview", "[true]")

#: What that same choice looks like once it has a mode to be.
_REVIEW_MODE_SETTING = ("reviewMode", '["allow_all"]')


def _typed(version: str) -> bool:
    return version in ("v3", "v4")


def build(path: Path, version: str, *, history: bool | None = None) -> None:
    """Write a database in the shape `version` shipped, filled with real data."""
    if version not in SHIPPED_VERSIONS:
        raise ValueError(f"no such shipped version: {version}")
    if history is None:
        # Any build after ticket 11 creates these on open, so the shapes that
        # can still be met in the wild at that version carry them.
        history = version in ("v3", "v4", "v5", "v6", "v7")

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.isolation_level = None
    try:
        _create(connection, version, history=history)
        _fill(connection, version, history=history)
    finally:
        connection.close()


def _create(connection: sqlite3.Connection, version: str, *, history: bool) -> None:
    numeric = {
        "v1": 1, "v2": 2, "v3legacy": 3, "v3": 3, "v4": 4, "v5": 5, "v6": 6,
        "v7": 7,
    }[version]
    connection.execute(
        "CREATE TABLE schema_meta ("
        "    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),"
        "    version INTEGER NOT NULL"
        ")"
    )
    connection.execute(
        "INSERT INTO schema_meta (singleton, version) VALUES (1, ?)", (numeric,)
    )
    connection.execute(_MAPS)
    connection.execute(
        {
            "v1": _ENTITIES_V1,
            "v2": _ENTITIES_V2,
            "v3legacy": _ENTITIES_V2,
            "v3": _ENTITIES_V3,
            "v4": _ENTITIES_V3,
            "v5": _ENTITIES_CURRENT,
            "v6": _ENTITIES_CURRENT,
            "v7": _ENTITIES_CURRENT,
        }[version]
    )
    if version in ("v3legacy", "v3"):
        connection.execute(_LINKS_V3)
        connection.execute(_COLLISIONS)
    elif version in ("v4", "v5", "v6", "v7"):
        connection.execute(_LINKS_V4)
        connection.execute(_COLLISIONS)
    if history:
        for statement in _HISTORY:
            connection.execute(statement)
        if version != "v7":
            connection.execute(_MAP_PREFERENCES)


def _fill(connection: sqlite3.Connection, version: str, *, history: bool) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executemany(
        "INSERT INTO maps (map_id, resource_name, map_name) VALUES (?, ?, ?)",
        [
            ("study-map", "ankigta", "maps/study.map"),
            ("second-map", "ankigta", "maps/second.map"),
        ],
    )

    entities = list(ENTITIES)
    if _typed(version):
        entities += TYPED_ENTITIES
    for entity in entities:
        map_id, entity_id, kind, model, x, y, z, heading, interior, dimension = entity
        if version == "v1":
            connection.execute(
                "INSERT INTO map_entities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (map_id, entity_id, kind, model, x, y, z, heading, interior, dimension),
            )
        elif version in ("v2", "v3legacy"):
            connection.execute(
                "INSERT INTO map_entities VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
                (
                    map_id, entity_id, kind, model, x, y, z, heading,
                    heading, interior, dimension,
                ),
            )
        else:
            connection.execute(
                "INSERT INTO map_entities VALUES "
                "(?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
                (
                    map_id, entity_id, kind, model, x, y, z,
                    heading, interior, dimension,
                ),
            )

    if version in ("v3legacy", "v3", "v4"):
        connection.executemany(
            "INSERT INTO spatial_links VALUES (?, ?, ?, ?, ?, ?)", LINKS
        )
        connection.execute(
            "INSERT INTO identity_collisions VALUES (?, ?, ?, ?)",
            ("second-map", "kerb", "copied_map_id", 1234),
        )

    if not history:
        return
    connection.executemany(
        "INSERT INTO map_entity_metadata VALUES (?, ?, ?, ?, ?, ?, ?)", METADATA
    )
    if version != "v7":
        connection.execute(
            "INSERT INTO map_preferences (map_id, include_in_study) VALUES (?, ?)",
            ("second-map", 0),
        )
    connection.executemany(
        "INSERT INTO user_settings (setting_key, setting_value) VALUES (?, ?)",
        SETTINGS
        + [
            _REVIEW_MODE_SETTING
            if version in ("v6", "v7")
            else _EARLY_REVIEW_SETTING
        ],
    )
    history_entries = [
        (
            "user_setting",
            '{"settingKey":"activationRadius"}',
            '{"exists":false}',
            '{"exists":true,"value":7}',
            100,
        ),
    ]
    if version != "v7":
        history_entries.append(
            (
                "map_preference",
                '{"mapId":"second-map"}',
                '{"exists":false}',
                '{"exists":true,"includeInStudy":false}',
                200,
            )
        )
    connection.executemany(
        "INSERT INTO change_history "
        "(operation, target, before_json, after_json, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        history_entries,
    )
    connection.execute(
        "INSERT INTO change_history_state (singleton, cursor_id) VALUES (1, ?)",
        (len(history_entries),),
    )


def rows(path: Path, sql: str) -> list[dict[str, object]]:
    """Read a database straight, with no Lua in the way."""
    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute(sql)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, record)) for record in cursor.fetchall()]
    finally:
        connection.close()

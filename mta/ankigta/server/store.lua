ANKIGTA = ANKIGTA or {}

local DATABASE_PATH = "ankigta.sqlite"
local CURRENT_SCHEMA_VERSION = 8
local HISTORY_LIMIT = 100

-- The volume ticket 30 states its thresholds against. Nothing here is a limit:
-- a larger world is stored, read and written exactly as a smaller one is. It is
-- the point past which ANKIGTA stops promising the response times, and says so
-- rather than letting the player conclude something is broken.
local REFERENCE_MAP_ENTITIES = 10000
local REFERENCE_SPATIAL_LINKS = 5000

local TRACER_MAP = {
    mapId = "ticket05-map",
    resourceName = "ankigta",
    mapName = "Ticket 05 tracer map",
}

local TRACER_ENTITY = {
    mapId = TRACER_MAP.mapId,
    entityId = "ticket05-entity",
    entityType = "object",
    model = 1337,
    authoredX = 10.5,
    authoredY = -20.25,
    authoredZ = 4.75,
    rotationX = 0,
    rotationY = 0,
    rotationZ = 135,
    interior = 3,
    dimension = 17,
}

local TICKET07_MAP = {
    mapId = "ticket07-map",
    resourceName = "ankigta",
    mapName = "maps/ticket07-matrix.map",
}

local TICKET07_ENTITIES = {
    {
        entityId = "ticket07-vehicle",
        entityType = "vehicle",
        model = 411,
        authoredX = 12,
        authoredY = 20,
        authoredZ = 3,
        rotationX = 0,
        rotationY = 0,
        rotationZ = 90,
    },
    {
        entityId = "ticket07-ped",
        entityType = "ped",
        model = 7,
        authoredX = 14,
        authoredY = 20,
        authoredZ = 3,
        rotationX = 0,
        rotationY = 0,
        rotationZ = 180,
    },
}

local Store = {
    connection = nil,
    ready = false,
    errorCategory = nil,
    errorMessage = nil,
    schemaVersion = nil,
    historyReady = false,
    -- Set only when the database cannot be opened and the user has to choose
    -- what happens next. Nothing here ever resolves it on its own.
    recoveryState = nil,
    -- Whether the "past the reference volume" line has already been logged for
    -- the current crossing.
    volumeWarned = false,
}

local function execute(connection, statement, ...)
    local handle = dbQuery(connection, statement, ...)
    if not handle then
        return false, "query_rejected"
    end

    local rows, errorCode, errorMessage = dbPoll(handle, -1)
    if rows == false then
        return false, tostring(errorCode) .. ": " .. tostring(errorMessage)
    end
    return true, rows
end

local function fail(category, message)
    Store.ready = false
    Store.errorCategory = category
    Store.errorMessage = tostring(message)
    outputDebugString(
        "[ANKIGTA] " .. category .. ": " .. Store.errorMessage,
        1
    )
    return false
end

local function connect(path)
    return dbConnect(
        "sqlite",
        path,
        "",
        "",
        "share=0;batch=0;tag=ankigta"
    )
end

local function closeConnection()
    if isElement(Store.connection) then
        destroyElement(Store.connection)
    end
    Store.connection = nil
end

local function enableForeignKeys(connection)
    local ok, errorMessage = execute(connection, "PRAGMA foreign_keys = ON")
    if not ok then
        return false, errorMessage
    end

    local checked, rows = execute(connection, "PRAGMA foreign_keys")
    if not checked or not rows[1] or tonumber(rows[1].foreign_keys) ~= 1 then
        return false, "foreign_keys_not_enabled"
    end
    return true
end

local function transaction(connection, steps)
    local begun, beginError = execute(connection, "BEGIN IMMEDIATE")
    if not begun then
        return false, beginError
    end

    for _, step in ipairs(steps) do
        local ok, stepError = execute(connection, step[1], unpack(step[2] or {}))
        if not ok then
            execute(connection, "ROLLBACK")
            return false, stepError
        end
    end

    local committed, commitError = execute(connection, "COMMIT")
    if not committed then
        execute(connection, "ROLLBACK")
        return false, commitError
    end
    return true
end

local function jsonEncode(value)
    if value == nil then
        return "null"
    end
    return toJSON(value, true)
end

local function jsonDecode(value)
    if value == nil or value == "null" then
        return nil
    end
    local decoded = fromJSON(value)
    return decoded
end

local function historyTarget(mapId, entityId)
    return jsonEncode({mapId = mapId, entityId = entityId})
end

local function historySteps(operation, target, before, after)
    return {
        {
            "DELETE FROM change_history WHERE history_id > "
                .. "(SELECT cursor_id FROM change_history_state WHERE singleton = 1)",
        },
        {
            [[
                INSERT INTO change_history (
                    operation, target, before_json, after_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
            ]],
            {
                operation,
                target,
                jsonEncode(before),
                jsonEncode(after),
                getTickCount(),
            },
        },
        {
            "UPDATE change_history_state SET cursor_id = last_insert_rowid() "
                .. "WHERE singleton = 1",
        },
        {
            "DELETE FROM change_history WHERE history_id NOT IN "
                .. "(SELECT history_id FROM change_history "
                .. "ORDER BY history_id DESC LIMIT " .. tostring(HISTORY_LIMIT) .. ")",
        },
    }
end

--- Tell the backup module the data moved.
-- It only marks the store dirty; the copying happens on a timer, because F7 has
-- a two-second envelope and copying a database is not what to spend it on.
local function noteDataChange()
    if ANKIGTA.Backup and ANKIGTA.Backup.noteDataChange then
        ANKIGTA.Backup.noteDataChange()
    end
end

local function historyTransaction(operation, target, before, after, steps)
    local allSteps = {}
    for _, step in ipairs(steps or {}) do
        table.insert(allSteps, step)
    end
    for _, step in ipairs(historySteps(operation, target, before, after)) do
        table.insert(allSteps, step)
    end
    local committed, errorMessage = transaction(Store.connection, allSteps)
    if not committed then
        return false, errorMessage
    end
    noteDataChange()
    return true
end

-- --- Map Entity metadata rows ------------------------------------------------
--
-- Written from six places: a metadata edit, either side of an undone relink,
-- an undone removal, a relink and a copy. Each of them wrote the column list
-- out again, so adding a column meant finding all six -- and the one that was
-- missed would quietly write a default over whatever the entity said. They go
-- through `metadataSteps` now, and what that writes is the schema's own list of
-- overridable settings rather than a column list kept here.

--- Every setting a Map Entity may answer for itself, as this module needs it.
--
-- Derived from the schema, and derived once. The schema is a shipped table that
-- nothing rewrites while the server runs, and this is read once per row of the
-- F7 snapshot -- ten thousand rows inside a two-second envelope. Re-deriving it
-- there means walking and sorting the whole schema per row, which costs more
-- than the read it serves.
local overridable = false

local function overridableSettings()
    if overridable then
        return overridable
    end
    local settings = ANKIGTA.Settings
    local list = {}
    for _, key in ipairs(settings.entityOverridableKeys()) do
        local definition = settings.definition(key)
        list[#list + 1] = {
            key = key,
            column = settings.entityOverrideColumn(key),
            field = settings.entityOverrideField(key),
            kind = definition and definition.rule and definition.rule.kind,
        }
    end
    overridable = list
    return list
end

--- One override as SQLite should hold it, or `nil` for "nothing of its own".
--
-- A boolean is stored as 1/0 because SQLite has no boolean, and the column is
-- NULL-able so that `false` -- "no corona on this one, whatever the global
-- says" -- is a value the entity can hold rather than a way of saying nothing.
local function storedOverride(kind, value)
    if value == nil then
        return nil
    end
    if kind == "boolean" then
        return value == true and 1 or 0
    end
    if kind == "number" then
        return tonumber(value)
    end
    if type(value) == "string" and value ~= "" then
        return value
    end
    return nil
end

--- The same, read back out of a row.
--
-- SQL NULL reaches Lua as boolean `false` (`PushRegistryResultTable`), which is
-- also a legitimate value for a boolean column -- so the two are told apart
-- here, once, by the type SQLite handed over rather than by its truthiness.
local function readOverride(kind, stored)
    if stored == nil or stored == false then
        return nil
    end
    if kind == "boolean" then
        return tonumber(stored) == 1
    end
    if kind == "number" then
        return tonumber(stored)
    end
    if type(stored) ~= "string" or stored == "" then
        return nil
    end
    return stored
end

--- Record one override, or record that the entity has none.
--
-- A statement of its own rather than a column in the insert beside it, because
-- "it has none" is SQL NULL and `dbExec` takes a parameter *list*: a nil in the
-- middle of one truncates it and `false` binds as 0, which for a radius is zero
-- rather than the absence of one. A literal NULL in the statement has neither
-- problem, and every write of a metadata row goes through here so none of them
-- can forget the question.
local function overrideStep(column, mapId, entityId, value)
    if value == nil then
        return {
            "UPDATE map_entity_metadata SET " .. column .. " = NULL"
                .. " WHERE map_id = ? AND entity_id = ?",
            {mapId, entityId},
        }
    end
    return {
        "UPDATE map_entity_metadata SET " .. column .. " = ?"
            .. " WHERE map_id = ? AND entity_id = ?",
        {value, mapId, entityId},
    }
end

local METADATA_INSERT = [[
    INSERT OR REPLACE INTO map_entity_metadata (
        map_id, entity_id, name, entity_tag, presence_state
    ) VALUES (?, ?, ?, ?, ?)
]]

--- What this row says of its own, keyed the way the rest of the resource is.
--
-- An absent field is the entity saying nothing, which means it follows the
-- global. One word for that, everywhere: `false` used to be it, and stopped
-- working the day a boolean became overridable -- `false` is then a value
-- somebody chose, not the absence of one.
--
-- Exposed because the F7 snapshot is built out of rows this module hands over,
-- and "a NULL column means follow the setting" is this module's rule about its
-- own storage rather than the snapshot's.
function Store.overridesOf(row)
    local overrides = {}
    for _, setting in ipairs(overridableSettings()) do
        overrides[setting.field] = readOverride(
            setting.kind, row and row[setting.column]
        )
    end
    return overrides
end

--- Everything one row says about itself, as a metadata table.
--
-- The one reader. Six callers used to spell out the same field list, which is
-- how "and also switch the corona off" got into an undo: the list each of them
-- carried was the list as of the day it was written.
function Store.metadataOf(row, presenceState)
    local metadata = Store.overridesOf(row)
    metadata.name = row and row.entity_name or ""
    metadata.entityTag = row and row.entity_tag or ""
    metadata.presenceState = presenceState
        or (row and row.entity_state)
        or "identified"
    return metadata
end

--- The same metadata, with the one field that has had two names under one.
--
-- Change History is persisted as JSON, so a state journalled before the flag
-- was renamed still says `showRadius` -- and it is exactly the states that
-- predate an upgrade that Undo exists to put back. Reading only the current
-- name would turn every such undo into "and also switch the corona off".
--
-- Done here, once, rather than inside the writer below: that loop is written to
-- know no field names at all, and a name in it would be the beginning of a
-- second list. The old name is read only where the new one is absent, so a
-- state carrying both cannot have the stale half win.
local function underCurrentNames(metadata)
    if metadata.showCorona == nil and metadata.showRadius ~= nil then
        local renamed = {}
        for key, value in pairs(metadata) do
            renamed[key] = value
        end
        renamed.showCorona = metadata.showRadius == true
        return renamed
    end
    return metadata
end

--- Write one metadata row, overrides and all.
--
-- The insert carries only what every row must have; each override is its own
-- statement, because "this entity has none" is NULL and a bound parameter list
-- cannot hold one. A caller that wrote only the insert would put an entity back
-- on every global each time it saved a name.
local function metadataSteps(mapId, entityId, metadata)
    metadata = underCurrentNames(metadata or {})
    local steps = {
        {
            METADATA_INSERT,
            {
                mapId,
                entityId,
                tostring(metadata.name or ""),
                tostring(metadata.entityTag or ""),
                metadata.presenceState or "identified",
            },
        },
    }
    for _, setting in ipairs(overridableSettings()) do
        steps[#steps + 1] = overrideStep(
            setting.column,
            mapId,
            entityId,
            storedOverride(setting.kind, metadata[setting.field])
        )
    end
    return steps
end

--- The same, read straight off a row rather than out of a metadata table.
--
-- The two differ in one thing: a row names its columns and a metadata table
-- names the fields the rest of the resource uses. Everything else about "what
-- one metadata row holds" stays in `metadataSteps`.
local function metadataStepsFromRow(mapId, entityId, row, presenceState)
    return metadataSteps(mapId, entityId, Store.metadataOf(row, presenceState))
end

--- Add every step of a metadata write to a step list being built.
local function addMetadataSteps(steps, mapId, entityId, metadata)
    for _, step in ipairs(metadataSteps(mapId, entityId, metadata)) do
        table.insert(steps, step)
    end
    return steps
end

--- Columns `map_entity_metadata` has grown since it was first created.
--
-- Listed rather than written out at each call site, so the repair below and
-- the `CREATE TABLE` above cannot disagree about what a metadata row holds. An
-- entry here is added to a database that lacks it; the `CREATE` is what a
-- fresh one gets, and the two have to say the same thing.
local METADATA_COLUMN_ADDITIONS = {
    {
        name = "presence_state",
        declaration = "TEXT NOT NULL DEFAULT 'identified'",
    },
    -- The defaults are the "follows Settings" values, so a row that already
    -- exists gains them already saying what it said before: nothing of its own.
    {name = "corona_color", declaration = "TEXT NOT NULL DEFAULT ''"},
    {name = "corona_opacity", declaration = "REAL NOT NULL DEFAULT -1"},
}

--- The override columns, as the schema names them.
--
-- Not written out here: `CREATE TABLE` below builds this part of itself from
-- the schema, and the migration that adds them to an older database reads the
-- same list. A setting that gains an override gains its column by gaining the
-- declaration, in one place, rather than in three that have to agree.
--
-- Every one of them is NULL-able and has no default, because NULL is how a row
-- says it has nothing of its own -- and a row that has just been created has
-- exactly that to say about every one of them.
local function overrideColumnDeclarations()
    local declarations = {}
    for _, setting in ipairs(overridableSettings()) do
        local storage = "TEXT"
        if setting.kind == "number" then
            storage = "REAL"
        elseif setting.kind == "boolean" then
            storage = "INTEGER"
        end
        declarations[#declarations + 1] = {
            name = setting.column,
            declaration = storage,
        }
    end
    return declarations
end

--- The metadata table, with one column per overridable setting.
--
-- The four columns above the overrides are inert and kept only because SQLite
-- cannot drop a column from a table that is the child of a cascading foreign
-- key without rebuilding it. Each of them was once the answer and could not
-- hold "this entity has none": `radius` and `show_radius` are NOT NULL, and
-- `corona_color` and `corona_opacity` said it with `''` and `-1` -- a different
-- spelling of nothing per column, which is what made clearing an override
-- everywhere need a list of special cases. The override columns beside them are
-- NULL-able, and NULL is the one spelling.
local function metadataTableStatement()
    local columns = {
        "map_id TEXT NOT NULL",
        "entity_id TEXT NOT NULL",
        "name TEXT NOT NULL DEFAULT ''",
        "entity_tag TEXT NOT NULL DEFAULT ''",
        "radius REAL NOT NULL DEFAULT 3",
        "show_radius INTEGER NOT NULL DEFAULT 0",
        "corona_color TEXT NOT NULL DEFAULT ''",
        "corona_opacity REAL NOT NULL DEFAULT -1",
        "presence_state TEXT NOT NULL DEFAULT 'identified'"
            .. " CHECK (presence_state IN ('identified', 'entity_missing'))",
    }
    for _, addition in ipairs(overrideColumnDeclarations()) do
        columns[#columns + 1] = addition.name .. " " .. addition.declaration
    end
    columns[#columns + 1] = "PRIMARY KEY (map_id, entity_id)"
    columns[#columns + 1] = "FOREIGN KEY (map_id, entity_id)"
        .. " REFERENCES map_entities(map_id, entity_id) ON DELETE CASCADE"
    return "CREATE TABLE IF NOT EXISTS map_entity_metadata ("
        .. table.concat(columns, ", ")
        .. ")"
end

local function ensureChangeHistorySchema()
    local created, errorMessage = transaction(Store.connection, {
        {
            [[
                CREATE TABLE IF NOT EXISTS change_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    target TEXT NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            ]],
        },
        {
            [[
                CREATE TABLE IF NOT EXISTS change_history_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    cursor_id INTEGER NOT NULL DEFAULT 0
                )
            ]],
        },
        {
            "INSERT OR IGNORE INTO change_history_state (singleton, cursor_id) VALUES (1, 0)",
        },
        {metadataTableStatement()},
        {
            [[
                CREATE TABLE IF NOT EXISTS user_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL
                )
            ]],
        },
    })
    if created then
        local ok, columns = execute(
            Store.connection,
            "PRAGMA table_info(map_entity_metadata)"
        )
        if not ok then
            return false, "metadata_schema_read_failed"
        end
        local present = {}
        for _, column in ipairs(columns) do
            present[column.name] = true
        end
        -- Repaired in place rather than through a numbered migration, the way
        -- `presence_state` already was. This table is created on every open
        -- regardless of schema version -- it arrived with Change History -- so
        -- a database can be carrying it while sitting at any version, and a
        -- version step would only run for some of them. Each addition here is
        -- a column an older shape simply lacks, never one whose meaning
        -- changed, so adding it is the whole repair.
        for _, addition in ipairs(METADATA_COLUMN_ADDITIONS) do
            if not present[addition.name] then
                local altered, alterError = execute(
                    Store.connection,
                    "ALTER TABLE map_entity_metadata ADD COLUMN "
                        .. addition.name .. " " .. addition.declaration
                )
                if not altered then
                    return false, alterError
                end
            end
        end
        -- The override columns are *not* repaired here. Adding them rewrites
        -- rows -- what the entity used to say lives in the inert column beside
        -- each one and has to be carried across -- and
        -- `docs/operations/backups-and-recovery.md` wants a verified copy
        -- before anything that does, which only the migration path takes. See
        -- `entity_override_columns` in `MIGRATIONS`.
    end
    Store.historyReady = created == true
    return created, errorMessage
end

local function hasSchema(connection)
    local ok, rows = execute(
        connection,
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
    )
    return ok and rows[1] ~= nil
end

local function readSchemaVersion(connection)
    local ok, rows = execute(
        connection,
        "SELECT version FROM schema_meta WHERE singleton = 1"
    )
    if not ok or not rows[1] then
        return nil
    end
    return tonumber(rows[1].version)
end

local function createCurrentSchema(connection)
    return transaction(connection, {
        {
            [[
                CREATE TABLE schema_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    version INTEGER NOT NULL
                )
            ]],
        },
        {
            "INSERT INTO schema_meta (singleton, version) VALUES (1, ?)",
            {CURRENT_SCHEMA_VERSION},
        },
        {
            [[
                CREATE TABLE maps (
                    map_id TEXT PRIMARY KEY,
                    resource_name TEXT NOT NULL,
                    map_name TEXT NOT NULL
                )
            ]],
        },
        {
            [[
                CREATE TABLE map_entities (
                    map_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL CHECK (entity_type IN ('object', 'vehicle', 'ped', 'marker')),
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
            ]],
        },
        {
            [[
                CREATE TABLE spatial_links (
                    map_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    collection_uuid TEXT NOT NULL,
                    card_id INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('active', 'card_missing')
                    ),
                    verified_map_sha256 TEXT NOT NULL,
                    PRIMARY KEY (map_id, entity_id),
                    FOREIGN KEY (map_id, entity_id)
                        REFERENCES map_entities(map_id, entity_id)
                        ON DELETE CASCADE
                )
            ]],
        },
    })
end

local function migrateVersionTwo()
    return transaction(Store.connection, {
        {
            [[
                CREATE TABLE spatial_links (
                    map_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    collection_uuid TEXT NOT NULL,
                    card_id INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK (state = 'active'),
                    verified_map_sha256 TEXT NOT NULL,
                    PRIMARY KEY (map_id, entity_id),
                    FOREIGN KEY (map_id, entity_id)
                        REFERENCES map_entities(map_id, entity_id)
                        ON DELETE CASCADE
                )
            ]],
        },
        {
            "UPDATE schema_meta SET version = ? WHERE singleton = 1",
            {3},
        },
        {
            [[
                CREATE TABLE identity_collisions (
                    map_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    detected_at INTEGER NOT NULL,
                    PRIMARY KEY (map_id, entity_id),
                    FOREIGN KEY (map_id, entity_id)
                        REFERENCES map_entities(map_id, entity_id)
                        ON DELETE CASCADE
                )
            ]],
        },
    })
end

local function migrateVersionFour()
    return transaction(Store.connection, {
        {"ALTER TABLE spatial_links RENAME TO spatial_links_v3"},
        {
            [[
                CREATE TABLE spatial_links (
                    map_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    collection_uuid TEXT NOT NULL,
                    card_id INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('active', 'card_missing')
                    ),
                    verified_map_sha256 TEXT NOT NULL,
                    PRIMARY KEY (map_id, entity_id),
                    FOREIGN KEY (map_id, entity_id)
                        REFERENCES map_entities(map_id, entity_id)
                        ON DELETE CASCADE
                )
            ]],
        },
        {
            [[
                INSERT INTO spatial_links
                    (map_id, entity_id, collection_uuid, card_id,
                     state, verified_map_sha256)
                SELECT map_id, entity_id, collection_uuid, card_id,
                       state, verified_map_sha256
                FROM spatial_links_v3
            ]],
        },
        {"DROP TABLE spatial_links_v3"},
        {
            "UPDATE schema_meta SET version = ? WHERE singleton = 1",
            {4},
        },
    })
end

local function needsEntityTypeMigration()
    local ok, rows = execute(
        Store.connection,
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'map_entities'"
    )
    if not ok or not rows[1] or type(rows[1].sql) ~= "string" then
        return false
    end
    -- Only the oldest shape, which compared with `=` rather than listing the
    -- types. Widening the list for markers is version 5's job and no earlier
    -- migration's: claiming it here would rebuild `map_entities` on the way
    -- through version 3, changing the schema before a later step that may yet
    -- fail.
    return rows[1].sql:find("entity_type = 'object'", 1, true) ~= nil
end

--- Rebuild `map_entities` without taking its dependants with it.
--
-- `spatial_links`, `map_entity_metadata` and `identity_collisions` all cascade
-- on delete from `map_entities`. Renaming it out of the way is the obvious
-- move and the wrong one: SQLite rewrites their `REFERENCES` clauses to follow
-- the renamed table, and dropping it afterwards then cascades their rows into
-- nothing -- Spatial Links and Map Entity metadata gone, quietly, inside a
-- migration that reported success.
--
-- So this follows the procedure SQLite documents for altering a table other
-- tables point at: foreign keys off, build the replacement under a temporary
-- name, drop the original, rename the replacement into its place, and check the
-- constraints before trusting the result.
local function rebuildMapEntities()
    local disabled = execute(Store.connection, "PRAGMA foreign_keys = OFF")
    if not disabled then
        return false, "foreign_keys_disable_failed"
    end
    local rebuilt, rebuildError = transaction(Store.connection, {
        {
            [[
                CREATE TABLE map_entities_rebuilt (
                    map_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL CHECK (entity_type IN ('object', 'vehicle', 'ped', 'marker')),
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
            ]],
        },
        {
            [[
                INSERT INTO map_entities_rebuilt
                SELECT map_id, entity_id, entity_type, model,
                       authored_x, authored_y, authored_z,
                       rotation_x, rotation_y, rotation_z,
                       interior, dimension
                FROM map_entities
            ]],
        },
        {"DROP TABLE map_entities"},
        {"ALTER TABLE map_entities_rebuilt RENAME TO map_entities"},
    })
    -- Whatever happened, the connection goes back to enforcing constraints.
    local restored = enableForeignKeys(Store.connection)
    if not rebuilt then
        return false, rebuildError
    end
    if not restored then
        return false, "foreign_keys_not_enabled"
    end
    local checked, violations = execute(Store.connection, "PRAGMA foreign_key_check")
    if not checked then
        return false, "constraint_check_failed"
    end
    if violations[1] then
        return false, "map_entity_rebuild_broke_constraints"
    end
    return true
end

--- Version 5: a marker is a thing a card can hang on.
--
-- The shape change is `rebuildMapEntities`, which widens the type constraint.
-- It is a version rather than a silent repair because a v4 database and a v5
-- one differ in what they will accept, and two shapes under one number is how
-- "already current" stops meaning anything.
local function migrateVersionFive()
    local rebuilt, rebuildError = rebuildMapEntities()
    if not rebuilt then
        return false, rebuildError
    end
    return transaction(Store.connection, {
        {
            "UPDATE schema_meta SET version = ? WHERE singleton = 1",
            {5},
        },
    })
end

--- Version 6: `allowEarlyReview` becomes the Review mode it meant.
--
-- Carried across rather than dropped. `listUserSettings` discards a stored
-- value the schema no longer accepts, which for a renamed setting would mean
-- silently putting the user back on the default -- a player who had turned
-- early review on would find their session quietly smaller after an update,
-- with nothing anywhere saying why.
--
-- The old value is read through the same JSON the store writes, because a
-- boolean has been written both bare and inside `toJSON`'s argument list, and
-- a rename that only understood one of the two shapes would migrate half the
-- databases in the wild.
local function migrateVersionSix()
    local steps = {}
    local ok, rows = execute(
        Store.connection,
        "SELECT setting_value FROM user_settings WHERE setting_key = ?",
        "allowEarlyReview"
    )
    -- A database from before the settings table exists has nothing to carry;
    -- it is the version number that has to move, not a row.
    if ok and rows[1] then
        local wasAllowed = jsonDecode(rows[1].setting_value) == true
        table.insert(steps, {
            "INSERT OR REPLACE INTO user_settings "
                .. "(setting_key, setting_value) VALUES (?, ?)",
            {
                "reviewMode",
                jsonEncode(wasAllowed and "allow_all" or "allow_due"),
            },
        })
        table.insert(steps, {
            "DELETE FROM user_settings WHERE setting_key = ?",
            {"allowEarlyReview"},
        })
    end
    table.insert(steps, {
        "UPDATE schema_meta SET version = ? WHERE singleton = 1",
        {6},
    })
    return transaction(Store.connection, steps)
end

local function tableExists(name)
    local ok, rows = execute(
        Store.connection,
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        name
    )
    return ok and rows[1] ~= nil
end

--- Version 7: the per-map `Include in study` switch stops being stored.
--
-- Which maps take part is not a preference any more -- a Map Entity is in play
-- when its map is loaded -- so a stored answer is a value nothing can read and
-- nothing can change. Only the preference goes: every Spatial Link on every
-- map, including the ones that were switched off, is left exactly as it is.
--
-- The switch's Change History entries go with the table they replayed into.
-- The cursor is walked back to the newest surviving entry rather than left
-- pointing at a deleted one, which Undo would report as a missing entry and
-- never get past.
local function migrateVersionSeven()
    local steps = {}
    -- The history tables are created after migrations run, so a database old
    -- enough not to have them yet has no entries to clear either.
    if tableExists("change_history") then
        table.insert(steps, {
            "DELETE FROM change_history WHERE operation = 'map_preference'",
        })
    end
    if tableExists("change_history_state") and tableExists("change_history") then
        table.insert(steps, {
            [[
                UPDATE change_history_state
                SET cursor_id = COALESCE(
                    (SELECT MAX(history_id) FROM change_history
                     WHERE history_id <= change_history_state.cursor_id),
                    0
                )
                WHERE singleton = 1
            ]],
        })
    end
    table.insert(steps, {"DROP TABLE IF EXISTS map_preferences"})
    table.insert(steps, {
        "UPDATE schema_meta SET version = ? WHERE singleton = 1",
        {7},
    })
    return transaction(Store.connection, steps)
end

local function migrateIdentityCollisionTable()
    return transaction(Store.connection, {
        {
            [[
                CREATE TABLE identity_collisions (
                    map_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    detected_at INTEGER NOT NULL,
                    PRIMARY KEY (map_id, entity_id),
                    FOREIGN KEY (map_id, entity_id)
                        REFERENCES map_entities(map_id, entity_id)
                        ON DELETE CASCADE
                )
            ]],
        },
    })
end

local function ensureIdentityCollisionTable()
    if tableExists("identity_collisions") then
        return true
    end
    return migrateIdentityCollisionTable()
end

local function migrateVersionOne()
    return transaction(Store.connection, {
        {
            "ALTER TABLE map_entities ADD COLUMN rotation_x REAL NOT NULL DEFAULT 0",
        },
        {
            "ALTER TABLE map_entities ADD COLUMN rotation_y REAL NOT NULL DEFAULT 0",
        },
        {
            "ALTER TABLE map_entities ADD COLUMN rotation_z REAL NOT NULL DEFAULT 0",
        },
        {
            "UPDATE map_entities SET rotation_z = authored_heading",
        },
        {
            "UPDATE schema_meta SET version = ? WHERE singleton = 1",
            {2},
        },
    })
end

--- Every step from a shipped schema shape to the current one.
--
-- Each step names the *earliest* version it applies from, never the version it
-- expects to find. Pinning a step to `version == N` is how this repository
-- already broke once: a step that bumps the number first leaves the shape
-- repair after it looking at `N + 1`, deciding it has nothing to do, and
-- shipping a database that is at the current version while still carrying an
-- older shape. A floor keeps applying until the shape is actually right.
--
-- A step with no `to` is a shape repair rather than a version step. It bumps
-- nothing, and its `needed` probe both decides whether it runs and, once it has
-- run, terminates the loop.
--- Which override columns `map_entity_metadata` is still missing.
--
-- The table is created by `ensureChangeHistorySchema`, which runs *after*
-- migrations, so a database that has never had it needs nothing here: it will
-- be created with every column already on it, and `PRAGMA table_info` of a
-- table that does not exist answers with no rows.
local function missingOverrideColumns()
    local ok, columns = execute(
        Store.connection,
        "PRAGMA table_info(map_entity_metadata)"
    )
    if not ok or #columns == 0 then
        return {}
    end
    local present = {}
    for _, column in ipairs(columns) do
        present[column.name] = true
    end
    local missing = {}
    for _, addition in ipairs(overrideColumnDeclarations()) do
        if not present[addition.name] then
            missing[#missing + 1] = addition
        end
    end
    return missing
end

local function needsOverrideColumns()
    return #missingOverrideColumns() > 0
end

--- What each override column inherits from the inert one it replaces.
--
-- Only the four that had somewhere to be before. `radius` is NOT NULL, so it
-- could not say "this entity has none" -- naming an entity wrote a copy of the
-- shipped default onto it and the global stopped reaching it. `show_radius` is
-- the same shape, and `corona_color` and `corona_opacity` each said "nothing of
-- its own" in a spelling of their own, `''` and `-1`.
--
-- What is already on disk becomes an override of itself, except where the old
-- column was saying nothing. A stored radius of 3 might be a number somebody
-- chose or the copy the old write path made, and nothing on disk can tell them
-- apart -- so the reading that changes nothing is the one to take. A
-- `show_radius` of 0 *is* distinguishable: it was the default a row got for
-- being written at all, so it becomes "follows the global", and with the
-- shipped global off that is the same dark entity it was yesterday.
--
-- The two override columns this ticket adds outright inherit nothing: nobody
-- has ever answered them, so every row follows the global by having no answer.
-- Each names the inert column it reads, because a shape old enough to predate
-- the override is sometimes old enough to predate what it inherits from too:
-- `corona_color` arrived with ticket 04 and is added by the shape repair in
-- `ensureChangeHistorySchema`, which runs *after* migrations do. An UPDATE
-- naming a column that is not there yet fails the whole transaction, and a
-- failed migration is a server that will not start.
local OVERRIDE_BACKFILL = {
    radius_override = {
        from = "radius",
        statement = "UPDATE map_entity_metadata SET radius_override = radius"
            .. " WHERE radius_override IS NULL",
    },
    show_corona_override = {
        from = "show_radius",
        statement = "UPDATE map_entity_metadata SET show_corona_override = 1"
            .. " WHERE show_corona_override IS NULL AND show_radius = 1",
    },
    corona_color_override = {
        from = "corona_color",
        statement = "UPDATE map_entity_metadata"
            .. " SET corona_color_override = corona_color"
            .. " WHERE corona_color_override IS NULL AND corona_color <> ''",
    },
    corona_opacity_override = {
        from = "corona_opacity",
        statement = "UPDATE map_entity_metadata"
            .. " SET corona_opacity_override = corona_opacity"
            .. " WHERE corona_opacity_override IS NULL AND corona_opacity >= 0",
    },
}

--- Give every metadata row somewhere to say it has nothing of its own.
--
-- SQLite cannot drop NOT NULL without rebuilding the table, and this one is the
-- child of a foreign key with ON DELETE CASCADE, so a column beside each is the
-- cheaper answer; the originals are left inert.
--
-- A migration rather than a shape fixup beside `presence_state`, because it
-- rewrites rows and only this path takes a verified copy first.
local function migrateOverrideColumns()
    local ok, columns = execute(
        Store.connection,
        "PRAGMA table_info(map_entity_metadata)"
    )
    if not ok then
        return false, "metadata_schema_read_failed"
    end
    local present = {}
    for _, column in ipairs(columns) do
        present[column.name] = true
    end
    local steps = {}
    for _, addition in ipairs(missingOverrideColumns()) do
        steps[#steps + 1] = {
            "ALTER TABLE map_entity_metadata ADD COLUMN "
                .. addition.name .. " " .. addition.declaration,
        }
        local backfill = OVERRIDE_BACKFILL[addition.name]
        if backfill and present[backfill.from] then
            steps[#steps + 1] = {backfill.statement}
        end
    end
    return transaction(Store.connection, steps)
end

--- Throw away the `coronaOpacity` a schema that no longer exists wrote down.
--
-- The owner's database carries one. A build that never reached this trunk
-- stored it, the setting was not in the schema afterwards, and every start
-- since has logged `discarded_stored_setting: coronaOpacity
-- (settings.error.unknown)` and fallen back to the default -- correctly, since
-- nothing knew what the key meant.
--
-- Ticket 04 gives the key a meaning again, and that is the moment the stored
-- value stops being discarded and becomes the value in force. It is worth
-- nothing: it describes a build nobody kept, at a default nobody chose, and on
-- the owner's disk it is 0.2 against a shipped 0.6 -- a corona so faint the
-- feature would read as not working. A value whose schema was deleted is not a
-- preference; it is a leftover, and the shipped default is the honest answer
-- until somebody chooses otherwise.
--
-- One key rather than "everything the schema does not know": that is the row
-- this build can name as stale. A blanket sweep would also delete a setting a
-- *newer* build stored, which is data this one has no business reading, let
-- alone removing.
local function migrateVersionEight()
    local steps = {}
    -- `user_settings` is created by `ensureChangeHistorySchema`, which runs
    -- after migrations do, so a database old enough not to have it yet has no
    -- row to retire -- and a DELETE against a table that does not exist would
    -- roll the whole step back and refuse to start the server.
    if tableExists("user_settings") then
        table.insert(steps, {
            "DELETE FROM user_settings WHERE setting_key = ?",
            {"coronaOpacity"},
        })
    end
    table.insert(steps, {
        "UPDATE schema_meta SET version = ? WHERE singleton = 1",
        {8},
    })
    return transaction(Store.connection, steps)
end

local MIGRATIONS = {
    {
        id = "rotation_columns",
        from = 1,
        to = 2,
        apply = migrateVersionOne,
    },
    {
        id = "spatial_links",
        from = 2,
        to = 3,
        apply = migrateVersionTwo,
    },
    {
        id = "map_entity_types",
        from = 3,
        needed = needsEntityTypeMigration,
        apply = rebuildMapEntities,
    },
    {
        id = "identity_collisions_table",
        from = 3,
        needed = function()
            return not tableExists("identity_collisions")
        end,
        apply = migrateIdentityCollisionTable,
    },
    {
        id = "spatial_link_card_missing",
        from = 3,
        to = 4,
        apply = migrateVersionFour,
    },
    {
        id = "map_entity_marker_type",
        from = 4,
        to = 5,
        apply = migrateVersionFive,
    },
    {
        id = "review_mode_setting",
        from = 5,
        to = 6,
        apply = migrateVersionSix,
    },
    {
        id = "drop_map_preferences",
        from = 6,
        to = 7,
        apply = migrateVersionSeven,
    },
    {
        id = "retire_orphaned_corona_opacity",
        from = 7,
        to = 8,
        apply = migrateVersionEight,
    },
    -- A shape repair, and last: it probes the shape rather than the number, so
    -- it applies to any database whose metadata table predates a column and
    -- clears itself once it has run. It covers every override the schema
    -- declares, which is why it is not named after any one of them: the next
    -- setting to gain an override is added to the schema and repaired here
    -- without this list changing.
    {
        id = "entity_override_columns",
        from = 1,
        needed = needsOverrideColumns,
        apply = migrateOverrideColumns,
    },
}

local function nextMigration(version)
    for _, migration in ipairs(MIGRATIONS) do
        local applies = version >= migration.from
            and (migration.to == nil or version < migration.to)
        if applies and (migration.needed == nil or migration.needed()) then
            return migration
        end
    end
    return nil
end

local function runMigrations(version)
    -- Bounded so a repair whose `needed` probe never clears is a reported
    -- failure rather than a server that hangs on start.
    for _ = 1, #MIGRATIONS * 2 do
        local migration = nextMigration(version)
        if not migration then
            return version
        end
        local applied, applyError = migration.apply()
        if not applied then
            return false, tostring(migration.id) .. ": " .. tostring(applyError)
        end
        version = readSchemaVersion(Store.connection)
        if not version then
            return false, tostring(migration.id) .. ": schema_version_unreadable"
        end
    end
    return false, "migration_did_not_converge"
end

local function ensureTracerEntity()
    return transaction(Store.connection, {
        {
            [[
                INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)
                VALUES (?, ?, ?)
            ]],
            {
                TRACER_MAP.mapId,
                TRACER_MAP.resourceName,
                TRACER_MAP.mapName,
            },
        },
        {
            [[
                INSERT OR IGNORE INTO map_entities (
                    map_id, entity_id, entity_type, model,
                    authored_x, authored_y, authored_z,
                    rotation_x, rotation_y, rotation_z,
                    interior, dimension
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ]],
            {
                TRACER_ENTITY.mapId,
                TRACER_ENTITY.entityId,
                TRACER_ENTITY.entityType,
                TRACER_ENTITY.model,
                TRACER_ENTITY.authoredX,
                TRACER_ENTITY.authoredY,
                TRACER_ENTITY.authoredZ,
                TRACER_ENTITY.rotationX,
                TRACER_ENTITY.rotationY,
                TRACER_ENTITY.rotationZ,
                TRACER_ENTITY.interior,
                TRACER_ENTITY.dimension,
            },
        },
    })
end

local function ensureTicket07Entities()
    local steps = {
        {
            [[
                INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)
                VALUES (?, ?, ?)
            ]],
            {
                TICKET07_MAP.mapId,
                TICKET07_MAP.resourceName,
                TICKET07_MAP.mapName,
            },
        },
    }
    for _, entity in ipairs(TICKET07_ENTITIES) do
        table.insert(steps, {
            [[
                INSERT OR IGNORE INTO map_entities (
                    map_id, entity_id, entity_type, model,
                    authored_x, authored_y, authored_z,
                    rotation_x, rotation_y, rotation_z,
                    interior, dimension
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ]],
            {
                TICKET07_MAP.mapId,
                entity.entityId,
                entity.entityType,
                entity.model,
                entity.authoredX,
                entity.authoredY,
                entity.authoredZ,
                entity.rotationX,
                entity.rotationY,
                entity.rotationZ,
                0,
                0,
            },
        })
    end
    return transaction(Store.connection, steps)
end

--- Stop, keep everything, and hand the decision to the user.
--
-- This is the whole point of the ticket. A damaged database is not repaired
-- here, not replaced here and not rolled back here: the file is left exactly as
-- it was found, and what the user gets is the list of copies that survived
-- verification plus whatever has already been kept for diagnosis.
local function enterRecovery(reason, detail)
    Store.ready = false
    Store.errorCategory = "database_corrupt"
    Store.errorMessage = tostring(detail)
    Store.recoveryState = {
        state = "recovery",
        reason = reason,
        detail = tostring(detail),
        databasePath = DATABASE_PATH,
        awaitingChoice = true,
        backups = ANKIGTA.Backup.list(),
        quarantine = ANKIGTA.Backup.quarantined(),
    }
    outputDebugString(
        "[ANKIGTA] database_recovery reason=" .. tostring(reason)
            .. " detail=" .. tostring(detail),
        1
    )
    return false
end

--- Is this file still a database, or only a file where one used to be?
-- Answered before anything is created, migrated or written, because every one
-- of those would be a change to a file that must not be changed.
local function damageReport(connection)
    local ok, rows = execute(connection, "PRAGMA integrity_check")
    if not ok then
        return tostring(rows)
    end
    if not rows[1] then
        return "integrity_check_returned_nothing"
    end
    if rows[1].integrity_check ~= "ok" then
        return tostring(rows[1].integrity_check)
    end
    return nil
end

--- The tables the current schema has to be able to answer for.
local function structureReport(connection)
    for _, name in ipairs({"schema_meta", "maps", "map_entities", "spatial_links"}) do
        local readable = execute(connection, "SELECT 1 FROM " .. name .. " LIMIT 1")
        if not readable then
            return "table_unreadable:" .. name
        end
    end
    local checked, violations = execute(connection, "PRAGMA foreign_key_check")
    if not checked then
        return "constraint_check_failed"
    end
    if violations[1] then
        return "constraints_violated"
    end
    return nil
end

function Store.open()
    Store.ready = false
    Store.errorCategory = nil
    Store.errorMessage = nil
    Store.schemaVersion = nil
    Store.historyReady = false
    Store.recoveryState = nil

    ANKIGTA.Backup.configure({
        databasePath = DATABASE_PATH,
        currentSchemaVersion = CURRENT_SCHEMA_VERSION,
    })
    local interrupted = ANKIGTA.Backup.recoverInterrupted()
    if interrupted and interrupted.phase ~= "completed" then
        -- A restore that did not finish is a state to report, not one to guess
        -- at: both the original and the copy are still on disk under the names
        -- the journal names, and which of them the user wants is their call.
        return enterRecovery("restore_interrupted", interrupted.phase)
    end

    Store.connection = connect(DATABASE_PATH)
    if not Store.connection then
        return fail("database_open_failed", DATABASE_PATH)
    end

    local damage = damageReport(Store.connection)
    if damage then
        closeConnection()
        return enterRecovery("database_corrupt", damage)
    end

    local foreignKeysOk, foreignKeysError = enableForeignKeys(Store.connection)
    if not foreignKeysOk then
        closeConnection()
        return fail("database_configuration_failed", foreignKeysError)
    end

    if not hasSchema(Store.connection) then
        local created, createError = createCurrentSchema(Store.connection)
        if not created then
            closeConnection()
            return fail("schema_create_failed", createError)
        end
        local collisionsCreated, collisionsError =
            ensureIdentityCollisionTable()
        if not collisionsCreated then
            closeConnection()
            return fail("schema_create_failed", collisionsError)
        end
    else
        local version = readSchemaVersion(Store.connection)
        if not version then
            closeConnection()
            return fail("unsupported_schema_version", "unreadable")
        end
        if version > CURRENT_SCHEMA_VERSION then
            -- A database written by a newer build. Guessing at it would be a
            -- write to data this build does not understand.
            closeConnection()
            return fail("unsupported_schema_version", tostring(version))
        end
        if nextMigration(version) then
            -- No verified copy, no migration. A migration that runs anyway is
            -- the one case where a failure has nothing to fall back on.
            local backup, backupError = ANKIGTA.Backup.createPreMigration()
            if not backup then
                closeConnection()
                return fail("migration_backup_failed", backupError)
            end
            local migrated, migrationError = runMigrations(version)
            if not migrated then
                closeConnection()
                return fail("migration_failed", migrationError)
            end
            version = migrated
        end
        if version ~= CURRENT_SCHEMA_VERSION then
            closeConnection()
            return fail("unsupported_schema_version", tostring(version))
        end
        local structure = structureReport(Store.connection)
        if structure then
            closeConnection()
            return enterRecovery("database_corrupt", structure)
        end
    end

    local historyCreated, historyError = ensureChangeHistorySchema()
    if not historyCreated then
        closeConnection()
        return fail("history_schema_failed", historyError)
    end

    Store.schemaVersion = readSchemaVersion(Store.connection)
    if Store.schemaVersion ~= CURRENT_SCHEMA_VERSION then
        closeConnection()
        return fail("schema_verification_failed", tostring(Store.schemaVersion))
    end

    if Store.seedTracerFixtures then
        local seeded, seedError = ensureTracerEntity()
        if not seeded then
            closeConnection()
            return fail("tracer_entity_create_failed", seedError)
        end
    end

    Store.ready = true
    return true
end

function Store.markEntityIdentityCollision(mapId, entityId, reason)
    if not Store.ready or type(mapId) ~= "string" or type(entityId) ~= "string" then
        return false, "invalid_identity_collision"
    end
    local ok, errorMessage = execute(
        Store.connection,
        [[
            INSERT OR REPLACE INTO identity_collisions
                (map_id, entity_id, reason, detected_at)
            VALUES (?, ?, ?, ?)
        ]],
        mapId,
        entityId,
        reason or "identity_collision",
        getTickCount()
    )
    if not ok then
        return false, errorMessage
    end
    return true
end

--- Is this Map Entity blocked on a copy decision?
--
-- Per entity, never per map. A map-wide flag used to be consulted first, so
-- one entity's collision painted every row of the map with the Original /
-- New copy buttons -- and on those borrowed rows both buttons answer
-- `identity_collision_not_found`, because no collision was ever recorded
-- against them. `recoverPersistedCollisions` re-armed the flag on every start,
-- so the state outlived the thing that caused it.
function Store.isIdentityCollision(mapId, entityId)
    if type(mapId) ~= "string" then
        return false
    end
    if not Store.ready then
        return false
    end
    local ok, rows = execute(
        Store.connection,
        "SELECT 1 FROM identity_collisions WHERE map_id = ? AND (? IS NULL OR entity_id = ?)",
        mapId,
        entityId,
        entityId
    )
    return ok and rows[1] ~= nil
end

--- The same answer, taken off a row the caller has already read.
--
-- `isIdentityCollision` is one query. That is the right shape for a caller
-- holding nothing but an id, and the wrong one for a caller walking every Map
-- Entity in the world: the F7 snapshot asked it once per entity, so opening F7
-- over the reference world issued ten thousand queries and spent about half of
-- its two-second budget on them.
--
-- The reads that walk many rows carry the answer as a column, so this is a
-- lookup rather than a query. A row from a read that does not carry it says so
-- by having no such key at all -- MTA turns SQL NULL into `false`, never into
-- nil -- and is asked the slow way rather than being assumed innocent.
function Store.rowIsIdentityCollision(row)
    if type(row) ~= "table" or type(row.map_id) ~= "string" then
        return false
    end
    if row.identity_collision == nil then
        return Store.isIdentityCollision(row.map_id, row.entity_id)
    end
    return tonumber(row.identity_collision) == 1
end

function Store.listIdentityCollisions()
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    -- Joined rather than keyed: the only caller rebuilds the whole collision
    -- record from this row on resource start, and it needs the map's locator,
    -- the entity's type and the link it was blocking. Returning the key alone
    -- left it concatenating a nil map name into a path -- on every start, for
    -- any user who had ever had a collision, aborting `onResourceStart` before
    -- the presence refresh and the authorization broadcast ran.
    local ok, rows = execute(
        Store.connection,
        [[
            SELECT
                identity_collisions.map_id,
                identity_collisions.entity_id,
                identity_collisions.reason,
                maps.resource_name,
                maps.map_name,
                map_entities.entity_type,
                spatial_links.collection_uuid,
                spatial_links.card_id,
                spatial_links.verified_map_sha256
            FROM identity_collisions
            INNER JOIN maps
                ON maps.map_id = identity_collisions.map_id
            INNER JOIN map_entities
                ON map_entities.map_id = identity_collisions.map_id
                AND map_entities.entity_id = identity_collisions.entity_id
            LEFT JOIN spatial_links
                ON spatial_links.map_id = identity_collisions.map_id
                AND spatial_links.entity_id = identity_collisions.entity_id
            ORDER BY identity_collisions.map_id, identity_collisions.entity_id
        ]]
    )
    if not ok then
        return false, "identity_collision_read_failed"
    end
    return rows
end

function Store.clearEntityIdentityCollision(mapId, entityId)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local ok, errorMessage = execute(
        Store.connection,
        "DELETE FROM identity_collisions WHERE map_id = ? AND entity_id = ?",
        mapId,
        entityId
    )
    if not ok then
        return false, errorMessage
    end
    return true
end

--- Forget a Map Entity the player deleted from the map.
--
-- Everything ANKIGTA holds about it goes: the entity, its metadata and the
-- Spatial Link it carried. This is the one place a Map Entity is removed
-- rather than marked, and it happens only because somebody asked -- the row
-- was deleted from the map, ANKIGTA said so, and the player answered.
--
-- Recorded in Change History, so an answer given too quickly is one Undo away.
function Store.forgetMapEntity(mapId, entityId)
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local row, readError = Store.getMapEntity(mapId, entityId)
    if not row then
        return false, readError or "entity_missing"
    end
    local ok, entityRows = execute(
        Store.connection,
        [[
            SELECT entity_type, model, authored_x, authored_y, authored_z,
                   rotation_x, rotation_y, rotation_z, interior, dimension
            FROM map_entities WHERE map_id = ? AND entity_id = ?
        ]],
        mapId,
        entityId
    )
    if not ok or not entityRows[1] then
        return false, "entity_read_failed"
    end
    local stored = entityRows[1]
    local before = {
        entity = {
            entityType = stored.entity_type,
            model = stored.model,
            x = stored.authored_x,
            y = stored.authored_y,
            z = stored.authored_z,
            rotationX = stored.rotation_x,
            rotationY = stored.rotation_y,
            rotationZ = stored.rotation_z,
            interior = stored.interior,
            dimension = stored.dimension,
        },
        -- Absent, not 3, where the entity has no radius of its own -- and the
        -- same for every other override. `or 3` would record "it followed the
        -- global" as "it was pinned at the global's current value", and Undo
        -- would put back the second.
        metadata = Store.metadataOf(row),
        link = row.link_state and {
            collectionUuid = row.collection_uuid,
            cardId = tonumber(row.card_id),
            state = row.link_state,
            verifiedMapSha256 = row.verified_map_sha256,
        } or nil,
    }
    return historyTransaction(
        "forget_map_entity",
        historyTarget(mapId, entityId),
        before,
        {},
        {
            {
                "DELETE FROM spatial_links WHERE map_id = ? AND entity_id = ?",
                {mapId, entityId},
            },
            {
                "DELETE FROM identity_collisions"
                    .. " WHERE map_id = ? AND entity_id = ?",
                {mapId, entityId},
            },
            {
                "DELETE FROM map_entity_metadata"
                    .. " WHERE map_id = ? AND entity_id = ?",
                {mapId, entityId},
            },
            {
                "DELETE FROM map_entities WHERE map_id = ? AND entity_id = ?",
                {mapId, entityId},
            },
        }
    )
end

function Store.createMapEntityCopy(
    oldMapId,
    oldEntityId,
    newMapId,
    newEntityId
)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local existing, readError = Store.getMapEntity(oldMapId, oldEntityId)
    if not existing then
        return false, readError
    end
    return transaction(Store.connection, {
        {
            "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name) VALUES (?, ?, ?)",
            {
                newMapId,
                existing.resource_name,
                existing.map_name,
            },
        },
        {
            [[
                INSERT INTO map_entities (
                    map_id, entity_id, entity_type, model,
                    authored_x, authored_y, authored_z,
                    rotation_x, rotation_y, rotation_z,
                    interior, dimension
                )
                SELECT ?, ?, entity_type, model,
                       authored_x, authored_y, authored_z,
                       rotation_x, rotation_y, rotation_z,
                       interior, dimension
                FROM map_entities
                WHERE map_id = ? AND entity_id = ?
            ]],
            {newMapId, newEntityId, oldMapId, oldEntityId},
        },
    })
end

--- Take in an object that already has a durable name of its own.
--
-- Nothing is written into anybody's `.map` file. An element loaded from one
-- carries the file's `id` attribute, which is exactly the durable identity the
-- store needs, so adoption is only a matter of writing down what the object
-- already is: which resource owns it, what it is called there, and where it
-- was authored. `me:ID` is not required and cannot be -- the stock Map Editor
-- writes that only while the map is open in it, and a player in freeroam is
-- not in it.
function Store.adoptMapEntity(value)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(value) ~= "table"
        or type(value.mapId) ~= "string" or value.mapId == ""
        or type(value.entityId) ~= "string" or value.entityId == ""
        or type(value.resourceName) ~= "string" or value.resourceName == ""
    then
        return false, "invalid_map_entity"
    end
    -- Read from the shared table rather than listed here. Listed here, it was
    -- the one place a marker was not a Map Entity: the schema's own CHECK has
    -- admitted one since version 5, the world scan finds them, Pick Entity
    -- offers them and the spatial poll follows them -- and adoption still
    -- refused, so a marker could be pointed at and never taken in. It could
    -- not be named, and had no row to carry a radius or a corona.
    if not ANKIGTA.EntityTypes.supported[value.entityType] then
        return false, "target_type_not_supported"
    end
    local existing = Store.getMapEntity(value.mapId, value.entityId)
    if existing then
        return existing
    end
    local written, writeError = transaction(Store.connection, {
        {
            "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
                .. " VALUES (?, ?, ?)",
            {value.mapId, value.resourceName, value.mapName or value.mapId},
        },
        {
            [[
                INSERT INTO map_entities (
                    map_id, entity_id, entity_type, model,
                    authored_x, authored_y, authored_z,
                    rotation_x, rotation_y, rotation_z,
                    interior, dimension
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ]],
            {
                value.mapId,
                value.entityId,
                value.entityType,
                math.floor(tonumber(value.model) or 0),
                tonumber(value.x) or 0,
                tonumber(value.y) or 0,
                tonumber(value.z) or 0,
                tonumber(value.rotationX) or 0,
                tonumber(value.rotationY) or 0,
                tonumber(value.rotationZ) or 0,
                math.floor(tonumber(value.interior) or 0),
                math.floor(tonumber(value.dimension) or 0),
            },
        },
    })
    if not written then
        return false, writeError
    end
    return Store.getMapEntity(value.mapId, value.entityId)
end

function Store.updateMapLocator(mapId, mapLocator)
    if not Store.ready
        or type(mapId) ~= "string"
        or type(mapLocator) ~= "table"
    then
        return false, "invalid_map_locator"
    end
    local current, readError = Store.mapIdentityOwner(mapId, mapLocator)
    if current == false then
        return false, readError
    end
    if not current then
        return false, "map_identity_not_found"
    end
    return historyTransaction(
        "map_locator",
        jsonEncode({mapId = mapId}),
        current,
        {
            resourceName = mapLocator.resourceName,
            mapFile = mapLocator.mapFile,
        },
        {
            {
                "UPDATE maps SET resource_name = ?, map_name = ? WHERE map_id = ?",
                {
                    mapLocator.resourceName,
                    mapLocator.mapFile,
                    mapId,
                },
            },
        }
    )
end

function Store.close()
    closeConnection()
    Store.ready = false
    Store.historyReady = false
end

local function applyHistoryStateSteps(operation, target, state)
    local steps = {}
    if operation == "spatial_link" then
        if type(target) ~= "table"
            or type(target.mapId) ~= "string"
            or type(target.entityId) ~= "string"
        then
            return false, "invalid_history_target"
        end
        local mapLocator = type(state) == "table" and state.mapLocator or nil
        if type(mapLocator) == "table" then
            table.insert(steps, {
                "UPDATE maps SET resource_name = ?, map_name = ? WHERE map_id = ?",
                {mapLocator.resourceName, mapLocator.mapFile, target.mapId},
            })
        end
        table.insert(
            steps,
            {
                "DELETE FROM spatial_links WHERE map_id = ? AND entity_id = ?",
                {target.mapId, target.entityId},
            }
        )
        local link = type(state) == "table" and state.link or nil
        if type(link) == "table" then
            table.insert(
                steps,
                {
                    [[
                        INSERT INTO spatial_links (
                            map_id, entity_id, collection_uuid, card_id,
                            state, verified_map_sha256
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    ]],
                    {
                        target.mapId,
                        target.entityId,
                        link.collectionUuid,
                        tonumber(link.cardId),
                        link.state or "active",
                        link.verifiedMapSha256,
                    },
                }
            )
        end
    elseif operation == "relink_entity" then
        if type(state) ~= "table"
            or type(state.source) ~= "table"
            or type(state.target) ~= "table"
            or type(target) ~= "table"
        then
            return false, "invalid_history_target"
        end
        local sourceId = target
        local sourceRow = state.source
        local targetRow = state.target
        local sourceMapId = sourceId.mapId
        local sourceEntityId = sourceId.entityId
        local targetMapId = targetRow.map_id or targetRow.mapId
        local targetEntityId = targetRow.entity_id or targetRow.entityId
        if type(targetMapId) ~= "string" or type(targetEntityId) ~= "string" then
            return false, "invalid_history_target"
        end
        table.insert(steps, {
            "DELETE FROM spatial_links WHERE map_id = ? AND entity_id = ?",
            {sourceMapId, sourceEntityId},
        })
        table.insert(steps, {
            "DELETE FROM spatial_links WHERE map_id = ? AND entity_id = ?",
            {targetMapId, targetEntityId},
        })
        if state.phase == "before" then
            if sourceRow.entity_id or sourceRow.entityId then
                for _, step in ipairs(metadataStepsFromRow(
                    sourceMapId,
                    sourceEntityId,
                    sourceRow,
                    sourceRow.entity_state or "entity_missing"
                )) do
                    table.insert(steps, step)
                end
            end
            if targetRow.entity_id or targetRow.entityId then
                for _, step in ipairs(metadataStepsFromRow(
                    targetMapId,
                    targetEntityId,
                    targetRow,
                    targetRow.entity_state or "identified"
                )) do
                    table.insert(steps, step)
                end
            end
            local sourceIdentity = sourceRow.collection_uuid and {
                collectionUuid = sourceRow.collection_uuid,
                cardId = tonumber(sourceRow.card_id),
                state = sourceRow.link_state or "active",
                verifiedMapSha256 = sourceRow.verified_map_sha256,
            } or nil
            if sourceIdentity then
                table.insert(steps, {
                    [[
                        INSERT INTO spatial_links (
                            map_id, entity_id, collection_uuid, card_id,
                            state, verified_map_sha256
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    ]],
                    {
                        sourceMapId,
                        sourceEntityId,
                        sourceIdentity.collectionUuid,
                        sourceIdentity.cardId,
                        sourceIdentity.state,
                        sourceIdentity.verifiedMapSha256,
                    },
                })
            end
            if targetRow.link_state == "active"
                or targetRow.link_state == "card_missing"
            then
                table.insert(steps, {
                    [[
                        INSERT INTO spatial_links (
                            map_id, entity_id, collection_uuid, card_id,
                            state, verified_map_sha256
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    ]],
                    {
                        targetMapId,
                        targetEntityId,
                        targetRow.collection_uuid,
                        tonumber(targetRow.card_id),
                        targetRow.link_state,
                        targetRow.verified_map_sha256,
                    },
                })
            end
        else
            local identity = targetRow.collectionUuid and targetRow or nil
            -- The recorded state names the overrides flat beside the identity,
            -- so they are read back the same way -- by the schema's field names
            -- rather than by a list written out here, which is what an entry
            -- recorded by a later build would not match.
            local moved = {
                name = targetRow.entityName,
                entityTag = targetRow.entityTag,
                presenceState = "identified",
                -- Read for its own sake: an entry recorded before ticket 04
                -- renamed the flag says `showRadius`, and it is exactly those
                -- that Undo exists to put back.
                showRadius = targetRow.showRadius,
            }
            for _, setting in ipairs(overridableSettings()) do
                moved[setting.field] = targetRow[setting.field]
            end
            addMetadataSteps(steps, targetMapId, targetEntityId, moved)
            table.insert(steps, {
                "UPDATE map_entity_metadata SET presence_state = 'entity_missing' "
                    .. "WHERE map_id = ? AND entity_id = ?",
                {sourceMapId, sourceEntityId},
            })
            if identity then
                table.insert(steps, {
                    [[
                        INSERT INTO spatial_links (
                            map_id, entity_id, collection_uuid, card_id,
                            state, verified_map_sha256
                        ) VALUES (?, ?, ?, ?, 'active', ?)
                    ]],
                    {
                        targetMapId,
                        targetEntityId,
                        identity.collectionUuid,
                        tonumber(identity.cardId),
                        identity.verifiedMapSha256,
                    },
                })
            end
        end
    elseif operation == "forget_map_entity" then
        if type(target) ~= "table"
            or type(target.mapId) ~= "string"
            or type(target.entityId) ~= "string"
            or type(state) ~= "table"
        then
            return false, "invalid_history_target"
        end
        table.insert(steps, {
            "DELETE FROM spatial_links WHERE map_id = ? AND entity_id = ?",
            {target.mapId, target.entityId},
        })
        table.insert(steps, {
            "DELETE FROM map_entity_metadata WHERE map_id = ? AND entity_id = ?",
            {target.mapId, target.entityId},
        })
        table.insert(steps, {
            "DELETE FROM identity_collisions WHERE map_id = ? AND entity_id = ?",
            {target.mapId, target.entityId},
        })
        table.insert(steps, {
            "DELETE FROM map_entities WHERE map_id = ? AND entity_id = ?",
            {target.mapId, target.entityId},
        })
        local entity = state.entity
        if type(entity) == "table" then
            table.insert(steps, {
                [[
                    INSERT INTO map_entities (
                        map_id, entity_id, entity_type, model,
                        authored_x, authored_y, authored_z,
                        rotation_x, rotation_y, rotation_z,
                        interior, dimension
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ]],
                {
                    target.mapId, target.entityId, entity.entityType,
                    tonumber(entity.model) or 0,
                    tonumber(entity.x) or 0,
                    tonumber(entity.y) or 0,
                    tonumber(entity.z) or 0,
                    tonumber(entity.rotationX) or 0,
                    tonumber(entity.rotationY) or 0,
                    tonumber(entity.rotationZ) or 0,
                    tonumber(entity.interior) or 0,
                    tonumber(entity.dimension) or 0,
                },
            })
        end
        local metadata = state.metadata
        if type(metadata) == "table" then
            -- The insert fills the NOT NULL legacy column and the override
            -- step is the one anything reads. Without the second, undoing a
            -- removal brings the entity back following the global, whatever
            -- radius it had.
            addMetadataSteps(steps, target.mapId, target.entityId, metadata)
        end
        local link = state.link
        if type(link) == "table" then
            table.insert(steps, {
                [[
                    INSERT INTO spatial_links (
                        map_id, entity_id, collection_uuid, card_id,
                        state, verified_map_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ]],
                {
                    target.mapId, target.entityId,
                    link.collectionUuid, tonumber(link.cardId),
                    link.state or "active", link.verifiedMapSha256,
                },
            })
        end
    elseif operation == "map_locator" then
        if type(target) ~= "table" or type(target.mapId) ~= "string"
            or type(state) ~= "table"
        then
            return false, "invalid_history_target"
        end
        table.insert(steps, {
            "UPDATE maps SET resource_name = ?, map_name = ? WHERE map_id = ?",
            {state.resourceName, state.mapFile, target.mapId},
        })
    elseif operation == "entity_metadata" then
        if type(target) ~= "table"
            or type(target.mapId) ~= "string"
            or type(target.entityId) ~= "string"
            or type(state) ~= "table"
        then
            return false, "invalid_history_target"
        end
        if state.exists == false then
            table.insert(steps, {
                "DELETE FROM map_entity_metadata WHERE map_id = ? AND entity_id = ?",
                {target.mapId, target.entityId},
            })
        else
            -- Undo has to put back "it followed the global" as faithfully as
            -- it puts back a number, or one Undo quietly pins an entity to
            -- whatever the global happened to say -- and the same holds for a
            -- corona colour and opacity the entity did not have.
            addMetadataSteps(steps, target.mapId, target.entityId, state)
        end
    elseif operation == "clear_entity_overrides" then
        if type(target) ~= "table" or type(target.settingKey) ~= "string"
            or type(state) ~= "table"
        then
            return false, "invalid_history_target"
        end
        local column = ANKIGTA.Settings.entityOverrideColumn(target.settingKey)
        if not column then
            return false, "invalid_history_target"
        end
        local definition = ANKIGTA.Settings.definition(target.settingKey)
        local kind = definition and definition.rule and definition.rule.kind
        -- Cleared first and then written back one row at a time, in both
        -- directions. Undo is not "put these back beside whatever is there
        -- now": the sweep is one decision over the whole world, so reversing
        -- it has to leave the world in the state it recorded, including the
        -- rows that had nothing of their own before it ran.
        table.insert(steps, {
            "UPDATE map_entity_metadata SET " .. column .. " = NULL",
        })
        for _, entry in ipairs(state.overrides or {}) do
            local stored = storedOverride(kind, entry.value)
            if stored ~= nil
                and type(entry.mapId) == "string"
                and type(entry.entityId) == "string"
            then
                table.insert(steps, {
                    "UPDATE map_entity_metadata SET " .. column .. " = ?"
                        .. " WHERE map_id = ? AND entity_id = ?",
                    {stored, entry.mapId, entry.entityId},
                })
            end
        end
    elseif operation == "user_setting" then
        if type(target) ~= "table" or type(target.settingKey) ~= "string"
            or type(state) ~= "table"
        then
            return false, "invalid_history_target"
        end
        if state.exists == false then
            table.insert(steps, {
                "DELETE FROM user_settings WHERE setting_key = ?",
                {target.settingKey},
            })
        else
            table.insert(steps, {
                "INSERT OR REPLACE INTO user_settings (setting_key, setting_value) VALUES (?, ?)",
                {target.settingKey, jsonEncode(state.value)},
            })
        end
    else
        return false, "unsupported_history_operation"
    end
    return steps
end

local function readHistoryEntry(whereClause, ...)
    local ok, rows = execute(
        Store.connection,
        [[
            SELECT
                history_id, operation, target, before_json, after_json, created_at
            FROM change_history
            WHERE ]] .. whereClause,
        ...
    )
    if not ok then
        return false, "history_read_failed"
    end
    return rows[1]
end

function Store.historyStatus()
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local ok, rows = execute(
        Store.connection,
        [[
            SELECT
                state.cursor_id AS cursor_id,
                (SELECT COUNT(*) FROM change_history) AS entry_count,
                (SELECT COUNT(*) FROM change_history future
                    WHERE future.history_id > state.cursor_id) AS redo_count
            FROM change_history_state state
            WHERE state.singleton = 1
        ]]
    )
    if not ok or not rows[1] then
        return false, "history_read_failed"
    end
    return {
        cursorId = tonumber(rows[1].cursor_id) or 0,
        entryCount = tonumber(rows[1].entry_count) or 0,
        canUndo = tonumber(rows[1].cursor_id) ~= nil
            and tonumber(rows[1].cursor_id) > 0,
        canRedo = tonumber(rows[1].redo_count) ~= nil
            and tonumber(rows[1].redo_count) > 0,
        limit = HISTORY_LIMIT,
    }
end

function Store.listChangeHistory()
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local ok, rows = execute(
        Store.connection,
        "SELECT history_id, operation, target, created_at "
            .. "FROM change_history ORDER BY history_id"
    )
    if not ok then
        return false, "history_read_failed"
    end
    return rows
end

function Store.recordChange(operation, target, before, after, mutationSteps)
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(operation) ~= "string" or type(target) ~= "table" then
        return false, "invalid_history_change"
    end
    local committed, errorMessage = historyTransaction(
        operation,
        jsonEncode(target),
        before,
        after,
        mutationSteps
    )
    if not committed then
        return false, "history_transaction_failed: " .. tostring(errorMessage)
    end
    return true
end

local function moveHistory(direction)
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local stateOk, stateRows = execute(
        Store.connection,
        "SELECT cursor_id FROM change_history_state WHERE singleton = 1"
    )
    if not stateOk or not stateRows[1] then
        return false, "history_read_failed"
    end
    local cursorId = tonumber(stateRows[1].cursor_id) or 0
    local entry
    local nextCursor
    if direction == "undo" then
        if cursorId == 0 then
            return false, "nothing_to_undo"
        end
        entry = readHistoryEntry("history_id = ?", cursorId)
        if not entry then
            return false, "history_entry_missing"
        end
        local previousOk, previousRows = execute(
            Store.connection,
            "SELECT COALESCE(MAX(history_id), 0) AS previous_id "
                .. "FROM change_history WHERE history_id < ?",
            cursorId
        )
        if not previousOk then
            return false, "history_read_failed"
        end
        nextCursor = tonumber(previousRows[1].previous_id) or 0
    else
        local nextOk, nextRows = execute(
            Store.connection,
            "SELECT cursor_id FROM change_history_state WHERE singleton = 1"
        )
        if not nextOk then
            return false, "history_read_failed"
        end
        local redoOk, redoRows = execute(
            Store.connection,
            "SELECT history_id FROM change_history WHERE history_id > ? "
                .. "ORDER BY history_id LIMIT 1",
            cursorId
        )
        if not redoOk or not redoRows[1] then
            return false, "nothing_to_redo"
        end
        local nextId = tonumber(redoRows[1].history_id)
        entry = readHistoryEntry("history_id = ?", nextId)
        if not entry then
            return false, "history_entry_missing"
        end
        nextCursor = nextId
    end

    local stateJson = direction == "undo" and entry.before_json or entry.after_json
    local state = jsonDecode(stateJson)
    local target = jsonDecode(entry.target)
    local applySteps, applyError =
        applyHistoryStateSteps(entry.operation, target, state)
    if not applySteps then
        return false, applyError
    end
    table.insert(applySteps, {
        "UPDATE change_history_state SET cursor_id = ? WHERE singleton = 1",
        {nextCursor},
    })
    local committed, errorMessage = transaction(Store.connection, applySteps)
    if not committed then
        return false, "history_move_failed: " .. tostring(errorMessage)
    end
    return true, entry
end

function Store.undo()
    return moveHistory("undo")
end

function Store.redo()
    return moveHistory("redo")
end

function Store.status()
    return {
        ready = Store.ready,
        schemaVersion = Store.schemaVersion or false,
        errorCategory = Store.errorCategory or false,
        recovery = Store.recoveryState or false,
    }
end

--- The recovery state, or `false` when there is nothing to recover from.
function Store.recovery()
    if not Store.recoveryState then
        return false
    end
    -- Re-read the copies each time: one may have been verified, deleted or
    -- restored since the state was entered.
    Store.recoveryState.backups = ANKIGTA.Backup.list()
    Store.recoveryState.quarantine = ANKIGTA.Backup.quarantined()
    return Store.recoveryState
end

--- Restore the copy the user chose, then open what came back.
--
-- The choice is the user's and arrives from the recovery screen; this only
-- makes sure nothing is holding the database file open while it is replaced,
-- and reports what the reopened database turned out to be.
function Store.restoreFromBackup(backupId)
    closeConnection()
    Store.ready = false
    Store.historyReady = false
    local restored, restoreError = ANKIGTA.Backup.restore(backupId)
    if not restored then
        -- Both the original and the copy are still on disk; the recovery state
        -- is refreshed so the screen shows what is left to choose from.
        return false, restoreError
    end
    local opened = Store.open()
    if not opened then
        return false, Store.errorCategory or "database_open_failed"
    end
    return {
        restored = restored.restored,
        quarantine = restored.quarantine,
        schemaVersion = Store.schemaVersion,
    }
end

local function ensureEntityMetadataRow(mapId, entityId)
    return execute(
        Store.connection,
        [[
            INSERT OR IGNORE INTO map_entity_metadata
                (map_id, entity_id, name, entity_tag, radius, show_radius, presence_state)
            VALUES (?, ?, '', '', 3, 0, 'identified')
        ]],
        mapId,
        entityId
    )
end

function Store.markEntityMissing(mapId, entityId)
    if not Store.ready
        or type(mapId) ~= "string"
        or type(entityId) ~= "string"
    then
        return false, "invalid_map_entity"
    end
    local ensured, ensureError = ensureEntityMetadataRow(mapId, entityId)
    if not ensured then
        return false, ensureError
    end
    return execute(
        Store.connection,
        [[
            UPDATE map_entity_metadata
            SET presence_state = 'entity_missing'
            WHERE map_id = ? AND entity_id = ?
        ]],
        mapId,
        entityId
    )
end

function Store.clearEntityMissing(mapId, entityId)
    if not Store.ready
        or type(mapId) ~= "string"
        or type(entityId) ~= "string"
    then
        return false, "invalid_map_entity"
    end
    local ensured, ensureError = ensureEntityMetadataRow(mapId, entityId)
    if not ensured then
        return false, ensureError
    end
    return execute(
        Store.connection,
        [[
            UPDATE map_entity_metadata
            SET presence_state = 'identified'
            WHERE map_id = ? AND entity_id = ?
        ]],
        mapId,
        entityId
    )
end

--- How much is stored, against the volume the response times are promised for.
--
-- Being over the reference volume changes nothing about how data is stored,
-- read or written: it is not a cap, and nothing here truncates, refuses or
-- prunes. It only means the times in ticket 30 are no longer promised, which is
-- worth saying out loud rather than leaving the player to conclude that a slow
-- F7 is a broken one.
function Store.volumeReport()
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local ok, rows = execute(
        Store.connection,
        [[
            SELECT
                (SELECT COUNT(*) FROM map_entities) AS map_entities,
                (SELECT COUNT(*) FROM spatial_links) AS spatial_links
        ]]
    )
    if not ok or not rows[1] then
        return false, "volume_read_failed"
    end
    local mapEntities = tonumber(rows[1].map_entities) or 0
    local spatialLinks = tonumber(rows[1].spatial_links) or 0
    local overReference = mapEntities > REFERENCE_MAP_ENTITIES
        or spatialLinks > REFERENCE_SPATIAL_LINKS
    if overReference and not Store.volumeWarned then
        -- Once per crossing: a warning repeated on every F7 open would be
        -- noise, and the state is readable from the report at any time.
        Store.volumeWarned = true
        outputDebugString(
            "[ANKIGTA] volume_over_reference"
                .. " mapEntities=" .. tostring(mapEntities)
                .. "/" .. tostring(REFERENCE_MAP_ENTITIES)
                .. " spatialLinks=" .. tostring(spatialLinks)
                .. "/" .. tostring(REFERENCE_SPATIAL_LINKS),
            2
        )
    elseif not overReference then
        Store.volumeWarned = false
    end
    return {
        mapEntities = mapEntities,
        spatialLinks = spatialLinks,
        referenceMapEntities = REFERENCE_MAP_ENTITIES,
        referenceSpatialLinks = REFERENCE_SPATIAL_LINKS,
        overReference = overReference,
    }
end

--- The override columns, as a projection for a SELECT over the join.
--
-- Generated, so a row read anywhere carries every override the schema declares.
-- A LEFT JOIN that finds no metadata row answers NULL for each of them, which
-- is the same thing a metadata row with nothing of its own says -- so an entity
-- nobody has ever touched follows every global by the join alone.
local function overrideProjection()
    local parts = {}
    for _, setting in ipairs(overridableSettings()) do
        parts[#parts + 1] = "map_entity_metadata." .. setting.column
    end
    return table.concat(parts, ", ")
end

function Store.listMapEntities()
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end

    local ok, rows = execute(
        Store.connection,
        "SELECT " .. overrideProjection() .. [[,
                maps.map_id,
                maps.resource_name,
                maps.map_name,
                map_entities.entity_id,
                map_entities.entity_type,
                map_entities.model,
                map_entities.authored_x,
                map_entities.authored_y,
                map_entities.authored_z,
                map_entities.rotation_x,
                map_entities.rotation_y,
                map_entities.rotation_z,
                map_entities.interior,
                map_entities.dimension,
                COALESCE(map_entity_metadata.name, '') AS entity_name,
                COALESCE(map_entity_metadata.entity_tag, '') AS entity_tag,
                -- No override is coalesced to anything: absent is a fact about
                -- the entity -- that it follows the global -- and inventing a
                -- value here is what made every row look like a decision
                -- somebody had taken.
                spatial_links.collection_uuid,
                spatial_links.card_id,
                spatial_links.state AS link_state,
                spatial_links.verified_map_sha256,
                COALESCE(map_entity_metadata.presence_state, 'identified')
                    AS entity_state,
                CASE WHEN identity_collisions.entity_id IS NULL THEN 0 ELSE 1 END
                    AS identity_collision
            FROM map_entities
            INNER JOIN maps ON maps.map_id = map_entities.map_id
            LEFT JOIN spatial_links
                ON spatial_links.map_id = map_entities.map_id
                AND spatial_links.entity_id = map_entities.entity_id
            LEFT JOIN map_entity_metadata
                ON map_entity_metadata.map_id = map_entities.map_id
                AND map_entity_metadata.entity_id = map_entities.entity_id
            -- Carried on the row rather than asked per entity: see
            -- `Store.rowIsIdentityCollision`.
            LEFT JOIN identity_collisions
                ON identity_collisions.map_id = map_entities.map_id
                AND identity_collisions.entity_id = map_entities.entity_id
            ORDER BY maps.map_id, map_entities.entity_id
        ]]
    )
    if not ok then
        return false, "entity_read_failed"
    end
    return rows
end

function Store.singleMapEntity(entityType, entityElement)
    local rows, readError = Store.listMapEntities()
    if not rows then
        return false, readError
    end
    if type(entityType) == "string" then
        local matching = {}
        for _, row in ipairs(rows) do
            if row.entity_type == entityType then
                table.insert(matching, row)
            end
        end
        rows = matching
    end
    if type(entityType) == "string" and isElement(entityElement) then
        local persistentId = getElementData(entityElement, "ankigtaEntityId")
        local editorId = getElementData(entityElement, "me:ID")
        local keyed = {}
        for _, row in ipairs(rows) do
            if (persistentId and persistentId ~= "" and row.entity_id == persistentId)
                or (editorId and editorId ~= "" and row.entity_id == editorId)
            then
                table.insert(keyed, row)
            end
        end
        if #keyed > 0 then
            rows = keyed
        end
    end
    if #rows == 0 and (entityType == "vehicle" or entityType == "ped") then
        local seeded, seedError = ensureTicket07Entities()
        if not seeded then
            return false, seedError
        end
        rows, readError = Store.listMapEntities()
        if not rows then
            return false, readError
        end
        local matching = {}
        for _, row in ipairs(rows) do
            if row.entity_type == entityType then
                table.insert(matching, row)
            end
        end
        if isElement(entityElement) then
            local editorId = getElementData(entityElement, "me:ID")
            local keyed = {}
            for _, row in ipairs(matching) do
                if editorId and row.entity_id == editorId then
                    table.insert(keyed, row)
                end
            end
            if #keyed > 0 then
                matching = keyed
            end
        end
        rows = matching
    end
    if #rows ~= 1 then
        return false, "single_map_entity_required"
    end
    return rows[1]
end

function Store.getMapEntity(mapId, entityId)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(mapId) ~= "string" or type(entityId) ~= "string"
        or mapId == "" or entityId == ""
    then
        return false, "invalid_map_entity"
    end
    local ok, rows = execute(
        Store.connection,
        "SELECT " .. overrideProjection() .. [[,
                maps.map_id,
                maps.resource_name,
                maps.map_name,
                map_entities.entity_id,
                map_entities.entity_type,
                -- Where the map says the entity stands. Teleport falls back to
                -- this whenever no Runtime Instance is loaded, and without it
                -- every teleport to an unloaded entity refused as
                -- `invalid_target` -- which is exactly the case teleport
                -- exists for. Position, interior and dimension only: the
                -- teleport snapshot is those five, and a row read here is
                -- copied into Change History by relink.
                map_entities.authored_x,
                map_entities.authored_y,
                map_entities.authored_z,
                map_entities.interior,
                map_entities.dimension,
                map_entity_metadata.name AS entity_name,
                map_entity_metadata.entity_tag AS entity_tag,
                spatial_links.collection_uuid,
                spatial_links.card_id,
                spatial_links.state AS link_state,
                spatial_links.verified_map_sha256,
                COALESCE(map_entity_metadata.presence_state, 'identified')
                    AS entity_state,
                CASE WHEN identity_collisions.entity_id IS NULL THEN 0 ELSE 1 END
                    AS identity_collision
            FROM map_entities
            INNER JOIN maps ON maps.map_id = map_entities.map_id
            LEFT JOIN spatial_links
                ON spatial_links.map_id = map_entities.map_id
                AND spatial_links.entity_id = map_entities.entity_id
            LEFT JOIN map_entity_metadata
                ON map_entity_metadata.map_id = map_entities.map_id
                AND map_entity_metadata.entity_id = map_entities.entity_id
            LEFT JOIN identity_collisions
                ON identity_collisions.map_id = map_entities.map_id
                AND identity_collisions.entity_id = map_entities.entity_id
            WHERE map_entities.map_id = ? AND map_entities.entity_id = ?
        ]],
        mapId,
        entityId
    )
    if not ok then
        return false, "entity_read_failed"
    end
    if not rows[1] then
        return false, "map_entity_not_found"
    end
    return rows[1]
end

function Store.relinkEntity(value)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(value) ~= "table"
        or type(value.sourceMapId) ~= "string"
        or type(value.sourceEntityId) ~= "string"
        or type(value.targetMapId) ~= "string"
        or type(value.targetEntityId) ~= "string"
        or value.sourceMapId == ""
        or value.sourceEntityId == ""
        or value.targetMapId == ""
        or value.targetEntityId == ""
        or (
            value.sourceMapId == value.targetMapId
            and value.sourceEntityId == value.targetEntityId
        )
    then
        return false, "invalid_relink_request"
    end

    local source, sourceError = Store.getMapEntity(
        value.sourceMapId,
        value.sourceEntityId
    )
    if not source then
        return false, sourceError
    end
    local target, targetError = Store.getMapEntity(
        value.targetMapId,
        value.targetEntityId
    )
    if not target then
        return false, targetError
    end
    if source.entity_state ~= "entity_missing" then
        return false, "source_entity_not_missing"
    end
    if source.link_state ~= "active" then
        return false, "source_spatial_link_missing"
    end
    if target.entity_state == "entity_missing" then
        return false, "target_entity_missing"
    end
    if target.link_state == "active"
        or target.link_state == "card_missing"
    then
        return false, "target_entity_already_linked"
    end

    local before = {
        phase = "before",
        source = source,
        target = target,
    }
    -- Everything the source said of its own, flat beside the identity that is
    -- moving. Built from the overrides rather than field by field, so an
    -- override added later moves with the relink and comes back on a Redo
    -- without this being edited.
    local moved = Store.overridesOf(source)
    moved.mapId = value.targetMapId
    moved.entityId = value.targetEntityId
    moved.state = "active"
    moved.entityName = source.entity_name or ""
    moved.entityTag = source.entity_tag or ""
    moved.collectionUuid = source.collection_uuid
    moved.cardId = tonumber(source.card_id)
    moved.verifiedMapSha256 = source.verified_map_sha256
    local after = {
        phase = "after",
        source = {
            mapId = value.sourceMapId,
            entityId = value.sourceEntityId,
            state = "removed",
        },
        target = moved,
    }
    -- The target takes on everything the source said about itself, in one
    -- statement rather than an insert-if-absent followed by an update: those
    -- two had to be kept saying the same thing, and a column added to one of
    -- them and not the other is a column that survives a relink only when the
    -- target row happened not to exist yet. "It follows the global" is part of
    -- what moves, which is why the override step travels with it -- without it
    -- the forward path dropped an override while Redo, which replays the
    -- recorded state, put it back.
    local steps = metadataStepsFromRow(
        value.targetMapId, value.targetEntityId, source, "identified"
    )
    for _, step in ipairs({
        {
            [[
                INSERT INTO spatial_links (
                    map_id, entity_id, collection_uuid, card_id,
                    state, verified_map_sha256
                ) VALUES (?, ?, ?, ?, 'active', ?)
            ]],
            {
                value.targetMapId,
                value.targetEntityId,
                source.collection_uuid,
                tonumber(source.card_id),
                source.verified_map_sha256,
            },
        },
        {
            "DELETE FROM spatial_links WHERE map_id = ? AND entity_id = ?",
            {value.sourceMapId, value.sourceEntityId},
        },
        {
            "UPDATE map_entity_metadata SET presence_state = 'entity_missing' "
                .. "WHERE map_id = ? AND entity_id = ?",
            {value.sourceMapId, value.sourceEntityId},
        },
        -- DELETE FROM map_entities is intentionally not executed: the
        -- persistent Map Entity remains available for a reversible relink.
    }) do
        table.insert(steps, step)
    end
    local committed, errorMessage = historyTransaction(
        "relink_entity",
        -- `historyTarget`, not the table itself. Every other caller encodes it
        -- and `historySteps` binds this straight into `change_history.target`,
        -- so a raw table failed the bind, rolled the whole transaction back and
        -- made `Relink entity` return `relink_transaction_failed` every single
        -- time. Nothing caught it because the two tests that mention relinking
        -- read the function's *source text* for the word `historyTransaction`.
        historyTarget(value.sourceMapId, value.sourceEntityId),
        before,
        after,
        steps
    )
    if not committed then
        return false, "relink_transaction_failed: " .. tostring(errorMessage)
    end
    return {
        state = "active",
        sourceMapId = value.sourceMapId,
        sourceEntityId = value.sourceEntityId,
        targetMapId = value.targetMapId,
        targetEntityId = value.targetEntityId,
        metadata = Store.metadataOf(source, "identified"),
        link = {
            collectionUuid = source.collection_uuid,
            cardId = tonumber(source.card_id),
        },
        reversible = {
            before = before,
            after = after,
        },
    }
end

function Store.findMapEntityByRuntimeElement(entityElement)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if not isElement(entityElement) then
        return false, "entity_not_an_element"
    end
    local entityType = getElementType(entityElement)
    local persistentId = getElementData(entityElement, "ankigtaEntityId")
    local editorId = getElementData(entityElement, "me:ID")
    -- The `id` a `.map` file gave the element. MTA fills it when it loads the
    -- map, so it is there for a player who is merely spawned in the world --
    -- where `me:ID`, which the stock editor writes only while editing, is not.
    local mapFileId = getElementID(entityElement)
    if type(mapFileId) ~= "string" then
        mapFileId = ""
    end
    local names = {}
    for _, name in ipairs({persistentId, editorId, mapFileId}) do
        if type(name) == "string" and name ~= "" then
            names[name] = true
        end
    end
    if not next(names) then
        return false, "entity_not_managed"
    end

    local rows, readError = Store.listMapEntities()
    if not rows then
        return false, readError
    end
    local matches = {}
    for _, row in ipairs(rows) do
        if row.entity_type == entityType and names[row.entity_id] then
            table.insert(matches, row)
        end
    end
    if #matches == 0 then
        return false, "map_entity_not_loaded"
    end
    if #matches ~= 1 then
        return false, "map_entity_ambiguous"
    end

    local ownerResource = getResourceFromName(matches[1].resource_name)
    if not ownerResource then
        return false, "map_entity_not_loaded"
    end
    local ownerRoot = getResourceRootElement(ownerResource)
    local ancestor = entityElement
    local belongsToOwner = false
    while isElement(ancestor) do
        if ancestor == ownerRoot then
            belongsToOwner = true
            break
        end
        ancestor = getElementParent(ancestor)
    end
    if not belongsToOwner then
        return false, "map_entity_not_loaded"
    end
    local embeddedMapId = getElementData(entityElement, "ankigtaMapId")
    if embeddedMapId and embeddedMapId ~= ""
        and embeddedMapId ~= matches[1].map_id
    then
        return false, "map_entity_not_loaded"
    end
    return matches[1]
end

function Store.activateSpatialLink(value)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(value) ~= "table"
        or type(value.mapId) ~= "string"
        or type(value.entityId) ~= "string"
        or type(value.cardIdentity) ~= "table"
        or type(value.cardIdentity.collectionUuid) ~= "string"
        or tonumber(value.cardIdentity.cardId) == nil
        or type(value.mapLocator) ~= "table"
        or type(value.mapLocator.resourceName) ~= "string"
        or type(value.mapLocator.mapFile) ~= "string"
        or type(value.verifiedMapSha256) ~= "string"
    then
        return false, "invalid_spatial_link"
    end
    if tonumber(value.cardIdentity.cardId) <= 0 then
        return false, "invalid_spatial_link"
    end

    local existing, existingError = Store.getMapEntity(
        value.mapId,
        value.entityId
    )
    if not existing then
        return false, existingError
    end
    if existing.link_state == "active" or existing.link_state == "card_missing" then
        if value.allowRename then
            local updated, updateError = Store.updateMapLocator(
                value.mapId,
                value.mapLocator
            )
            if not updated then
                return false, updateError
            end
            return {
                state = "active",
                collectionUuid = existing.collection_uuid,
                cardId = tonumber(existing.card_id),
                verifiedMapSha256 = existing.verified_map_sha256,
            }
        end
        return false, "entity_already_linked"
    end

    local owner, ownerError = Store.mapIdentityOwner(
        value.mapId,
        value.mapLocator
    )
    if ownerError then
        return false, ownerError
    end
    if owner and not value.allowRename and (
        owner.resourceName ~= value.mapLocator.resourceName
        or owner.mapFile ~= value.mapLocator.mapFile
    ) then
        return false, "identity_collision"
    end

    local before = {
        mapLocator = {
            resourceName = existing.resource_name,
            mapFile = existing.map_name,
        },
        link = nil,
    }
    local after = {
        mapLocator = {
            resourceName = value.mapLocator.resourceName,
            mapFile = value.mapLocator.mapFile,
        },
        link = {
            collectionUuid = value.cardIdentity.collectionUuid,
            cardId = tonumber(value.cardIdentity.cardId),
            verifiedMapSha256 = value.verifiedMapSha256,
        },
    }
    -- historyTransaction uses transaction(Store.connection, ...) so the
    -- Spatial Link and its reversible journal entry commit together.
    local activated, activationError = historyTransaction(
        "spatial_link",
        historyTarget(value.mapId, value.entityId),
        before,
        after,
        {
            {
                "UPDATE maps SET resource_name = ?, map_name = ? WHERE map_id = ?",
                {
                    value.mapLocator.resourceName,
                    value.mapLocator.mapFile,
                    value.mapId,
                },
            },
            {
                [[
                    INSERT INTO spatial_links (
                        map_id, entity_id, collection_uuid, card_id,
                        state, verified_map_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ]],
                {
                    value.mapId,
                    value.entityId,
                    value.cardIdentity.collectionUuid,
                    tonumber(value.cardIdentity.cardId),
                    "active",
                    value.verifiedMapSha256,
                },
            },
        }
    )
    if not activated then
        return false, "spatial_link_activation_failed: " .. tostring(activationError)
    end
    return {
        state = "active",
        collectionUuid = value.cardIdentity.collectionUuid,
        cardId = tonumber(value.cardIdentity.cardId),
        verifiedMapSha256 = value.verifiedMapSha256,
    }
end

local function validCardIdentity(identity)
    return type(identity) == "table"
        and type(identity.collectionUuid) == "string"
        and identity.collectionUuid ~= ""
        and tonumber(identity.cardId) ~= nil
        and tonumber(identity.cardId) > 0
end

local function rowCardIdentity(row)
    if type(row) ~= "table"
        or type(row.collection_uuid) ~= "string"
        or tonumber(row.card_id) == nil
    then
        return false
    end
    return {
        collectionUuid = row.collection_uuid,
        cardId = tonumber(row.card_id),
    }
end

local function sameCardIdentity(left, right)
    return validCardIdentity(left)
        and validCardIdentity(right)
        and left.collectionUuid == right.collectionUuid
        and tonumber(left.cardId) == tonumber(right.cardId)
end

local function linkHistoryState(row, identity, stateOverride)
    return {
        mapLocator = {
            resourceName = row.resource_name,
            mapFile = row.map_name,
        },
        link = identity and {
            collectionUuid = identity.collectionUuid,
            cardId = tonumber(identity.cardId),
            state = stateOverride or row.link_state or "active",
            verifiedMapSha256 = row.verified_map_sha256,
        } or nil,
    }
end

function Store.unlinkSpatialLink(value)
    -- historyTransaction commits through transaction(Store.connection, ...)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(value) ~= "table"
        or type(value.mapId) ~= "string"
        or type(value.entityId) ~= "string"
        or not validCardIdentity(value.expectedCardIdentity)
    then
        return false, "invalid_unlink_request"
    end
    local row, readError = Store.getMapEntity(value.mapId, value.entityId)
    if not row then
        return false, readError
    end
    local current = rowCardIdentity(row)
    if row.link_state ~= "active" and row.link_state ~= "card_missing" then
        return false, "spatial_link_not_found"
    end
    if not sameCardIdentity(current, value.expectedCardIdentity) then
        return false, "spatial_link_identity_changed"
    end
    local committed, errorMessage = historyTransaction(
        "spatial_link",
        historyTarget(value.mapId, value.entityId),
        linkHistoryState(row, current),
        linkHistoryState(row, nil),
        {
            {
                "DELETE FROM spatial_links WHERE map_id = ? AND entity_id = ?",
                {value.mapId, value.entityId},
            },
        }
    )
    if not committed then
        return false, "spatial_link_unlink_failed: " .. tostring(errorMessage)
    end
    return {
        state = "unlinked",
        cardIdentity = current,
    }
end

function Store.replaceSpatialLink(value)
    -- historyTransaction commits through transaction(Store.connection, ...)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(value) ~= "table"
        or type(value.mapId) ~= "string"
        or type(value.entityId) ~= "string"
        or not validCardIdentity(value.oldCardIdentity)
        or not validCardIdentity(value.newCardIdentity)
    then
        return false, "invalid_replace_request"
    end
    if sameCardIdentity(value.oldCardIdentity, value.newCardIdentity) then
        return false, "replacement_card_unchanged"
    end
    local row, readError = Store.getMapEntity(value.mapId, value.entityId)
    if not row then
        return false, readError
    end
    local current = rowCardIdentity(row)
    if row.link_state ~= "active" and row.link_state ~= "card_missing" then
        return false, "spatial_link_not_found"
    end
    if not sameCardIdentity(current, value.oldCardIdentity) then
        return false, "spatial_link_identity_changed"
    end
    local committed, errorMessage = historyTransaction(
        "spatial_link",
        historyTarget(value.mapId, value.entityId),
        linkHistoryState(row, current),
        linkHistoryState(row, value.newCardIdentity, "active"),
        {
            {
                [[
                    UPDATE spatial_links
                    SET collection_uuid = ?, card_id = ?, state = 'active'
                    WHERE map_id = ? AND entity_id = ?
                ]],
                {
                    value.newCardIdentity.collectionUuid,
                    tonumber(value.newCardIdentity.cardId),
                    value.mapId,
                    value.entityId,
                },
            },
        }
    )
    if not committed then
        return false, "spatial_link_replace_failed: " .. tostring(errorMessage)
    end
    return {
        state = "active",
        oldCardIdentity = current,
        newCardIdentity = {
            collectionUuid = value.newCardIdentity.collectionUuid,
            cardId = tonumber(value.newCardIdentity.cardId),
        },
    }
end

function Store.refreshSpatialLinkCardState(cardIdentity, present)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if not validCardIdentity(cardIdentity) then
        return false, "invalid_anki_card_identity"
    end
    local state = present == true and "active" or "card_missing"
    local previousOk, previousRows = execute(
        Store.connection,
        [[
            SELECT state
            FROM spatial_links
            WHERE collection_uuid = ? AND card_id = ?
        ]],
        cardIdentity.collectionUuid,
        tonumber(cardIdentity.cardId)
    )
    if not previousOk then
        return false, "card_state_refresh_failed"
    end
    local previousState = previousRows[1] and previousRows[1].state or false
    local ok, errorMessage = execute(
        Store.connection,
        [[
            UPDATE spatial_links
            SET state = ?
            WHERE collection_uuid = ? AND card_id = ?
        ]],
        state,
        cardIdentity.collectionUuid,
        tonumber(cardIdentity.cardId)
    )
    if not ok then
        return false, "card_state_refresh_failed: " .. tostring(errorMessage)
    end
    return true, previousState ~= state
end

function Store.markCardMissing(cardIdentity)
    return Store.refreshSpatialLinkCardState(cardIdentity, false)
end

function Store.linkCardToEntity(value)
    return Store.activateSpatialLink(value)
end

function Store.mapIdentityOwner(mapId, mapLocator)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(mapId) ~= "string" or type(mapLocator) ~= "table" then
        return false, "invalid_map_identity"
    end

    local ok, rows = execute(
        Store.connection,
        "SELECT resource_name, map_name FROM maps WHERE map_id = ?",
        mapId
    )
    if not ok then
        return false, "map_identity_owner_read_failed"
    end
    if not rows[1] then
        return nil
    end
    return {
        resourceName = rows[1].resource_name,
        mapFile = rows[1].map_name,
    }
end

function Store.updateEntityMetadata(mapId, entityId, metadata)
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(mapId) ~= "string" or type(entityId) ~= "string"
        or type(metadata) ~= "table"
    then
        return false, "invalid_entity_metadata"
    end
    local existing, readError = Store.getMapEntity(mapId, entityId)
    if not existing then
        return false, readError
    end
    local metadataOk, metadataRows = execute(
        Store.connection,
        "SELECT 1 FROM map_entity_metadata WHERE map_id = ? AND entity_id = ?",
        mapId,
        entityId
    )
    if not metadataOk then
        return false, "entity_metadata_read_failed"
    end
    -- An absent field is "this entity follows the global", which is a different
    -- answer from 3 and has to survive a round trip through Change History as
    -- itself.
    local before = Store.metadataOf(existing)
    before.exists = metadataRows[1] ~= nil
    local after = {
        exists = true,
        name = tostring(metadata.name or ""),
        entityTag = tostring(metadata.entityTag or ""),
        presenceState = metadata.presenceState
            or existing.entity_state
            or "identified",
    }
    -- Each override taken as the caller gave it, which has already been checked
    -- against the schema's own rule for the setting it overrides. Nothing is
    -- coerced here: `false` is a corona switched off on this entity and absent
    -- is one that follows the global, and a coercion is how those two became
    -- one answer the last time this was written out field by field.
    local wanted = underCurrentNames(metadata)
    for _, setting in ipairs(overridableSettings()) do
        after[setting.field] = wanted[setting.field]
    end
    local committed, errorMessage = historyTransaction(
        "entity_metadata",
        historyTarget(mapId, entityId),
        before,
        after,
        metadataSteps(mapId, entityId, after)
    )
    if not committed then
        return false, "entity_metadata_update_failed: " .. tostring(errorMessage)
    end
    return true
end

--- The column a setting's overrides live in, or why there is none.
local function overrideColumnFor(settingKey)
    if type(settingKey) ~= "string" then
        return false, "settings.error.unknown"
    end
    if not ANKIGTA.Settings.definition(settingKey) then
        return false, "settings.error.unknown"
    end
    local column = ANKIGTA.Settings.entityOverrideColumn(settingKey)
    if not column then
        return false, "settings.error.not_overridable"
    end
    return column
end

--- How many links say something of their own about this setting.
--
-- Asked before the clearing rather than carried on every settings push: the
-- number is what the confirmation names, and a number attached to a control the
-- player is not looking at would be recounted on every state change instead.
function Store.countEntityOverrides(settingKey)
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local column, reason = overrideColumnFor(settingKey)
    if not column then
        return false, reason
    end
    local ok, rows = execute(
        Store.connection,
        "SELECT COUNT(*) AS overrides FROM map_entity_metadata"
            .. " WHERE " .. column .. " IS NOT NULL"
    )
    if not ok or not rows[1] then
        return false, "entity_override_read_failed"
    end
    return tonumber(rows[1].overrides) or 0
end

--- Put every link back on the global for one setting.
--
-- Clearing, not copying. Every link *follows* the global afterwards, so
-- changing the global again moves them all again; writing today's value into
-- each link as its own override would look identical for a minute and then
-- quietly stop tracking.
--
-- One Change History entry for the whole sweep, because it is one decision. The
-- entry carries what each link said, so one Undo puts every one of them back.
function Store.clearEntityOverrides(settingKey)
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local column, reason = overrideColumnFor(settingKey)
    if not column then
        return false, reason
    end
    local definition = ANKIGTA.Settings.definition(settingKey)
    local kind = definition and definition.rule and definition.rule.kind
    local ok, rows = execute(
        Store.connection,
        "SELECT map_id, entity_id, " .. column .. " AS override"
            .. " FROM map_entity_metadata WHERE " .. column .. " IS NOT NULL"
    )
    if not ok then
        return false, "entity_override_read_failed"
    end
    local overrides = {}
    for _, row in ipairs(rows) do
        overrides[#overrides + 1] = {
            mapId = row.map_id,
            entityId = row.entity_id,
            value = readOverride(kind, row.override),
        }
    end
    if #overrides == 0 then
        -- Nothing changed, so there is nothing to undo. An entry here would be
        -- a history step that does nothing and an Undo that appears to fail.
        return {settingKey = settingKey, cleared = 0}
    end
    local committed, errorMessage = historyTransaction(
        "clear_entity_overrides",
        jsonEncode({settingKey = settingKey}),
        {settingKey = settingKey, overrides = overrides},
        {settingKey = settingKey, overrides = {}},
        {
            {
                "UPDATE map_entity_metadata SET " .. column .. " = NULL"
                    .. " WHERE " .. column .. " IS NOT NULL",
            },
        }
    )
    if not committed then
        return false, "entity_override_clear_failed: " .. tostring(errorMessage)
    end
    return {settingKey = settingKey, cleared = #overrides}
end

--- Every persisted setting, decoded, keyed by setting.
--
-- A stored value the schema no longer accepts is dropped here rather than
-- handed on: a range that narrowed between versions must not resurrect a value
-- the user can no longer choose.
function Store.listUserSettings()
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local ok, rows = execute(
        Store.connection,
        "SELECT setting_key, setting_value FROM user_settings"
    )
    if not ok then
        return false, "user_setting_read_failed"
    end
    local settings = {}
    for _, row in ipairs(rows) do
        local key = row.setting_key
        local value = jsonDecode(row.setting_value)
        local valid, reason = ANKIGTA.Settings.validate(key, value)
        if valid then
            settings[key] = ANKIGTA.Settings.normalize(key, value)
        else
            outputDebugString(
                "[ANKIGTA] discarded_stored_setting: "
                    .. tostring(key) .. " (" .. tostring(reason) .. ")",
                2
            )
        end
    end
    return settings
end

--- Persist one setting the server owns.
--
-- The schema decides three separate things here: whether this side may write
-- the setting at all, whether the value is acceptable, and whether the change
-- belongs in Change History. None of them is a property of the database.
function Store.setUserSetting(settingKey, value)
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(settingKey) ~= "string" or settingKey == "" then
        return false, "invalid_user_setting"
    end
    local writeKind, writeReason =
        ANKIGTA.Settings.writeKind("server", settingKey)
    if not writeKind then
        if writeReason == "unknown_setting" then
            return false, "settings.error.unknown"
        end
        return false, writeReason
    end
    if writeKind ~= "authority" then
        -- A local override is not shared state: it belongs to the connection
        -- file on the side that made it, not to the shared database.
        return false, "not_a_stored_setting"
    end
    local valid, invalidReason = ANKIGTA.Settings.validate(settingKey, value)
    if not valid then
        return false, invalidReason
    end
    value = ANKIGTA.Settings.normalize(settingKey, value)

    local ok, rows = execute(
        Store.connection,
        "SELECT setting_value FROM user_settings WHERE setting_key = ?",
        settingKey
    )
    if not ok then
        return false, "user_setting_read_failed"
    end
    local before = {
        exists = rows[1] ~= nil,
        value = rows[1] and jsonDecode(rows[1].setting_value) or nil,
    }
    local after = {exists = true, value = value}
    local write = {
        {
            "INSERT OR REPLACE INTO user_settings (setting_key, setting_value) VALUES (?, ?)",
            {settingKey, jsonEncode(value)},
        },
    }
    if not ANKIGTA.Settings.inChangeHistory(settingKey) then
        -- Undoable is a property of the setting, not of the write path.
        local committed, writeError = transaction(Store.connection, write)
        if not committed then
            return false, writeError
        end
        noteDataChange()
        return true
    end
    return historyTransaction(
        "user_setting",
        jsonEncode({settingKey = settingKey}),
        before,
        after,
        write
    )
end

ANKIGTA.Store = Store

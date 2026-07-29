ANKIGTA = ANKIGTA or {}

local DATABASE_PATH = "ankigta.sqlite"
local CURRENT_SCHEMA_VERSION = 2

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

local Store = {
    connection = nil,
    ready = false,
    errorCategory = nil,
    errorMessage = nil,
    schemaVersion = nil,
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
                    entity_type TEXT NOT NULL CHECK (entity_type = 'object'),
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
    })
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
            {CURRENT_SCHEMA_VERSION},
        },
    })
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

function Store.open()
    Store.ready = false
    Store.errorCategory = nil
    Store.errorMessage = nil
    Store.schemaVersion = nil

    Store.connection = connect(DATABASE_PATH)
    if not Store.connection then
        return fail("database_open_failed", DATABASE_PATH)
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
    else
        local version = readSchemaVersion(Store.connection)
        if version == 1 then
            local migrated, migrationError = migrateVersionOne()
            if not migrated then
                closeConnection()
                return fail("migration_failed", migrationError)
            end
        elseif version ~= CURRENT_SCHEMA_VERSION then
            closeConnection()
            return fail("unsupported_schema_version", tostring(version))
        end
    end

    Store.schemaVersion = readSchemaVersion(Store.connection)
    if Store.schemaVersion ~= CURRENT_SCHEMA_VERSION then
        closeConnection()
        return fail("schema_verification_failed", tostring(Store.schemaVersion))
    end

    local seeded, seedError = ensureTracerEntity()
    if not seeded then
        closeConnection()
        return fail("tracer_entity_create_failed", seedError)
    end

    Store.ready = true
    return true
end

function Store.close()
    closeConnection()
    Store.ready = false
end

function Store.status()
    return {
        ready = Store.ready,
        schemaVersion = Store.schemaVersion or false,
        errorCategory = Store.errorCategory or false,
    }
end

function Store.listMapEntities()
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end

    local ok, rows = execute(
        Store.connection,
        [[
            SELECT
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
                map_entities.dimension
            FROM map_entities
            INNER JOIN maps ON maps.map_id = map_entities.map_id
            ORDER BY maps.map_id, map_entities.entity_id
        ]]
    )
    if not ok then
        return false, "entity_read_failed"
    end
    return rows
end

ANKIGTA.Store = Store

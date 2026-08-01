ANKIGTA = ANKIGTA or {}

local DATABASE_PATH = "ankigta.sqlite"
local CURRENT_SCHEMA_VERSION = 4
local HISTORY_LIMIT = 100

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
    identityCollisionByMap = {},
    historyReady = false,
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

local function historyTransaction(operation, target, before, after, steps)
    local allSteps = {}
    for _, step in ipairs(steps or {}) do
        table.insert(allSteps, step)
    end
    for _, step in ipairs(historySteps(operation, target, before, after)) do
        table.insert(allSteps, step)
    end
    return transaction(Store.connection, allSteps)
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
        {
            [[
                CREATE TABLE IF NOT EXISTS map_preferences (
                    map_id TEXT PRIMARY KEY,
                    include_in_study INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY (map_id) REFERENCES maps(map_id) ON DELETE CASCADE
                )
            ]],
        },
        {
            [[
                CREATE TABLE IF NOT EXISTS map_entity_metadata (
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
            ]],
        },
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
        local hasPresenceState = false
        for _, column in ipairs(columns) do
            if column.name == "presence_state" then
                hasPresenceState = true
                break
            end
        end
        if not hasPresenceState then
            local altered, alterError = execute(
                Store.connection,
                [[
                    ALTER TABLE map_entity_metadata
                    ADD COLUMN presence_state TEXT NOT NULL DEFAULT 'identified'
                ]]
            )
            if not altered then
                return false, alterError
            end
        end
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
            {CURRENT_SCHEMA_VERSION},
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
    return rows[1].sql:find("entity_type = 'object'", 1, true) ~= nil
end

local function hasIdentityCollisionTable()
    local ok, rows = execute(
        Store.connection,
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'identity_collisions'"
    )
    return ok and rows[1] ~= nil
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
    if hasIdentityCollisionTable() then
        return true
    end
    return migrateIdentityCollisionTable()
end

local function migrateVersionThree()
    return transaction(Store.connection, {
        {"ALTER TABLE spatial_links RENAME TO spatial_links_legacy"},
        {"ALTER TABLE map_entities RENAME TO map_entities_legacy"},
        {
            [[
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
            ]],
        },
        {
            [[
                INSERT INTO map_entities
                SELECT map_id, entity_id, entity_type, model,
                       authored_x, authored_y, authored_z,
                       rotation_x, rotation_y, rotation_z,
                       interior, dimension
                FROM map_entities_legacy
            ]],
        },
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
        {
            [[
                INSERT INTO spatial_links
                SELECT map_id, entity_id, collection_uuid, card_id,
                       state, verified_map_sha256
                FROM spatial_links_legacy
            ]],
        },
        {"DROP TABLE spatial_links_legacy"},
        {"DROP TABLE map_entities_legacy"},
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
            {2},
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

function Store.open()
    Store.ready = false
    Store.errorCategory = nil
    Store.errorMessage = nil
    Store.schemaVersion = nil
    Store.identityCollisionByMap = {}
    Store.historyReady = false

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
        local collisionsCreated, collisionsError =
            ensureIdentityCollisionTable()
        if not collisionsCreated then
            closeConnection()
            return fail("schema_create_failed", collisionsError)
        end
    else
        local version = readSchemaVersion(Store.connection)
        if version == 1 then
            local migrated, migrationError = migrateVersionOne()
            if not migrated then
                closeConnection()
                return fail("migration_failed", migrationError)
            end
            version = readSchemaVersion(Store.connection)
        end
        if version == 2 then
            local migrated, migrationError = migrateVersionTwo()
            if not migrated then
                closeConnection()
                return fail("migration_failed", migrationError)
            end
            version = readSchemaVersion(Store.connection)
        end
        if version == 3 and needsEntityTypeMigration() then
            local migrated, migrationError = migrateVersionThree()
            if not migrated then
                closeConnection()
                return fail("migration_failed", migrationError)
            end
            version = readSchemaVersion(Store.connection)
        end
        if version == 3 and not hasIdentityCollisionTable() then
            local migrated, migrationError = migrateIdentityCollisionTable()
            if not migrated then
                closeConnection()
                return fail("migration_failed", migrationError)
            end
        end
        if version == 3 then
            local migrated, migrationError = migrateVersionFour()
            if not migrated then
                closeConnection()
                return fail("migration_failed", migrationError)
            end
            version = readSchemaVersion(Store.connection)
        end
        if version ~= CURRENT_SCHEMA_VERSION then
            closeConnection()
            return fail("unsupported_schema_version", tostring(version))
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

    local seeded, seedError = ensureTracerEntity()
    if not seeded then
        closeConnection()
        return fail("tracer_entity_create_failed", seedError)
    end

    Store.ready = true
    return true
end

function Store.markIdentityCollision(mapId)
    if type(mapId) == "string" and mapId ~= "" then
        Store.identityCollisionByMap[mapId] = true
    end
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
    Store.markIdentityCollision(mapId)
    return true
end

function Store.isIdentityCollision(mapId, entityId)
    if type(mapId) ~= "string" or Store.identityCollisionByMap[mapId] == true then
        return type(mapId) == "string" and Store.identityCollisionByMap[mapId] == true
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

function Store.listIdentityCollisions()
    if not Store.ready then
        return false, Store.errorCategory or "storage_unavailable"
    end
    local ok, rows = execute(
        Store.connection,
        "SELECT map_id, entity_id, reason FROM identity_collisions"
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
    local remainingOk, remainingRows = execute(
        Store.connection,
        "SELECT 1 FROM identity_collisions WHERE map_id = ? LIMIT 1",
        mapId
    )
    if not remainingOk then
        return false, "identity_collision_read_failed"
    end
    local remaining = remainingRows
    if #remaining == 0 then
        Store.identityCollisionByMap[mapId] = nil
    end
    return true
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
                table.insert(steps, {
                    [[
                        INSERT OR REPLACE INTO map_entity_metadata (
                            map_id, entity_id, name, entity_tag, radius,
                            show_radius, presence_state
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ]],
                    {
                        sourceMapId,
                        sourceEntityId,
                        sourceRow.entity_name or "",
                        sourceRow.entity_tag or "",
                        tonumber(sourceRow.radius) or 3,
                        tonumber(sourceRow.show_radius) == 1 and 1 or 0,
                        sourceRow.entity_state or "entity_missing",
                    },
                })
            end
            if targetRow.entity_id or targetRow.entityId then
                table.insert(steps, {
                    [[
                        INSERT OR REPLACE INTO map_entity_metadata (
                            map_id, entity_id, name, entity_tag, radius,
                            show_radius, presence_state
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ]],
                    {
                        targetMapId,
                        targetEntityId,
                        targetRow.entity_name or "",
                        targetRow.entity_tag or "",
                        tonumber(targetRow.radius) or 3,
                        tonumber(targetRow.show_radius) == 1 and 1 or 0,
                        targetRow.entity_state or "identified",
                    },
                })
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
            table.insert(steps, {
                [[
                    INSERT OR REPLACE INTO map_entity_metadata (
                        map_id, entity_id, name, entity_tag, radius,
                        show_radius, presence_state
                    ) VALUES (?, ?, ?, ?, ?, ?, 'identified')
                ]],
                {
                    targetMapId,
                    targetEntityId,
                    targetRow.entityName or "",
                    targetRow.entityTag or "",
                    tonumber(targetRow.radius) or 3,
                    targetRow.showRadius and 1 or 0,
                },
            })
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
            table.insert(steps, {
                [[
                    INSERT OR REPLACE INTO map_entity_metadata (
                        map_id, entity_id, name, entity_tag, radius, show_radius,
                        presence_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ]],
                {
                    target.mapId,
                    target.entityId,
                    state.name or "",
                    state.entityTag or "",
                    tonumber(state.radius) or 3,
                    state.showRadius and 1 or 0,
                    state.presenceState or "identified",
                },
            })
        end
    elseif operation == "map_preference" then
        if type(target) ~= "table" or type(target.mapId) ~= "string"
            or type(state) ~= "table"
        then
            return false, "invalid_history_target"
        end
        if state.exists == false then
            table.insert(steps, {
                "DELETE FROM map_preferences WHERE map_id = ?",
                {target.mapId},
            })
        else
            table.insert(steps, {
                "INSERT OR REPLACE INTO map_preferences (map_id, include_in_study) VALUES (?, ?)",
                {target.mapId, state.includeInStudy and 1 or 0},
            })
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
                map_entities.dimension,
                COALESCE(map_entity_metadata.name, '') AS entity_name,
                COALESCE(map_entity_metadata.entity_tag, '') AS entity_tag,
                COALESCE(map_entity_metadata.radius, 3) AS radius,
                COALESCE(map_entity_metadata.show_radius, 0) AS show_radius,
                COALESCE(map_preferences.include_in_study, 1)
                    AS include_in_study,
                spatial_links.collection_uuid,
                spatial_links.card_id,
                spatial_links.state AS link_state,
                spatial_links.verified_map_sha256,
                COALESCE(map_entity_metadata.presence_state, 'identified')
                    AS entity_state
            FROM map_entities
            INNER JOIN maps ON maps.map_id = map_entities.map_id
            LEFT JOIN spatial_links
                ON spatial_links.map_id = map_entities.map_id
                AND spatial_links.entity_id = map_entities.entity_id
            LEFT JOIN map_entity_metadata
                ON map_entity_metadata.map_id = map_entities.map_id
                AND map_entity_metadata.entity_id = map_entities.entity_id
            LEFT JOIN map_preferences
                ON map_preferences.map_id = map_entities.map_id
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
        [[
            SELECT
                maps.map_id,
                maps.resource_name,
                maps.map_name,
                map_entities.entity_id,
                map_entities.entity_type,
                map_entity_metadata.name AS entity_name,
                map_entity_metadata.entity_tag AS entity_tag,
                map_entity_metadata.radius AS radius,
                map_entity_metadata.show_radius AS show_radius,
                map_preferences.include_in_study AS include_in_study,
                spatial_links.collection_uuid,
                spatial_links.card_id,
                spatial_links.state AS link_state,
                spatial_links.verified_map_sha256,
                COALESCE(map_entity_metadata.presence_state, 'identified')
                    AS entity_state
            FROM map_entities
            INNER JOIN maps ON maps.map_id = map_entities.map_id
            LEFT JOIN spatial_links
                ON spatial_links.map_id = map_entities.map_id
                AND spatial_links.entity_id = map_entities.entity_id
            LEFT JOIN map_entity_metadata
                ON map_entity_metadata.map_id = map_entities.map_id
                AND map_entity_metadata.entity_id = map_entities.entity_id
            LEFT JOIN map_preferences
                ON map_preferences.map_id = map_entities.map_id
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
    local after = {
        phase = "after",
        source = {
            mapId = value.sourceMapId,
            entityId = value.sourceEntityId,
            state = "removed",
        },
        target = {
            mapId = value.targetMapId,
            entityId = value.targetEntityId,
            state = "active",
            entityName = source.entity_name or "",
            entityTag = source.entity_tag or "",
            radius = tonumber(source.radius) or 3,
            showRadius = tonumber(source.show_radius) == 1,
            collectionUuid = source.collection_uuid,
            cardId = tonumber(source.card_id),
            verifiedMapSha256 = source.verified_map_sha256,
        },
    }
    local steps = {
        {
            [[
                INSERT OR IGNORE INTO map_entity_metadata
                    (map_id, entity_id, name, entity_tag, radius, show_radius, presence_state)
                VALUES (?, ?, ?, ?, ?, ?, 'identified')
            ]],
            {
                value.targetMapId,
                value.targetEntityId,
                source.entity_name or "",
                source.entity_tag or "",
                tonumber(source.radius) or 3,
                tonumber(source.show_radius) == 1 and 1 or 0,
            },
        },
        {
            [[
                UPDATE map_entity_metadata
                SET name = ?, entity_tag = ?, radius = ?, show_radius = ?,
                    presence_state = 'identified'
                WHERE map_id = ? AND entity_id = ?
            ]],
            {
                source.entity_name or "",
                source.entity_tag or "",
                tonumber(source.radius) or 3,
                tonumber(source.show_radius) == 1 and 1 or 0,
                value.targetMapId,
                value.targetEntityId,
            },
        },
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
    }
    local committed, errorMessage = historyTransaction(
        "relink_entity",
        {
            mapId = value.sourceMapId,
            entityId = value.sourceEntityId,
        },
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
        metadata = {
            name = source.entity_name or "",
            entityTag = source.entity_tag or "",
            radius = tonumber(source.radius) or 3,
            showRadius = tonumber(source.show_radius) == 1,
        },
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
    if type(persistentId) ~= "string" or persistentId == "" then
        return false, "entity_not_managed"
    end
    if type(editorId) ~= "string" or editorId == "" then
        return false, "entity_not_managed"
    end

    local rows, readError = Store.listMapEntities()
    if not rows then
        return false, readError
    end
    local matches = {}
    for _, row in ipairs(rows) do
        if row.entity_type == entityType
            and (row.entity_id == persistentId or row.entity_id == editorId)
        then
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
    local before = {
        exists = metadataRows[1] ~= nil,
        name = existing.entity_name or "",
        entityTag = existing.entity_tag or "",
        radius = tonumber(existing.radius) or 3,
        showRadius = tonumber(existing.show_radius) == 1,
        presenceState = existing.entity_state or "identified",
    }
    local after = {
        exists = true,
        name = tostring(metadata.name or ""),
        entityTag = tostring(metadata.entityTag or ""),
        radius = tonumber(metadata.radius) or 3,
        showRadius = metadata.showRadius == true,
        presenceState = metadata.presenceState or existing.entity_state or "identified",
    }
    local committed, errorMessage = historyTransaction(
        "entity_metadata",
        historyTarget(mapId, entityId),
        before,
        after,
        {
            {
                [[
                    INSERT OR REPLACE INTO map_entity_metadata (
                        map_id, entity_id, name, entity_tag, radius, show_radius,
                        presence_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ]],
                {
                    mapId,
                    entityId,
                    after.name,
                    after.entityTag,
                    after.radius,
                    after.showRadius and 1 or 0,
                    after.presenceState,
                },
            },
        }
    )
    if not committed then
        return false, "entity_metadata_update_failed: " .. tostring(errorMessage)
    end
    return true
end

function Store.setMapIncludeInStudy(mapId, includeInStudy)
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(mapId) ~= "string" or type(includeInStudy) ~= "boolean" then
        return false, "invalid_map_preference"
    end
    local ok, rows = execute(
        Store.connection,
        "SELECT include_in_study FROM map_preferences WHERE map_id = ?",
        mapId
    )
    if not ok then
        return false, "map_preference_read_failed"
    end
    local before = {
        exists = rows[1] ~= nil,
        includeInStudy = not rows[1] or tonumber(rows[1].include_in_study) == 1,
    }
    local after = {exists = true, includeInStudy = includeInStudy}
    return historyTransaction(
        "map_preference",
        jsonEncode({mapId = mapId}),
        before,
        after,
        {
            {
                "INSERT OR REPLACE INTO map_preferences (map_id, include_in_study) VALUES (?, ?)",
                {mapId, includeInStudy and 1 or 0},
            },
        }
    )
end

function Store.setUserSetting(settingKey, value)
    if not Store.ready or not Store.historyReady then
        return false, Store.errorCategory or "storage_unavailable"
    end
    if type(settingKey) ~= "string" or settingKey == "" then
        return false, "invalid_user_setting"
    end
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
    return historyTransaction(
        "user_setting",
        jsonEncode({settingKey = settingKey}),
        before,
        after,
        {
            {
                "INSERT OR REPLACE INTO user_settings (setting_key, setting_value) VALUES (?, ?)",
                {settingKey, jsonEncode(value)},
            },
        }
    )
end

ANKIGTA.Store = Store

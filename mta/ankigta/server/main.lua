ANKIGTA = ANKIGTA or {}

local STUDY_RIGHT = "resource.ankigta.study"
local F7_REQUEST_EVENT = "ankigta:requestF7"
local F7_SNAPSHOT_EVENT = "ankigta:f7Snapshot"
local F7_DENIED_EVENT = "ankigta:f7Denied"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"
local RUNTIME_REFERENCE_ID = "ankigta-ticket05-runtime"

local runtimeInstance = nil

local function denial(category)
    return {
        category = category,
    }
end

local function accountAuthorization(account)
    if not account or isGuestAccount(account) then
        return false, denial("authentication_required")
    end

    local accountName = getAccountName(account)
    if not accountName
        or not hasObjectPermissionTo(
            "user." .. accountName,
            STUDY_RIGHT,
            false
        )
    then
        return false, denial("forbidden")
    end

    return true
end

local function playerAuthorization(player)
    if not isElement(player) or getElementType(player) ~= "player" then
        return false, denial("authentication_required")
    end

    local account = getPlayerAccount(player)
    if not account or isGuestAccount(account) then
        return false, denial("authentication_required")
    end

    if not hasObjectPermissionTo(player, STUDY_RIGHT, false) then
        return false, denial("forbidden")
    end

    return true
end

local function runtimeSnapshot()
    if not isElement(runtimeInstance) then
        return {
            available = false,
            streamed = false,
        }
    end

    return {
        available = true,
        streamed = false,
        referenceId = RUNTIME_REFERENCE_ID,
    }
end

local function entityContract(row)
    return {
        mapEntity = {
            mapId = row.map_id,
            entityId = row.entity_id,
            type = row.entity_type,
            model = tonumber(row.model),
            map = {
                resourceName = row.resource_name,
                mapName = row.map_name,
            },
            authored = {
                position = {
                    x = tonumber(row.authored_x),
                    y = tonumber(row.authored_y),
                    z = tonumber(row.authored_z),
                },
                rotation = {
                    x = tonumber(row.rotation_x),
                    y = tonumber(row.rotation_y),
                    z = tonumber(row.rotation_z),
                },
                world = {
                    interior = tonumber(row.interior),
                    dimension = tonumber(row.dimension),
                },
            },
        },
        runtimeInstance = runtimeSnapshot(),
    }
end

local function buildF7Snapshot()
    local rows, readError = ANKIGTA.Store.listMapEntities()
    if not rows then
        return false, denial(readError or "storage_unavailable")
    end

    local entities = {}
    for _, row in ipairs(rows) do
        table.insert(entities, entityContract(row))
    end

    return {
        contractVersion = 1,
        visible = true,
        entities = entities,
    }
end

local function snapshotForAccount(account)
    local authorized, authorizationError = accountAuthorization(account)
    if not authorized then
        return false, authorizationError
    end

    if not ANKIGTA.Store.status().ready then
        return false, denial("storage_unavailable")
    end
    return buildF7Snapshot()
end

function getF7SnapshotForAccount(account)
    return snapshotForAccount(account)
end

function getStoreStatus()
    return ANKIGTA.Store.status()
end

local function sendAuthorization(player)
    local authorized = playerAuthorization(player)
    if authorized then
        triggerClientEvent(
            player,
            AUTHORIZATION_EVENT,
            resourceRoot,
            true
        )
    else
        triggerClientEvent(
            player,
            AUTHORIZATION_EVENT,
            resourceRoot,
            false
        )
    end
end

local function sendF7Snapshot(player)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        triggerClientEvent(
            player,
            F7_DENIED_EVENT,
            resourceRoot,
            authorizationError
        )
        return false
    end

    local snapshot, snapshotError = buildF7Snapshot()
    if not snapshot then
        triggerClientEvent(
            player,
            F7_DENIED_EVENT,
            resourceRoot,
            snapshotError
        )
        return false
    end

    triggerClientEvent(
        player,
        F7_SNAPSHOT_EVENT,
        resourceRoot,
        snapshot
    )
    return true
end

addEvent(F7_REQUEST_EVENT, true)
addEventHandler(F7_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    sendF7Snapshot(client)
end)

addEventHandler("onPlayerLogin", root, function()
    sendAuthorization(source)
end)

addEventHandler("onPlayerLogout", root, function()
    sendAuthorization(source)
end)

addEventHandler("onElementDestroy", root, function()
    if source == runtimeInstance then
        runtimeInstance = nil
    end
end)

addEventHandler("onResourceStart", resourceRoot, function()
    runtimeInstance = getElementByID(RUNTIME_REFERENCE_ID)
    ANKIGTA.Store.open()

    for _, player in ipairs(getElementsByType("player")) do
        sendAuthorization(player)
    end
end)

addEventHandler("onResourceStop", resourceRoot, function()
    ANKIGTA.Store.close()
end)

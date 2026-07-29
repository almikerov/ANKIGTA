local F7_REQUEST_EVENT = "ankigta:requestF7"
local F7_SNAPSHOT_EVENT = "ankigta:f7Snapshot"
local F7_DENIED_EVENT = "ankigta:f7Denied"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"
local AUTHORIZATION_REQUEST_EVENT = "ankigta:requestAuthorization"

local authorized = false
local window = nil
local grid = nil
local cursorOwned = false
local cursorWasShowing = false

local function closeF7()
    if isElement(window) then
        destroyElement(window)
    end
    window = nil
    grid = nil
    if cursorOwned then
        showCursor(cursorWasShowing)
        cursorOwned = false
        cursorWasShowing = false
    end
end

local function runtimeStatus(runtime)
    if not runtime.available then
        return "Unavailable — Runtime Instance destroyed"
    end

    local element = getElementByID(runtime.referenceId)
    if not isElement(element) or not isElementStreamedIn(element) then
        return "Unavailable — Runtime Instance not streamed"
    end

    return "Available — Runtime Instance streamed"
end

local function authoredPosition(mapEntity)
    local position = mapEntity.authored.position
    local world = mapEntity.authored.world
    return string.format(
        "%.2f, %.2f, %.2f · interior %d · dimension %d",
        position.x,
        position.y,
        position.z,
        world.interior,
        world.dimension
    )
end

local function renderSnapshot(snapshot)
    closeF7()

    local width = 900
    local height = 360
    local screenWidth, screenHeight = guiGetScreenSize()
    window = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        "ANKIGTA — Map Entity",
        false
    )
    grid = guiCreateGridList(16, 32, width - 32, height - 48, false, window)
    guiGridListAddColumn(grid, "Map Entity", 0.20)
    guiGridListAddColumn(grid, "Type", 0.10)
    guiGridListAddColumn(grid, "Authored transform / world", 0.34)
    guiGridListAddColumn(grid, "Runtime Instance", 0.31)

    for _, entry in ipairs(snapshot.entities) do
        local row = guiGridListAddRow(grid)
        local mapEntity = entry.mapEntity
        guiGridListSetItemText(
            grid,
            row,
            1,
            mapEntity.mapId .. " / " .. mapEntity.entityId,
            false,
            false
        )
        guiGridListSetItemText(grid, row, 2, mapEntity.type, false, false)
        guiGridListSetItemText(
            grid,
            row,
            3,
            authoredPosition(mapEntity),
            false,
            false
        )
        guiGridListSetItemText(
            grid,
            row,
            4,
            runtimeStatus(entry.runtimeInstance),
            false,
            false
        )
    end

    cursorWasShowing = isCursorShowing()
    cursorOwned = true
    showCursor(true)
end

local function requestF7()
    if not authorized then
        return
    end

    if isElement(window) then
        closeF7()
        return
    end

    triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
end

bindKey("F7", "down", requestF7)

addEvent(AUTHORIZATION_EVENT, true)
addEventHandler(AUTHORIZATION_EVENT, resourceRoot, function(value)
    authorized = value == true
    if not authorized then
        closeF7()
    end
end)

addEvent(F7_SNAPSHOT_EVENT, true)
addEventHandler(F7_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if authorized and type(snapshot) == "table" and snapshot.visible == true then
        renderSnapshot(snapshot)
    end
end)

addEvent(F7_DENIED_EVENT, true)
addEventHandler(F7_DENIED_EVENT, resourceRoot, function()
    authorized = false
    closeF7()
end)

addEventHandler("onClientResourceStart", resourceRoot, function()
    triggerServerEvent(AUTHORIZATION_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, closeF7)

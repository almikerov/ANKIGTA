ANKIGTA = ANKIGTA or {}

-- The panel.
--
-- One local CEF page behind F7, in place of the windows this resource had
-- grown: connection, entities, Card Picker, settings. The page is a view — it
-- holds no state of its own and decides nothing. This file owns the state,
-- pushes it in whole, and takes named actions back.
--
-- Local, not remote, and that is load-bearing: the browser process only
-- honours `window.mta` for a local browser (prototype 0006), so a panel
-- created remote would render and then be deaf.

local PANEL_ACTION_EVENT = "ankigta:panelAction"
local STATUS_EVENT = "ankigta:companionStatus"
local F7_REQUEST_EVENT = "ankigta:requestF7"
local F7_SNAPSHOT_EVENT = "ankigta:f7Snapshot"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"
local AUTHORIZATION_REQUEST_EVENT = "ankigta:requestAuthorization"
local CONNECT_EVENT = "ankigta:connectCompanion"
local SETTINGS_UPDATE_EVENT = "ankigta:updateConnectionSettings"
local PAGE_URL = "http://mta/local/client/panel/index.html"

local authorized = false
local guiBrowser = nil
local browser = nil
local pageReady = false
local cursorOwned = false
local cursorWasShowing = false

-- The last thing each source told us. The page is redrawn from these, so a
-- language change or a new status repaints without asking anyone again.
local lastStatus = nil
local lastSnapshot = nil

function isPanelOpen()
    return isElement(guiBrowser)
end

--- Give the cursor back exactly as it was found.
-- Called from every path that ends the panel, including the one where the
-- browser could not be created: a panel that fails to open must not leave the
-- player holding a cursor they cannot dismiss.
local function releaseCursor()
    if not cursorOwned then
        return
    end
    showCursor(cursorWasShowing)
    cursorOwned = false
    cursorWasShowing = false
end

local function takeCursor()
    if cursorOwned then
        return
    end
    cursorWasShowing = isCursorShowing()
    cursorOwned = true
    showCursor(true)
end

local function closePanel()
    if isElement(guiBrowser) then
        destroyElement(guiBrowser)
    end
    guiBrowser = nil
    browser = nil
    pageReady = false
    releaseCursor()
end

--- Which section the panel should be showing.
-- Not a stored preference: it follows the state of the world, because the
-- reason to open the panel with no connection is always the connection.
local function section()
    if not lastStatus or lastStatus.state ~= "connected" then
        return "connection"
    end
    return "entities"
end

--- Rank a row the way a reader thinks about it.
-- Never by raw identifier. A Map Entity someone has already linked is the one
-- they came back for; one that needs a decision is the one that cannot wait;
-- the rest are alphabetical so the list does not move around underneath them.
local LINK_STATE_RANK = {
    ["Identity Collision"] = 1,
    ["Pending Map Save"] = 2,
    ["Entity missing"] = 3,
    ["Card missing"] = 4,
    ["Active Spatial Link"] = 5,
    ["Unlinked"] = 6,
}

local function entityRows(snapshot)
    local rows = {}
    for _, entry in ipairs(snapshot and snapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        table.insert(rows, {
            mapId = mapEntity.mapId,
            entityId = mapEntity.entityId,
            type = mapEntity.type,
            name = entry.metadata and entry.metadata.name
                or entry.link.metadata and entry.link.metadata.name
                or "",
            linkState = entry.link.state,
            guidanceKey = entry.link.guidanceKey or false,
            available = entry.runtimeInstance
                and entry.runtimeInstance.available == true,
            recheckAvailable = entry.link.recheckAvailable == true,
            copyCollision = entry.link.copyCollision == true,
        })
    end
    table.sort(rows, function(left, right)
        local leftRank = LINK_STATE_RANK[left.linkState] or 99
        local rightRank = LINK_STATE_RANK[right.linkState] or 99
        if leftRank ~= rightRank then
            return leftRank < rightRank
        end
        local leftName = left.name ~= "" and left.name or left.entityId
        local rightName = right.name ~= "" and right.name or right.entityId
        if leftName ~= rightName then
            return leftName < rightName
        end
        -- Total, so two rows never swap places between one render and the next.
        return left.mapId < right.mapId
    end)
    return rows
end

local function localeTable()
    local strings = ANKIGTA.Locale and ANKIGTA.Locale.strings
    if not strings then
        return {}
    end
    local active = strings[ANKIGTA.Locale.language] or {}
    local merged = {}
    -- English underneath, so a key the active language lacks still renders as
    -- words rather than as its own name.
    for key, value in pairs(strings.en or {}) do
        merged[key] = value
    end
    for key, value in pairs(active) do
        merged[key] = value
    end
    return merged
end

local function push()
    if not pageReady or not isElement(browser) then
        return
    end
    local state = {
        section = section(),
        language = ANKIGTA.Locale and ANKIGTA.Locale.language or "en",
        locale = localeTable(),
        connection = {
            state = lastStatus and lastStatus.state or "disconnected",
            category = lastStatus and lastStatus.category or false,
            sessionCategory = lastStatus and lastStatus.sessionCategory or false,
            warningCategory = lastStatus and lastStatus.warningCategory or false,
        },
        entities = entityRows(lastSnapshot),
    }
    local encoded = toJSON(state, true)
    if not encoded then
        outputDebugString("[ANKIGTA] panel_state_encode_failed", 2)
        return
    end
    executeBrowserJavascript(
        browser,
        "window.ANKIGTA && window.ANKIGTA.receive(" .. encoded .. ");"
    )
end

local function openPanel()
    if isPanelOpen() then
        return
    end
    local screenWidth, screenHeight = guiGetScreenSize()
    -- UI Scale reaches the panel too (ticket 28). The rendered size gives way
    -- before the screen does; the setting itself is never clamped, so a scale
    -- chosen for a bigger monitor survives being played on a smaller one.
    local scale = ANKIGTA.Layout and ANKIGTA.Layout.scale() or 1
    local width = math.min(
        screenWidth - 40, math.floor(screenWidth * 0.82 * scale)
    )
    local height = math.min(
        screenHeight - 40, math.floor(screenHeight * 0.8 * scale)
    )
    guiBrowser = guiCreateBrowser(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        true,
        true,
        false
    )
    if not isElement(guiBrowser) then
        guiBrowser = nil
        -- Nothing was taken, so there is nothing to give back, and the player
        -- is left exactly as they were.
        return
    end
    browser = guiGetBrowser(guiBrowser)
    takeCursor()
    addEventHandler("onClientBrowserCreated", browser, function()
        loadBrowserURL(source, PAGE_URL)
    end)
    if isElement(browser) then
        loadBrowserURL(browser, PAGE_URL)
    end
end

function togglePanel()
    if not authorized then
        return
    end
    if isPanelOpen() then
        closePanel()
        return
    end
    openPanel()
    triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
end

bindKey("F7", "down", togglePanel)

-- Kept from the window this replaces: reachable by command as well as by key,
-- because "always reachable" has to hold when the key is bound to something
-- else or the panel is the thing that is wrong.
addCommandHandler("ankigta-connect", function()
    triggerServerEvent(CONNECT_EVENT, resourceRoot)
end)

addCommandHandler("ankigta-connection", togglePanel)

-- --- what the page sends back -------------------------------------------------

local actions = {}

function actions.ready()
    pageReady = true
    push()
end

function actions.close()
    closePanel()
end

function actions.connect()
    triggerServerEvent(CONNECT_EVENT, resourceRoot)
end

function actions.updateConnection(payload)
    triggerServerEvent(SETTINGS_UPDATE_EVENT, resourceRoot, payload)
end

addEvent(PANEL_ACTION_EVENT, true)
addEventHandler(PANEL_ACTION_EVENT, resourceRoot, function(action, rawPayload)
    if type(action) ~= "string" then
        return
    end
    local handler = actions[action]
    if not handler then
        outputDebugString("[ANKIGTA] panel_unknown_action action=" .. action, 2)
        return
    end
    local payload = nil
    if type(rawPayload) == "string" and rawPayload ~= "" then
        payload = fromJSON(rawPayload)
    end
    handler(type(payload) == "table" and payload or {})
end)

-- --- what changes underneath it -----------------------------------------------

addEvent(STATUS_EVENT, true)
addEventHandler(STATUS_EVENT, resourceRoot, function(status)
    if source ~= resourceRoot or type(status) ~= "table" then
        return
    end
    lastStatus = status
    push()
end)

addEvent(F7_SNAPSHOT_EVENT, true)
addEventHandler(F7_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if not authorized or type(snapshot) ~= "table" then
        return
    end
    lastSnapshot = snapshot
    push()
end)

addEvent(AUTHORIZATION_EVENT, true)
addEventHandler(AUTHORIZATION_EVENT, resourceRoot, function(value)
    authorized = value == true
    if not authorized then
        closePanel()
    end
end)

if ANKIGTA.Locale then
    ANKIGTA.Locale.onChange(push)
end

addEventHandler("onClientResourceStart", resourceRoot, function()
    triggerServerEvent(AUTHORIZATION_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, closePanel)

ANKIGTA.Panel = {
    isOpen = isPanelOpen,
    close = closePanel,
    rows = entityRows,
}

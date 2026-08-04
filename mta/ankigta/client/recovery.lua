ANKIGTA = ANKIGTA or {}

-- The recovery screen.
--
-- The server never replaces a damaged database on its own (ADR 0016). That
-- refusal only means something if someone is offered the choice instead, which
-- is what this window is: the copies that survived verification, the ones that
-- did not and why, and whatever has already been kept for diagnosis.
--
-- Two rules shape it. A copy that failed verification is shown but cannot be
-- chosen -- hiding it would leave the user believing there was never a backup
-- at all. And nothing here decides anything: the button sends an id, and the
-- server does the moving.

local RECOVERY_STATE_EVENT = "ankigta:databaseRecovery"
local RECOVERY_REQUEST_EVENT = "ankigta:requestDatabaseRecovery"
local RESTORE_REQUEST_EVENT = "ankigta:restoreDatabaseBackup"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"

local Recovery = {}

local authorized = false
local state = false
local window = nil
local backupsGrid = nil
local quarantineGrid = nil
local restoreButton = nil
local named = {}
local rowEntries = {}
local chosen = false

local function text(key, ...)
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.format(key, ...)
    end
    return key
end

local function close()
    if isElement(window) then
        destroyElement(window)
    end
    window = nil
    backupsGrid = nil
    quarantineGrid = nil
    restoreButton = nil
    named = {}
    rowEntries = {}
    chosen = false
end

--- One named control, for whoever needs to address the screen by part.
function Recovery.control(name)
    local handle = named[name]
    if not isElement(handle) then
        return false
    end
    return handle
end

--- The state the screen is showing, or `false` when it is not showing one.
function Recovery.state()
    return state
end

local function kindText(kind)
    return text("recovery.kind." .. tostring(kind))
end

local function stateText(entry)
    if entry.verified == true then
        return text("recovery.usable")
    end
    return text("recovery.unusable", tostring(entry.reason or "unverified"))
end

local function render()
    close()
    if type(state) ~= "table" then
        return
    end

    local width = 820
    local height = 470
    local screenWidth, screenHeight = guiGetScreenSize()
    window = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        text("recovery.title"),
        false
    )
    named.window = window

    guiCreateLabel(
        16,
        30,
        width - 32,
        22,
        text("recovery.reason." .. tostring(state.reason)),
        false,
        window
    )
    guiCreateLabel(
        16,
        54,
        width - 32,
        22,
        text(
            "recovery.damaged",
            tostring(state.databasePath or ""),
            tostring(state.detail or "")
        ),
        false,
        window
    )
    guiCreateLabel(
        16,
        78,
        width - 32,
        40,
        text("recovery.explanation"),
        false,
        window
    )

    backupsGrid = guiCreateGridList(16, 122, width - 32, 168, false, window)
    named.backups = backupsGrid
    guiGridListAddColumn(backupsGrid, text("recovery.column.created"), 0.16)
    guiGridListAddColumn(backupsGrid, text("recovery.column.kind"), 0.14)
    guiGridListAddColumn(backupsGrid, text("recovery.column.schema"), 0.10)
    guiGridListAddColumn(backupsGrid, text("recovery.column.state"), 0.26)
    guiGridListAddColumn(backupsGrid, text("recovery.column.file"), 0.30)

    rowEntries = {}
    local usable = 0
    for _, entry in ipairs(state.backups or {}) do
        local row = guiGridListAddRow(backupsGrid)
        rowEntries[row] = entry
        guiGridListSetItemText(
            backupsGrid, row, 1, tostring(entry.day or ""), false, false
        )
        guiGridListSetItemText(
            backupsGrid, row, 2, kindText(entry.kind), false, false
        )
        guiGridListSetItemText(
            backupsGrid, row, 3, tostring(entry.schemaVersion or ""), false, false
        )
        guiGridListSetItemText(
            backupsGrid, row, 4, stateText(entry), false, false
        )
        guiGridListSetItemText(
            backupsGrid, row, 5, tostring(entry.path or ""), false, false
        )
        if entry.verified == true then
            usable = usable + 1
        end
    end

    guiCreateLabel(
        16,
        296,
        width - 32,
        22,
        usable > 0
            and text("recovery.quarantineTitle")
            or text("recovery.noVerifiedBackup"),
        false,
        window
    )

    quarantineGrid = guiCreateGridList(16, 320, width - 32, 100, false, window)
    named.quarantine = quarantineGrid
    guiGridListAddColumn(quarantineGrid, text("recovery.column.file"), 0.54)
    guiGridListAddColumn(quarantineGrid, text("recovery.column.reason"), 0.44)
    for _, entry in ipairs(state.quarantine or {}) do
        local row = guiGridListAddRow(quarantineGrid)
        guiGridListSetItemText(
            quarantineGrid, row, 1, tostring(entry.path or ""), false, false
        )
        guiGridListSetItemText(
            quarantineGrid, row, 2, tostring(entry.reason or ""), false, false
        )
    end

    restoreButton = guiCreateButton(
        width - 250,
        height - 40,
        234,
        28,
        text("recovery.restore"),
        false,
        window
    )
    named.restore = restoreButton
    -- Nothing is chosen yet, and a copy that failed verification never will be.
    guiSetEnabled(restoreButton, false)

    local closeButton = guiCreateButton(
        16,
        height - 40,
        140,
        28,
        text("common.close"),
        false,
        window
    )
    named.close = closeButton

    addEventHandler("onClientGUIClick", backupsGrid, function()
        local row = guiGridListGetSelectedItem(backupsGrid)
        local entry = rowEntries[row]
        chosen = (type(entry) == "table" and entry.verified == true) and entry
            or false
        guiSetEnabled(restoreButton, chosen ~= false)
    end, false)

    addEventHandler("onClientGUIClick", restoreButton, function()
        -- Checked here rather than trusted to the disabled state: the button is
        -- the hint, this is the rule.
        if type(chosen) ~= "table" or chosen.verified ~= true then
            return
        end
        triggerServerEvent(RESTORE_REQUEST_EVENT, resourceRoot, chosen.id)
    end, false)

    addEventHandler("onClientGUIClick", closeButton, function()
        close()
    end, false)

    showCursor(true)
end

addEvent(RECOVERY_STATE_EVENT, true)
addEventHandler(RECOVERY_STATE_EVENT, resourceRoot, function(payload)
    if not authorized then
        return
    end
    if type(payload) ~= "table" then
        -- Recovery is over, or there was never anything to recover from.
        state = false
        close()
        return
    end
    state = payload
    render()
end)

addEvent(AUTHORIZATION_EVENT, true)
addEventHandler(AUTHORIZATION_EVENT, resourceRoot, function(value)
    authorized = value == true
    if not authorized then
        state = false
        close()
    end
end)

addEventHandler("onClientResourceStart", resourceRoot, function()
    triggerServerEvent(RECOVERY_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, close)

ANKIGTA.Recovery = Recovery

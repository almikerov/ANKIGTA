local STATUS_EVENT = "ankigta:companionStatus"
local CONNECT_EVENT = "ankigta:connectCompanion"
local SETTINGS_REQUEST_EVENT = "ankigta:requestConnectionSettings"
local SETTINGS_SNAPSHOT_EVENT = "ankigta:connectionSettingsSnapshot"
local SETTINGS_UPDATE_EVENT = "ankigta:updateConnectionSettings"

ANKIGTA = ANKIGTA or {}
ANKIGTA.ConnectionWarning = ANKIGTA.ConnectionWarning or {
    emptyTokenDismissed = false,
}

local function text(key, ...)
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.format(key, ...)
    end
    return key
end

local statusWindow = nil
local settingsWindow = nil
-- What each window was built from, so a language change can rebuild it without
-- another round trip to the server.
local lastStatus = nil
local lastSettingsSnapshot = nil
local cursorOwned = false
local cursorWasShowing = false

local function releaseCursor()
    if cursorOwned then
        showCursor(cursorWasShowing)
        cursorOwned = false
        cursorWasShowing = false
    end
end

local function ownCursor()
    if not cursorOwned then
        cursorWasShowing = isCursorShowing()
        cursorOwned = true
        showCursor(true)
    end
end

local function closeStatusWindow()
    if isElement(statusWindow) then
        destroyElement(statusWindow)
    end
    ANKIGTA.Layout.detach("connection")
    statusWindow = nil
    if not isElement(settingsWindow) then
        releaseCursor()
    end
end

local function closeSettingsWindow()
    if isElement(settingsWindow) then
        destroyElement(settingsWindow)
    end
    ANKIGTA.Layout.detach("connectionSettings")
    settingsWindow = nil
    if not isElement(statusWindow) then
        releaseCursor()
    end
end

local function openDisconnectedWindow(status)
    closeStatusWindow()
    local surface = ANKIGTA.Layout.open("connection", text("connection.title"))
    if not surface then
        return
    end
    statusWindow = surface.window
    local width = surface.width
    surface.label(
        18,
        34,
        width - 36,
        38,
        text(
            "connection.disconnected",
            tostring(status.category or "disconnected")
        )
    )
    local connectButton = surface.button(
        18,
        88,
        190,
        36,
        text("connection.connect")
    )
    local advancedButton = surface.button(
        220,
        88,
        190,
        36,
        text("connection.advanced")
    )
    addEventHandler("onClientGUIClick", connectButton, function()
        triggerServerEvent(CONNECT_EVENT, resourceRoot)
    end, false)
    addEventHandler("onClientGUIClick", advancedButton, function()
        triggerServerEvent(SETTINGS_REQUEST_EVENT, resourceRoot)
    end, false)
    ownCursor()
end

local function openSettingsWindow(snapshot)
    closeSettingsWindow()
    local surface = ANKIGTA.Layout.open(
        "connectionSettings", text("connection.settingsTitle")
    )
    if not surface then
        return
    end
    settingsWindow = surface.window
    local width = surface.width
    surface.label(
        18,
        34,
        width - 36,
        22,
        text(
            "connection.currentMode",
            -- The mode is a stable technical value and stays as stored.
            tostring(snapshot.mode or "invalid"),
            snapshot.tokenConfigured
                and text("connection.tokenProtected")
                or text("connection.tokenDisabled")
        )
    )
    surface.label(18, 72, 120, 24, text("connection.manualPort"))
    local portEdit = surface.edit(
        150,
        68,
        280,
        30,
        tostring(snapshot.port or "")
    )
    surface.label(18, 112, 120, 24, text("connection.replacementToken"))
    local tokenEdit = surface.edit(150, 108, 280, 30, "")
    guiEditSetMasked(tokenEdit, true)
    local disableToken = surface.checkBox(
        150,
        146,
        280,
        26,
        text("connection.disableToken"),
        false
    )
    local dismissWarningButton = false
    if snapshot.tokenDisabled
        and not ANKIGTA.ConnectionWarning.emptyTokenDismissed
    then
        dismissWarningButton = surface.button(
            150,
            180,
            280,
            28,
            text("connection.dismissWarning")
        )
    end
    local manualButton = surface.button(
        18,
        220,
        205,
        34,
        text("connection.manualMode")
    )
    local automaticButton = surface.button(
        235,
        220,
        205,
        34,
        text("connection.automaticMode")
    )
    local closeButton = surface.button(18, 264, 422, 30, text("common.close"))
    addEventHandler("onClientGUIClick", manualButton, function()
        local token = guiGetText(tokenEdit)
        local disableTokenSelected = guiCheckBoxGetSelected(disableToken)
        if token ~= "" and disableTokenSelected then
            outputChatBox(
                text("connection.clearTokenFirst"),
                255,
                196,
                96
            )
            return
        end
        ANKIGTA.ConnectionWarning.emptyTokenDismissed = false
        triggerServerEvent(
            SETTINGS_UPDATE_EVENT,
            resourceRoot,
            {
                mode = "manual",
                port = tonumber(guiGetText(portEdit)),
                token = disableTokenSelected and "" or token,
                keepToken = token == "" and not disableTokenSelected,
            }
        )
    end, false)
    addEventHandler("onClientGUIClick", automaticButton, function()
        ANKIGTA.ConnectionWarning.emptyTokenDismissed = false
        triggerServerEvent(
            SETTINGS_UPDATE_EVENT,
            resourceRoot,
            {mode = "automatic"}
        )
    end, false)
    if isElement(dismissWarningButton) then
        addEventHandler(
            "onClientGUIClick",
            dismissWarningButton,
            function()
                ANKIGTA.ConnectionWarning.emptyTokenDismissed = true
                destroyElement(dismissWarningButton)
            end,
            false
        )
    end
    addEventHandler(
        "onClientGUIClick",
        closeButton,
        closeSettingsWindow,
        false
    )
    ownCursor()
end

addEvent(STATUS_EVENT, true)
addEventHandler(STATUS_EVENT, resourceRoot, function(status)
    if source ~= resourceRoot or type(status) ~= "table" then
        return
    end
    lastStatus = status
    if status.state == "connected" then
        closeStatusWindow()
    elseif status.state ~= "connecting" then
        openDisconnectedWindow(status)
    end
end)

addEvent(SETTINGS_SNAPSHOT_EVENT, true)
addEventHandler(SETTINGS_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if source == resourceRoot and type(snapshot) == "table" then
        lastSettingsSnapshot = snapshot
        openSettingsWindow(snapshot)
    end
end)

-- Both windows write their labels and their control geometry when they are
-- built, so a language change and a scale change are the same rebuild.
local function rebuildOpenWindows()
    if isElement(statusWindow) and lastStatus then
        openDisconnectedWindow(lastStatus)
    end
    if isElement(settingsWindow) and lastSettingsSnapshot then
        openSettingsWindow(lastSettingsSnapshot)
    end
end

if ANKIGTA.Locale then
    ANKIGTA.Locale.onChange(rebuildOpenWindows)
end

if ANKIGTA.Layout then
    ANKIGTA.Layout.onChange(rebuildOpenWindows)
end

addCommandHandler("ankigta-connect", function()
    triggerServerEvent(CONNECT_EVENT, resourceRoot)
end)

addCommandHandler("ankigta-connection", function()
    triggerServerEvent(SETTINGS_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, function()
    closeSettingsWindow()
    closeStatusWindow()
end)

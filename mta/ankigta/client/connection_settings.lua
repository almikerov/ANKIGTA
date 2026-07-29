local STATUS_EVENT = "ankigta:companionStatus"
local CONNECT_EVENT = "ankigta:connectCompanion"
local SETTINGS_REQUEST_EVENT = "ankigta:requestConnectionSettings"
local SETTINGS_SNAPSHOT_EVENT = "ankigta:connectionSettingsSnapshot"
local SETTINGS_UPDATE_EVENT = "ankigta:updateConnectionSettings"

ANKIGTA = ANKIGTA or {}
ANKIGTA.ConnectionWarning = ANKIGTA.ConnectionWarning or {
    emptyTokenDismissed = false,
}

local statusWindow = nil
local settingsWindow = nil
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
    statusWindow = nil
    if not isElement(settingsWindow) then
        releaseCursor()
    end
end

local function closeSettingsWindow()
    if isElement(settingsWindow) then
        destroyElement(settingsWindow)
    end
    settingsWindow = nil
    if not isElement(statusWindow) then
        releaseCursor()
    end
end

local function openDisconnectedWindow(status)
    closeStatusWindow()
    local width = 430
    local height = 150
    local screenWidth, screenHeight = guiGetScreenSize()
    statusWindow = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        "ANKIGTA — Companion Connection",
        false
    )
    guiCreateLabel(
        18,
        34,
        width - 36,
        38,
        "Соединение отключено: " .. tostring(status.category or "disconnected"),
        false,
        statusWindow
    )
    local connectButton = guiCreateButton(
        18,
        88,
        190,
        36,
        "Подключиться",
        false,
        statusWindow
    )
    local advancedButton = guiCreateButton(
        220,
        88,
        190,
        36,
        "Advanced settings…",
        false,
        statusWindow
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
    local width = 470
    local height = 330
    local screenWidth, screenHeight = guiGetScreenSize()
    settingsWindow = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        "ANKIGTA — Connection settings",
        false
    )
    guiCreateLabel(
        18,
        34,
        width - 36,
        22,
        "Current mode: " .. tostring(snapshot.mode or "invalid")
            .. "; token: "
            .. (snapshot.tokenConfigured and "protected (hidden)" or "disabled"),
        false,
        settingsWindow
    )
    guiCreateLabel(18, 72, 120, 24, "Manual port", false, settingsWindow)
    local portEdit = guiCreateEdit(
        150,
        68,
        280,
        30,
        tostring(snapshot.port or ""),
        false,
        settingsWindow
    )
    guiCreateLabel(
        18,
        112,
        120,
        24,
        "Replacement token (blank keeps current)",
        false,
        settingsWindow
    )
    local tokenEdit = guiCreateEdit(
        150,
        108,
        280,
        30,
        "",
        false,
        settingsWindow
    )
    guiEditSetMasked(tokenEdit, true)
    local disableToken = guiCreateCheckBox(
        150,
        146,
        280,
        26,
        "Disable token explicitly",
        false,
        false,
        settingsWindow
    )
    local dismissWarningButton = false
    if snapshot.tokenDisabled
        and not ANKIGTA.ConnectionWarning.emptyTokenDismissed
    then
        dismissWarningButton = guiCreateButton(
            150,
            180,
            280,
            28,
            "Dismiss empty-token warning",
            false,
            settingsWindow
        )
    end
    local manualButton = guiCreateButton(
        18,
        220,
        205,
        34,
        "Manual Connection Mode",
        false,
        settingsWindow
    )
    local automaticButton = guiCreateButton(
        235,
        220,
        205,
        34,
        "Automatic Connection Mode",
        false,
        settingsWindow
    )
    local closeButton = guiCreateButton(
        18,
        264,
        422,
        30,
        "Close",
        false,
        settingsWindow
    )
    addEventHandler("onClientGUIClick", manualButton, function()
        local token = guiGetText(tokenEdit)
        local disableTokenSelected = guiCheckBoxGetSelected(disableToken)
        if token ~= "" and disableTokenSelected then
            outputChatBox(
                "ANKIGTA: clear the replacement token before disabling it.",
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
    if status.state == "connected" then
        closeStatusWindow()
    elseif status.state ~= "connecting" then
        openDisconnectedWindow(status)
    end
end)

addEvent(SETTINGS_SNAPSHOT_EVENT, true)
addEventHandler(SETTINGS_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if source == resourceRoot and type(snapshot) == "table" then
        openSettingsWindow(snapshot)
    end
end)

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

local SETTINGS_FILE = "@ui_settings.xml"
--- The key the panel opens on when nothing has been chosen yet.
-- Kept here rather than in `config.lua`: that file is declared server-side
-- only, so `HOTRELOAD_CONFIG` does not exist on this side.
local DEFAULT_OPEN_KEY = "F6"
--- Keys that cannot be the open key. A mouse button would fire while clicking
-- inside the very panel it opens, and these two are how you get out of it.
local UNBINDABLE_KEYS = {
    ["mouse1"] = true, ["mouse2"] = true, ["mouse3"] = true,
    ["mouse4"] = true, ["mouse5"] = true,
    ["mouse_wheel_up"] = true, ["mouse_wheel_down"] = true,
    ["escape"] = true, ["enter"] = true,
}
--- How many changed files go to chat before it stops listing them. The panel
-- shows all of them; chat is a notification, not the report.
local CHAT_CHANGE_LIMIT = 5

local currentLanguage = "en"
local openKey = DEFAULT_OPEN_KEY
local lastCatalog = nil
--- The last change report, kept so that rebuilding the window for another
-- language does not throw away what it was showing.
local lastChange = nil
local awaitingKey = false

local TEXT = {
    en = {
        title = "MTA Hot Reload — Resources",
        resource = "Resource",
        state = "MTA state",
        hotReload = "Hot Reload",
        selectResource = "Select a resource in the table",
        updating = "Updating resource list...",
        saving = "Saving...",
        initial = "Click Refresh list to read the current MTA state",
        allow = "Allow",
        ignore = "Ignore",
        toggle = "Toggle status",
        allowSelected = "Allow selected",
        ignoreSelected = "Ignore selected",
        protectedSelected = "Protected resource",
        search = "Search:",
        showAllowedOnly = "Show allowed only",
        customOnly = "Custom resources only",
        refresh = "Refresh list",
        reload = "Reload allowed",
        discover = "Find new",
        autoupdate = "Autoupdate (watch files)",
        startup = "Startup",
        toggleStartup = "Toggle startup",
        startupOn = "yes",
        startupOff = "—",
        close = "Close",
        start = "Start",
        stop = "Stop",
        restart = "Restart",
        detected = "Showing: %d of %d | Allowed: %d",
        panelHint = "[dev_hotreload] Resource manager: %s",
        allowed = "allowed",
        ignored = "ignored",
        blocked = "blocked",
        noPermission = "Missing ACL permission: command.hotreload (you are not logged in as an administrator)",
        refreshFailed = "MTA could not refresh the resource catalog",
        invalidMode = "Invalid resource mode",
        changesTitle = "Last change",
        changesNone = "No change reported yet",
        changesIn = "%s — %d file(s)",
        changeFile = "File",
        changeCount = "Change",
        openKeyButton = "Open key: %s",
        pressKey = "Press the new key — Escape cancels",
        keySaved = "Panel now opens on %s",
        keyCancelled = "Key unchanged",
        keyRefused = "That key cannot be used; pick another",
    },
    ru = {
        title = "MTA Hot Reload — Ресурсы",
        resource = "Ресурс",
        state = "Состояние MTA",
        hotReload = "Hot Reload",
        selectResource = "Выберите ресурс в таблице",
        updating = "Обновление списка ресурсов...",
        saving = "Сохранение...",
        initial = "Нажмите «Обновить список», чтобы прочитать состояние MTA",
        allow = "Разрешить",
        ignore = "Игнорировать",
        toggle = "Переключить статус",
        allowSelected = "Разрешить выбранный",
        ignoreSelected = "Игнорировать выбранный",
        protectedSelected = "Защищённый ресурс",
        search = "Поиск:",
        showAllowedOnly = "Только разрешённые",
        customOnly = "Только пользовательские",
        refresh = "Обновить список",
        reload = "Перезагрузить разрешённые",
        discover = "Найти новые",
        autoupdate = "Автообновление (следить за файлами)",
        startup = "Автозапуск",
        toggleStartup = "Переключить автозапуск",
        startupOn = "да",
        startupOff = "—",
        close = "Закрыть",
        start = "Запустить",
        stop = "Остановить",
        restart = "Перезапустить",
        detected = "Показано: %d из %d | Разрешено: %d",
        panelHint = "[dev_hotreload] Панель ресурсов: %s",
        allowed = "разрешён",
        ignored = "игнорируется",
        blocked = "заблокирован",
        noPermission = "Нет ACL-права command.hotreload (вы не вошли как администратор)",
        refreshFailed = "MTA не смог обновить каталог ресурсов",
        invalidMode = "Некорректный режим ресурса",
        changesTitle = "Последнее изменение",
        changesNone = "Изменений пока не было",
        changesIn = "%s — файлов: %d",
        changeFile = "Файл",
        changeCount = "Изменение",
        openKeyButton = "Клавиша: %s",
        pressKey = "Нажмите новую клавишу — Escape отменяет",
        keySaved = "Панель теперь открывается на %s",
        keyCancelled = "Клавиша не изменена",
        keyRefused = "Эту клавишу использовать нельзя, выберите другую",
    },
}

local UI = {}

local view = {
    search = "",
    showAllowedOnly = false,
    customOnly = false,
}

local selectedResource = nil

local function text(key)
    return TEXT[currentLanguage][key] or TEXT.en[key] or key
end

-- --- stored preferences ------------------------------------------------------

local function loadSettings()
    local settings = xmlLoadFile(SETTINGS_FILE)
    if not settings then
        return
    end
    local saved = xmlNodeGetAttribute(settings, "language")
    if saved == "en" or saved == "ru" then
        currentLanguage = saved
    end
    local savedKey = xmlNodeGetAttribute(settings, "openKey")
    if type(savedKey) == "string" and savedKey ~= "" then
        openKey = savedKey
    end
    xmlUnloadFile(settings)
end

local function saveSettings()
    local settings = xmlLoadFile(SETTINGS_FILE)
    if not settings then
        settings = xmlCreateFile(SETTINGS_FILE, "settings")
    end
    if not settings then
        return false
    end
    xmlNodeSetAttribute(settings, "language", currentLanguage)
    xmlNodeSetAttribute(settings, "openKey", openKey)
    local saved = xmlSaveFile(settings)
    xmlUnloadFile(settings)
    return saved
end

local function setStatus(message, isError)
    if not UI.status or not isElement(UI.status) then
        return
    end
    guiSetText(UI.status, message or "")
    guiLabelSetColor(UI.status, isError and 220 or 180, isError and 70 or 220, isError and 70 or 180)
end

local function selectedResourceDetails(showError)
    local row = guiGridListGetSelectedItem(UI.grid)
    if row == -1 then
        if showError then
            setStatus(text("selectResource"), true)
        end
        return nil, nil
    end
    return guiGridListGetItemData(UI.grid, row, 1),
        guiGridListGetItemData(UI.grid, row, 3),
        guiGridListGetItemData(UI.grid, row, 4) == true
end

--- Turn "start this when the server starts" on or off for the selected row.
--
-- Independent of Hot Reload: a resource can be started at boot without being
-- watched, and watched without being started, so this is its own switch rather
-- than a second meaning for the existing one.
local function toggleSelectedStartup()
    local resourceName, _, startup = selectedResourceDetails(true)
    if not resourceName then
        return
    end
    setStatus(text("saving"), false)
    triggerServerEvent(
        "dev_hotreload:setStartup", resourceRoot, resourceName, not startup
    )
end

--- Plain resource control for the selected row: start, stop or restart it.
--
-- No parameters to type, which is the whole point of having it here rather
-- than at the console. It applies to any row the server will act on, including
-- one Hot Reload is set to ignore -- watching files and running a resource are
-- separate questions.
local function controlSelected(action)
    local resourceName, mode = selectedResourceDetails(true)
    if not resourceName then
        return
    end
    if mode == "blocked" then
        setStatus(text("protectedSelected"), true)
        return
    end
    setStatus(text("saving"), false)
    triggerServerEvent(
        "dev_hotreload:controlResource", resourceRoot, resourceName, action
    )
end

local function updateActionButton()
    if not UI.actionButton or not isElement(UI.actionButton) then
        return
    end
    local resourceName, mode, startup = selectedResourceDetails(false)
    selectedResource = resourceName
    local protected = mode == "blocked"
    if UI.startupButton and isElement(UI.startupButton) then
        -- A protected resource is one Hot Reload will not touch, but the
        -- server still starts it, so startup stays available for it.
        guiSetEnabled(UI.startupButton, resourceName ~= nil)
        guiSetText(
            UI.startupButton,
            text("toggleStartup") .. (startup and " ✓" or "")
        )
    end
    for _, button in ipairs({UI.startButton, UI.stopButton, UI.restartButton}) do
        if button and isElement(button) then
            guiSetEnabled(button, resourceName ~= nil and not protected)
        end
    end
    if mode == "allowed" then
        guiSetText(UI.actionButton, text("ignoreSelected"))
        guiSetEnabled(UI.actionButton, true)
    elseif mode == "ignored" then
        guiSetText(UI.actionButton, text("allowSelected"))
        guiSetEnabled(UI.actionButton, true)
    elseif protected then
        guiSetText(UI.actionButton, text("protectedSelected"))
        guiSetEnabled(UI.actionButton, false)
    else
        guiSetText(UI.actionButton, text("toggle"))
        guiSetEnabled(UI.actionButton, false)
    end
end

local function requestCatalog(refreshMTA)
    setStatus(text("updating"), false)
    triggerServerEvent("dev_hotreload:requestCatalog", resourceRoot, refreshMTA == true)
end

local function toggleSelectedMode()
    local resourceName, mode = selectedResourceDetails(true)
    if not resourceName then
        return
    end
    if mode == "blocked" then
        setStatus(text("protectedSelected"), true)
        return
    end
    if mode ~= "allowed" and mode ~= "ignored" then
        return
    end
    setStatus(text("saving"), false)
    triggerServerEvent("dev_hotreload:setManaged", resourceRoot, resourceName, mode ~= "allowed")
end

local function localizedMode(mode)
    return text(mode) or tostring(mode)
end

local function updateViewFromControls()
    view.search = guiGetText(UI.search):lower()
    view.showAllowedOnly = guiCheckBoxGetSelected(UI.showAllowedOnly)
    view.customOnly = guiCheckBoxGetSelected(UI.customOnly)
end

local function resourceMatchesView(item)
    local name = tostring(item.name or "")
    if view.search ~= "" and not name:lower():find(view.search, 1, true) then
        return false
    end
    if view.showAllowedOnly and item.hotReload ~= "allowed" then
        return false
    end
    if view.customOnly and item.custom ~= true then
        return false
    end
    return true
end

-- --- the change report -------------------------------------------------------

--- `+12 -3`, or a plain word where the file was too large to have been kept.
local function formatCount(change)
    if type(change.added) == "number" and type(change.removed) == "number" then
        return ("+%d -%d"):format(change.added, change.removed)
    end
    return "?"
end

local function populateChanges()
    if not UI.changes or not isElement(UI.changes) then
        return
    end
    guiGridListClear(UI.changes)
    if not lastChange or type(lastChange.changes) ~= "table"
        or #lastChange.changes == 0
    then
        if UI.changesHeader and isElement(UI.changesHeader) then
            guiSetText(UI.changesHeader, text("changesTitle") .. ": " .. text("changesNone"))
        end
        return
    end
    if UI.changesHeader and isElement(UI.changesHeader) then
        guiSetText(UI.changesHeader, text("changesTitle") .. ": "
            .. text("changesIn"):format(
                tostring(lastChange.resource), #lastChange.changes
            ))
    end
    for _, change in ipairs(lastChange.changes) do
        local row = guiGridListAddRow(UI.changes)
        guiGridListSetItemText(UI.changes, row, 1, tostring(change.file), false, false)
        guiGridListSetItemText(UI.changes, row, 2, formatCount(change), false, false)
        if change.status == "added" then
            guiGridListSetItemColor(UI.changes, row, 1, 120, 220, 140)
        elseif change.status == "removed" then
            guiGridListSetItemColor(UI.changes, row, 1, 230, 130, 130)
        end
        -- Green when the file only grew, red when it only shrank, plain when
        -- both moved: the colour is about direction, not about importance.
        if type(change.added) == "number" and type(change.removed) == "number" then
            if change.added > 0 and change.removed == 0 then
                guiGridListSetItemColor(UI.changes, row, 2, 120, 220, 140)
            elseif change.removed > 0 and change.added == 0 then
                guiGridListSetItemColor(UI.changes, row, 2, 230, 130, 130)
            end
        end
    end
end

local function populateCatalog(payload)
    if not UI.grid or not isElement(UI.grid) then
        return
    end
    payload = type(payload) == "table" and payload or {}
    guiGridListClear(UI.grid)
    local resources = type(payload.resources) == "table" and payload.resources or {}
    local visibleCount = 0
    for _, item in ipairs(resources) do
        if resourceMatchesView(item) then
            visibleCount = visibleCount + 1
            local row = guiGridListAddRow(UI.grid)
            guiGridListSetItemText(UI.grid, row, 1, tostring(item.name), false, false)
            guiGridListSetItemText(UI.grid, row, 2, tostring(item.state), false, false)
            guiGridListSetItemText(UI.grid, row, 3, localizedMode(item.hotReload), false, false)
            guiGridListSetItemText(
                UI.grid, row, 4,
                item.startup and text("startupOn") or text("startupOff"),
                false, false
            )
            guiGridListSetItemData(UI.grid, row, 1, item.name)
            guiGridListSetItemData(UI.grid, row, 3, item.hotReload)
            guiGridListSetItemData(UI.grid, row, 4, item.startup == true)
            if item.startup then
                guiGridListSetItemColor(UI.grid, row, 4, 120, 190, 255)
            end
            if item.state == "running" then
                guiGridListSetItemColor(UI.grid, row, 2, 120, 210, 140)
            end
            if item.hotReload == "allowed" then
                guiGridListSetItemColor(UI.grid, row, 3, 80, 210, 110)
            elseif item.hotReload == "blocked" then
                guiGridListSetItemColor(UI.grid, row, 3, 220, 80, 80)
            else
                guiGridListSetItemColor(UI.grid, row, 3, 190, 190, 190)
            end
            if item.name == selectedResource then
                guiGridListSetSelectedItem(UI.grid, row, 1)
            end
        end
    end
    -- The checkbox follows the server rather than the last click: the setting
    -- lives there, and two players with the panel open would otherwise
    -- disagree about it.
    if UI.autoupdate then
        guiCheckBoxSetSelected(UI.autoupdate, payload.autoupdate == true)
    end
    setStatus(text("detected"):format(visibleCount, #resources, tonumber(payload.allowedCount) or 0), false)
    updateActionButton()
end

local createInterface
--- Declared here, defined below the window it opens.
--
-- A plain local rather than a field on `UI`, because `changeLanguage` replaces
-- that whole table: `unbindKey` matches on the exact function it was given, so
-- a handler that gets wiped on a language change could never be unbound and
-- rebinding the open key would silently leave the old key working too.
local toggleInterface

local function changeLanguage()
    updateViewFromControls()
    local selected = guiComboBoxGetSelected(UI.language)
    local selectedLanguage = selected == 1 and "ru" or "en"
    if selectedLanguage == currentLanguage then
        return
    end
    currentLanguage = selectedLanguage
    saveSettings()
    if UI.window and isElement(UI.window) then
        destroyElement(UI.window)
    end
    UI = {}
    createInterface()
    guiSetVisible(UI.window, true)
    showCursor(true)
    populateChanges()
    if lastCatalog then
        populateCatalog(lastCatalog)
    else
        requestCatalog(false)
    end
end

-- --- choosing the key the panel opens on -------------------------------------

local finishKeyCapture

local function onCaptureKey(button, press)
    if not press then
        return
    end
    -- Held while choosing, so the key being chosen does not also fire whatever
    -- it was bound to before.
    cancelEvent()
    if button == "escape" then
        finishKeyCapture(nil)
        return
    end
    if UNBINDABLE_KEYS[button] then
        setStatus(text("keyRefused"), true)
        return
    end
    finishKeyCapture(button)
end

finishKeyCapture = function(chosen)
    if not awaitingKey then
        return
    end
    awaitingKey = false
    removeEventHandler("onClientKey", root, onCaptureKey)
    if not chosen then
        setStatus(text("keyCancelled"), false)
    elseif chosen ~= openKey then
        unbindKey(openKey, "down", toggleInterface)
        openKey = chosen
        bindKey(openKey, "down", toggleInterface)
        saveSettings()
        setStatus(text("keySaved"):format(openKey), false)
    else
        setStatus(text("keyCancelled"), false)
    end
    if UI.keyButton and isElement(UI.keyButton) then
        guiSetText(UI.keyButton, text("openKeyButton"):format(openKey))
    end
end

local function beginKeyCapture()
    if awaitingKey then
        return
    end
    awaitingKey = true
    setStatus(text("pressKey"), false)
    addEventHandler("onClientKey", root, onCaptureKey)
end

-- --- the window --------------------------------------------------------------

createInterface = function()
    local screenWidth, screenHeight = guiGetScreenSize()
    local width = math.min(860, screenWidth - 60)
    local height = math.min(660, screenHeight - 60)
    UI.window = guiCreateWindow((screenWidth - width) / 2, (screenHeight - height) / 2, width, height, text("title"), false)
    guiWindowSetSizable(UI.window, true)

    guiCreateLabel(12, 33, 54, 22, text("search"), false, UI.window)
    UI.search = guiCreateEdit(70, 28, width - 370, 26, view.search, false, UI.window)

    guiCreateLabel(width - 288, 33, 135, 22, "Language / Язык:", false, UI.window)
    UI.language = guiCreateComboBox(width - 148, 28, 136, 88, "", false, UI.window)
    guiComboBoxAddItem(UI.language, "English")
    guiComboBoxAddItem(UI.language, "Русский")
    guiComboBoxSetSelected(UI.language, currentLanguage == "ru" and 1 or 0)

    UI.showAllowedOnly = guiCreateCheckBox(12, 61, 260, 22, text("showAllowedOnly"), view.showAllowedOnly, false, UI.window)
    UI.customOnly = guiCreateCheckBox(280, 61, 220, 22, text("customOnly"), view.customOnly, false, UI.window)
    -- Off until asked for: watching reads every file of every allowed resource
    -- on every tick, and that is a cost nobody should pay by default.
    UI.autoupdate = guiCreateCheckBox(
        510, 61, 280, 22, text("autoupdate"), false, false, UI.window
    )

    -- Laid out from the bottom up, because everything below the resource list
    -- has a fixed height and the list takes whatever is left.
    local buttonRow = height - 46
    local resourceRow = height - 84
    local statusRow = height - 110
    local changesBottom = statusRow - 6
    local changesTop = changesBottom - 104
    local changesHeaderTop = changesTop - 22

    UI.grid = guiCreateGridList(12, 88, width - 24, changesHeaderTop - 92, false, UI.window)
    guiGridListAddColumn(UI.grid, text("resource"), 0.50)
    guiGridListAddColumn(UI.grid, text("state"), 0.22)
    guiGridListAddColumn(UI.grid, text("hotReload"), 0.20)
    guiGridListAddColumn(UI.grid, text("startup"), 0.14)
    guiGridListSetSortingEnabled(UI.grid, false)

    UI.changesHeader = guiCreateLabel(
        16, changesHeaderTop, width - 32, 20,
        text("changesTitle") .. ": " .. text("changesNone"), false, UI.window
    )
    UI.changes = guiCreateGridList(
        12, changesTop, width - 24, changesBottom - changesTop, false, UI.window
    )
    guiGridListAddColumn(UI.changes, text("changeFile"), 0.72)
    guiGridListAddColumn(UI.changes, text("changeCount"), 0.22)
    guiGridListSetSortingEnabled(UI.changes, false)

    UI.status = guiCreateLabel(16, statusRow, width - 32, 20, text("initial"), false, UI.window)
    guiLabelSetVerticalAlign(UI.status, "center")

    -- Row one acts on the selected resource, row two on the server as a whole.
    UI.startButton = guiCreateButton(12, resourceRow, 100, 32, text("start"), false, UI.window)
    UI.stopButton = guiCreateButton(118, resourceRow, 100, 32, text("stop"), false, UI.window)
    UI.restartButton = guiCreateButton(224, resourceRow, 110, 32, text("restart"), false, UI.window)
    UI.actionButton = guiCreateButton(340, resourceRow, 170, 32, text("toggle"), false, UI.window)
    UI.startupButton = guiCreateButton(516, resourceRow, 160, 32, text("toggleStartup"), false, UI.window)
    for _, button in ipairs({
        UI.startButton, UI.stopButton, UI.restartButton,
        UI.actionButton, UI.startupButton,
    }) do
        guiSetEnabled(button, false)
    end

    local reloadButton = guiCreateButton(12, buttonRow, 175, 32, text("reload"), false, UI.window)
    local refreshButton = guiCreateButton(193, buttonRow, 130, 32, text("refresh"), false, UI.window)
    local discoverButton = guiCreateButton(329, buttonRow, 120, 32, text("discover"), false, UI.window)
    UI.keyButton = guiCreateButton(
        455, buttonRow, 180, 32, text("openKeyButton"):format(openKey), false, UI.window
    )
    local closeButton = guiCreateButton(width - 132, buttonRow, 120, 32, text("close"), false, UI.window)

    addEventHandler("onClientGUIClick", UI.actionButton, toggleSelectedMode, false)
    addEventHandler("onClientGUIClick", UI.startButton, function() controlSelected("start") end, false)
    addEventHandler("onClientGUIClick", UI.stopButton, function() controlSelected("stop") end, false)
    addEventHandler("onClientGUIClick", UI.restartButton, function() controlSelected("restart") end, false)
    addEventHandler("onClientGUIClick", refreshButton, function() requestCatalog(true) end, false)
    addEventHandler("onClientGUIClick", discoverButton, function()
        setStatus(text("updating"), false)
        triggerServerEvent("dev_hotreload:discover", resourceRoot)
    end, false)
    addEventHandler("onClientGUIClick", UI.keyButton, beginKeyCapture, false)
    addEventHandler("onClientGUIClick", reloadButton, function()
        setStatus(text("saving"), false)
        triggerServerEvent("dev_hotreload:reloadAll", resourceRoot)
    end, false)
    addEventHandler("onClientGUIClick", UI.autoupdate, function()
        triggerServerEvent(
            "dev_hotreload:setAutoupdate", resourceRoot,
            guiCheckBoxGetSelected(UI.autoupdate) == true
        )
    end, false)
    addEventHandler("onClientGUIClick", UI.startupButton, toggleSelectedStartup, false)
    addEventHandler("onClientGUIComboBoxAccepted", UI.language, changeLanguage, false)
    addEventHandler("onClientGUIChanged", UI.search, function()
        updateViewFromControls()
        populateCatalog(lastCatalog)
    end, false)
    local function filterChanged()
        updateViewFromControls()
        populateCatalog(lastCatalog)
    end
    addEventHandler("onClientGUIClick", UI.showAllowedOnly, filterChanged, false)
    addEventHandler("onClientGUIClick", UI.customOnly, filterChanged, false)
    addEventHandler("onClientGUIClick", UI.grid, updateActionButton, false)
    addEventHandler("onClientGUIDoubleClick", UI.grid, function(button, state)
        if button == "left" and state == "up" then
            toggleSelectedMode()
        end
    end, false)
    addEventHandler("onClientGUIClick", closeButton, function()
        guiSetVisible(UI.window, false)
        showCursor(false)
    end, false)

    guiSetVisible(UI.window, false)
end

toggleInterface = function()
    local visible = not guiGetVisible(UI.window)
    guiSetVisible(UI.window, visible)
    showCursor(visible)
    if visible then
        guiBringToFront(UI.window)
        requestCatalog(false)
    end
end

local function localizeServerMessage(message)
    if currentLanguage ~= "ru" then
        return message
    end
    local exact = {
        ["Missing ACL permission: command.hotreload"] = text("noPermission"),
        ["Missing ACL permission: command.hotreload (you are not logged in as an administrator)"] = text("noPermission"),
        ["MTA could not refresh the resource catalog"] = text("refreshFailed"),
        ["Invalid resource mode"] = text("invalidMode"),
    }
    if exact[message] then
        return exact[message]
    end
    local name = message:match("^(.-) is now allowed$")
    if name then
        return name .. ": разрешён для Hot Reload"
    end
    name = message:match("^(.-) is now ignored$")
    if name then
        return name .. ": игнорируется"
    end
    local action
    name, action = message:match("^(.-): (start)$")
    if not name then name, action = message:match("^(.-): (stop)$") end
    if not name then name, action = message:match("^(.-): (restart)$") end
    if name then
        local verb = action == "start" and "запущен"
            or (action == "stop" and "остановлен" or "перезапущен")
        return name .. ": " .. verb
    end
    if message:match("^ALREADY_RUNNING") then
        return "Ресурс уже запущен"
    end
    if message:match("^NOT_RUNNING") then
        return "Ресурс не запущен"
    end
    if message:match("^RESOURCE_NOT_FOUND") then
        return "MTA не видит такой ресурс"
    end
    if message:match("^ACTION_REFUSED") then
        return "MTA отказал в этом действии (проверьте ACL)"
    end
    return message
end

addEvent("dev_hotreload:catalog", true)
addEventHandler("dev_hotreload:catalog", resourceRoot, function(payload)
    lastCatalog = payload
    populateCatalog(payload)
end)

addEvent("dev_hotreload:message", true)
addEventHandler("dev_hotreload:message", resourceRoot, function(message, isError)
    local localized = localizeServerMessage(tostring(message))
    setStatus(localized, isError == true)
    if isError then
        outputChatBox("[dev_hotreload] " .. localized, 220, 70, 70)
    end
end)

addEvent("dev_hotreload:changed", true)
addEventHandler("dev_hotreload:changed", resourceRoot, function(payload)
    if type(payload) ~= "table" or type(payload.changes) ~= "table" then
        return
    end
    lastChange = payload
    populateChanges()
    outputChatBox(
        ("[dev_hotreload] %s — %d file(s) changed"):format(
            tostring(payload.resource), #payload.changes
        ), 120, 190, 255
    )
    for index, change in ipairs(payload.changes) do
        if index > CHAT_CHANGE_LIMIT then
            outputChatBox(("  ... %d more"):format(#payload.changes - CHAT_CHANGE_LIMIT), 150, 150, 150)
            break
        end
        outputChatBox(
            ("  %s  %s"):format(tostring(change.file), formatCount(change)),
            170, 200, 230
        )
    end
end)

addEventHandler("onClientResourceStart", resourceRoot, function()
    loadSettings()
    createInterface()
    if not bindKey(openKey, "down", toggleInterface) then
        -- A key name saved by an older build, or one this MTA does not know.
        -- Falling back beats a panel that cannot be opened at all.
        outputChatBox(
            ("[dev_hotreload] '%s' is not a key; falling back to %s")
                :format(tostring(openKey), DEFAULT_OPEN_KEY), 220, 150, 70
        )
        openKey = DEFAULT_OPEN_KEY
        bindKey(openKey, "down", toggleInterface)
        saveSettings()
        if UI.keyButton and isElement(UI.keyButton) then
            guiSetText(UI.keyButton, text("openKeyButton"):format(openKey))
        end
    end
    outputChatBox(text("panelHint"):format(openKey), 100, 210, 130)
end)

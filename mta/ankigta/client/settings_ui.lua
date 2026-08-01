ANKIGTA = ANKIGTA or {}

-- The settings panel, reachable from F7 and from Review Mode.
--
-- It is built from the schema rather than from a hand-written list of rows, so
-- a setting added later appears here instead of quietly becoming unreachable.
-- Which control a setting gets, and which side is asked to store it, both come
-- from the schema too: the panel has no opinion about authority of its own.
--
-- Nothing is clamped. A value the schema rejects is shown back with the reason
-- the schema gave, translated -- a mistyped 200 silently becoming 50 would
-- leave the user with a setting they never chose and no way to notice.

local SETTINGS_REQUEST_EVENT = "ankigta:requestSettings"
local SETTINGS_SNAPSHOT_EVENT = "ankigta:settingsSnapshot"
local SETTINGS_UPDATE_EVENT = "ankigta:updateSetting"
local SETTINGS_REJECTED_EVENT = "ankigta:settingRejected"
local CONNECTION_SETTINGS_REQUEST_EVENT = "ankigta:requestConnectionSettings"
local OPEN_SETTINGS_EVENT = "ankigta:openSettings"

local WIDTH = 760
local ROW_HEIGHT = 30
local LABEL_X, LABEL_WIDTH = 16, 250
local CONTROL_X, CONTROL_WIDTH = 274, 190
local APPLY_X, APPLY_WIDTH = 472, 90
local ERROR_X, ERROR_WIDTH = 570, 174

local SettingsUI = {
    window = false,
    controls = {},
    mapControls = {},
    serverValues = {},
    maps = {},
    rejection = false,
}

local cursorOwned = false
local cursorWasShowing = false

local function label(key)
    -- Read at draw time, so switching language needs no resource restart.
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.text(key)
    end
    return key
end

local function schema()
    return ANKIGTA.Settings
end

local function ownedByServer(key)
    return schema().authorityOf(key) == schema().SERVER
end

local function currentValue(key)
    if ownedByServer(key) then
        local value = SettingsUI.serverValues[key]
        if value ~= nil then
            return value
        end
        return schema().default(key)
    end
    if ANKIGTA.ClientSettings then
        return ANKIGTA.ClientSettings.get(key)
    end
    return schema().default(key)
end

local function valueLabel(value)
    return label("settings.value." .. tostring(value))
end

-- ---------------------------------------------------------------- rejection

local function showRejection(key, reason)
    SettingsUI.rejection = {key = key, reason = reason}
    local entry = SettingsUI.controls[key]
    if entry and isElement(entry.errorLabel) then
        guiSetText(entry.errorLabel, label(reason))
    end
end

local function clearRejection(key)
    if SettingsUI.rejection and SettingsUI.rejection.key == key then
        SettingsUI.rejection = false
    end
    local entry = SettingsUI.controls[key]
    if entry and isElement(entry.errorLabel) then
        guiSetText(entry.errorLabel, "")
    end
end

-- ------------------------------------------------------------------ writing

--- The one path every change takes, whichever control started it.
function SettingsUI.propose(key, value, mapId)
    local valid, reason = schema().validate(key, value)
    if not valid then
        showRejection(key, reason)
        return false, reason
    end

    if ownedByServer(key) then
        -- Nothing is redrawn here on purpose. Snapping the field back to the
        -- old value while the server is still deciding would look exactly like
        -- a rejection; the snapshot that follows is what shows the new value.
        triggerServerEvent(
            SETTINGS_UPDATE_EVENT,
            resourceRoot,
            key,
            value,
            mapId
        )
        clearRejection(key)
        return true
    end

    local stored, storeReason = ANKIGTA.ClientSettings.set(key, value)
    if not stored then
        showRejection(key, storeReason)
        return false, storeReason
    end
    clearRejection(key)
    SettingsUI.refresh()
    return true
end

--- Apply what was typed into a number field.
function SettingsUI.applyNumber(key)
    local entry = SettingsUI.controls[key]
    if not entry or not isElement(entry.element) then
        return false
    end
    local typed = guiGetText(entry.element)
    -- Hand the raw text over when it is not a number at all, so the schema is
    -- the one that decides it is not a number.
    return SettingsUI.propose(key, tonumber(typed) or typed)
end

function SettingsUI.toggle(key, value)
    return SettingsUI.propose(key, value == true)
end

function SettingsUI.chooseValue(key, value)
    return SettingsUI.propose(key, value)
end

function SettingsUI.setMapIncluded(mapId, includeInStudy)
    return SettingsUI.propose("includeInStudy", includeInStudy == true, mapId)
end

-- ------------------------------------------------------------------ drawing

local function nextChoice(key, value)
    local values = schema().definition(key).rule.values
    for index, candidate in ipairs(values) do
        if candidate == value then
            return values[index % #values + 1]
        end
    end
    return values[1]
end

local function addRow(parent, y, key)
    local entry = {labelKey = "settings." .. key}
    entry.label = guiCreateLabel(
        LABEL_X,
        y,
        LABEL_WIDTH,
        24,
        label(entry.labelKey),
        false,
        parent
    )
    entry.errorLabel = guiCreateLabel(
        ERROR_X,
        y,
        ERROR_WIDTH,
        24,
        "",
        false,
        parent
    )
    return entry
end

local function buildNumberRow(parent, y, key)
    local entry = addRow(parent, y, key)
    entry.kind = "number"
    entry.element = guiCreateEdit(
        CONTROL_X,
        y - 4,
        CONTROL_WIDTH,
        26,
        tostring(currentValue(key)),
        false,
        parent
    )
    entry.applyButton = guiCreateButton(
        APPLY_X,
        y - 4,
        APPLY_WIDTH,
        26,
        label("settings.apply"),
        false,
        parent
    )
    addEventHandler("onClientGUIClick", entry.applyButton, function()
        SettingsUI.applyNumber(key)
    end, false)
    return entry
end

local function buildBooleanRow(parent, y, key)
    local entry = addRow(parent, y, key)
    entry.kind = "boolean"
    entry.element = guiCreateCheckBox(
        CONTROL_X,
        y,
        CONTROL_WIDTH,
        24,
        "",
        currentValue(key) == true,
        false,
        parent
    )
    addEventHandler("onClientGUIClick", entry.element, function()
        SettingsUI.toggle(key, guiCheckBoxGetSelected(entry.element))
    end, false)
    return entry
end

local function buildChoiceRow(parent, y, key)
    local entry = addRow(parent, y, key)
    entry.kind = "choice"
    entry.element = guiCreateButton(
        CONTROL_X,
        y - 4,
        CONTROL_WIDTH,
        26,
        valueLabel(currentValue(key)),
        false,
        parent
    )
    addEventHandler("onClientGUIClick", entry.element, function()
        SettingsUI.chooseValue(key, nextChoice(key, currentValue(key)))
    end, false)
    return entry
end

local function buildDelegatedRow(parent, y, key)
    -- The add-on owns the connection and publishes it; the panel only points at
    -- the window that already knows how to edit an override.
    local entry = addRow(parent, y, key)
    entry.kind = "delegated"
    entry.element = guiCreateButton(
        CONTROL_X,
        y - 4,
        CONTROL_WIDTH,
        26,
        label("settings.connectionSettings"),
        false,
        parent
    )
    addEventHandler("onClientGUIClick", entry.element, function()
        triggerServerEvent(CONNECTION_SETTINGS_REQUEST_EVENT, resourceRoot)
    end, false)
    return entry
end

local function buildMapsRow(parent, y, key)
    -- Per map, not global: one checkbox below per map the server knows about.
    local entry = addRow(parent, y, key)
    entry.kind = "maps"
    entry.element = false
    return entry
end

local function buildMapRows(parent, y)
    SettingsUI.mapControls = {}
    if #SettingsUI.maps == 0 then
        guiCreateLabel(
            LABEL_X,
            y,
            WIDTH - 32,
            24,
            label("settings.noMaps"),
            false,
            parent
        )
        return y + ROW_HEIGHT
    end
    for _, map in ipairs(SettingsUI.maps) do
        guiCreateLabel(
            LABEL_X + 16,
            y,
            LABEL_WIDTH,
            24,
            tostring(map.mapName or map.mapId),
            false,
            parent
        )
        local checkBox = guiCreateCheckBox(
            CONTROL_X,
            y,
            CONTROL_WIDTH,
            24,
            "",
            map.includeInStudy ~= false,
            false,
            parent
        )
        SettingsUI.mapControls[map.mapId] = checkBox
        local mapId = map.mapId
        addEventHandler("onClientGUIClick", checkBox, function()
            SettingsUI.setMapIncluded(mapId, guiCheckBoxGetSelected(checkBox))
        end, false)
        y = y + ROW_HEIGHT
    end
    return y
end

local BUILDERS = {
    number = buildNumberRow,
    boolean = buildBooleanRow,
    choice = buildChoiceRow,
}

--- Which control a setting gets: its owner first, then its rule.
--
-- The add-on's settings are delegated whatever their rule says. A port is a
-- number, but editing it here would make this panel a second writer of a value
-- the add-on publishes.
local function builderFor(definition)
    if definition.authority == schema().ADDON then
        return buildDelegatedRow
    end
    return BUILDERS[definition.rule.kind] or buildDelegatedRow
end

local function placement(height)
    local stored = ANKIGTA.ClientSettings
        and ANKIGTA.ClientSettings.get("uiPlacement")
    if type(stored) == "table"
        and tonumber(stored.x)
        and tonumber(stored.y)
    then
        return tonumber(stored.x), tonumber(stored.y)
    end
    local screenWidth, screenHeight = guiGetScreenSize()
    return (screenWidth - WIDTH) / 2, (screenHeight - height) / 2
end

local function render()
    if isElement(SettingsUI.window) then
        destroyElement(SettingsUI.window)
    end
    SettingsUI.controls = {}
    SettingsUI.mapControls = {}

    local keys = schema().orderedKeys()
    for _, key in ipairs(keys) do
        -- Show the schema's default until the owner says otherwise, so a panel
        -- opened before the server answers still shows real values.
        if ownedByServer(key) and SettingsUI.serverValues[key] == nil then
            SettingsUI.serverValues[key] = schema().default(key)
        end
    end
    local height = 76 + (#keys + math.max(#SettingsUI.maps, 1)) * ROW_HEIGHT
    local x, y = placement(height)
    SettingsUI.window = guiCreateWindow(
        x,
        y,
        WIDTH,
        height,
        label("settings.title"),
        false
    )

    local row = 32
    for _, key in ipairs(keys) do
        local definition = schema().definition(key)
        if key == "uiPlacement" then
            -- Changed by dragging the window, not by typing coordinates.
            SettingsUI.controls[key] = {
                kind = "placement",
                element = SettingsUI.window,
                label = false,
                labelKey = false,
            }
        elseif key == "includeInStudy" then
            SettingsUI.controls[key] = buildMapsRow(SettingsUI.window, row, key)
            row = buildMapRows(SettingsUI.window, row + ROW_HEIGHT)
        else
            SettingsUI.controls[key] =
                builderFor(definition)(SettingsUI.window, row, key)
            row = row + ROW_HEIGHT
        end
    end

    local closeButton = guiCreateButton(
        WIDTH - 122,
        height - 40,
        106,
        28,
        label("settings.close"),
        false,
        SettingsUI.window
    )
    addEventHandler("onClientGUIClick", closeButton, function()
        closeSettings()
    end, false)

    if not cursorOwned then
        cursorWasShowing = isCursorShowing()
        cursorOwned = true
        showCursor(true)
    end
end

--- Update every label and value in place, without rebuilding the panel.
function SettingsUI.refresh()
    if not isElement(SettingsUI.window) then
        return false
    end
    guiSetText(SettingsUI.window, label("settings.title"))
    for key, entry in pairs(SettingsUI.controls) do
        if entry.labelKey and isElement(entry.label) then
            guiSetText(entry.label, label(entry.labelKey))
        end
        if entry.kind == "number" and isElement(entry.element) then
            guiSetText(entry.element, tostring(currentValue(key)))
            guiSetText(entry.applyButton, label("settings.apply"))
        elseif entry.kind == "boolean" and isElement(entry.element) then
            guiCheckBoxSetSelected(entry.element, currentValue(key) == true)
        elseif entry.kind == "choice" and isElement(entry.element) then
            guiSetText(entry.element, valueLabel(currentValue(key)))
        elseif entry.kind == "delegated" and isElement(entry.element) then
            guiSetText(entry.element, label("settings.connectionSettings"))
        end
        if SettingsUI.rejection
            and SettingsUI.rejection.key == key
            and isElement(entry.errorLabel)
        then
            guiSetText(entry.errorLabel, label(SettingsUI.rejection.reason))
        end
    end
    return true
end

function closeSettings()
    if not isElement(SettingsUI.window) then
        return false
    end
    -- Where the user dragged the panel is a setting like any other, minus the
    -- part where anyone would want to undo it.
    if ANKIGTA.ClientSettings then
        local x, y = guiGetPosition(SettingsUI.window, false)
        ANKIGTA.ClientSettings.set("uiPlacement", {x = x, y = y})
    end
    destroyElement(SettingsUI.window)
    SettingsUI.window = false
    SettingsUI.controls = {}
    SettingsUI.mapControls = {}
    SettingsUI.rejection = false
    if cursorOwned then
        showCursor(cursorWasShowing)
        cursorOwned = false
        cursorWasShowing = false
    end
    return true
end

function openSettings()
    if isElement(SettingsUI.window) then
        closeSettings()
        return false
    end
    render()
    -- Drawn from what is known already, then corrected by the side that owns
    -- the rest: the panel opens whether or not the server answers.
    triggerServerEvent(SETTINGS_REQUEST_EVENT, resourceRoot)
    return true
end

addEvent(OPEN_SETTINGS_EVENT, false)
addEventHandler(OPEN_SETTINGS_EVENT, resourceRoot, function()
    openSettings()
end)

addEvent(SETTINGS_SNAPSHOT_EVENT, true)
addEventHandler(SETTINGS_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if type(snapshot) ~= "table" then
        return
    end
    SettingsUI.serverValues = snapshot.values or {}
    SettingsUI.maps = snapshot.maps or {}
    if isElement(SettingsUI.window) then
        -- The map list may have changed, so rows are rebuilt rather than
        -- relabelled.
        render()
    end
end)

addEvent(SETTINGS_REJECTED_EVENT, true)
addEventHandler(SETTINGS_REJECTED_EVENT, resourceRoot, function(key, reason)
    if type(key) == "string" and type(reason) == "string" then
        showRejection(key, reason)
    end
end)

addCommandHandler("ankigta-settings", function()
    openSettings()
end)

addEventHandler("onClientResourceStop", resourceRoot, closeSettings)

ANKIGTA.SettingsUI = SettingsUI

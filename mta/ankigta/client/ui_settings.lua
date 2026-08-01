ANKIGTA = ANKIGTA or {}

-- The UI Scale and layout panel.
--
-- Small on purpose. It holds the two controls a player needs when the
-- interface is the wrong size or in the wrong place, and the way back from
-- both: `Reset UI layout`.
--
-- It is reachable by a chat command as well as from F7, because "reachable"
-- has to survive the case where the window that would have opened it is the
-- one that is unusable.

local COMMAND = "ankigta-ui"

local function text(key, ...)
    -- Looked up when the control is written, so a language change reaches the
    -- next render without a restart.
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.format(key, ...)
    end
    return key
end

local window = nil
local cursorOwned = false
local cursorWasShowing = false

local function layout()
    return ANKIGTA.Layout
end

local function closePanel()
    if isElement(window) then
        destroyElement(window)
    end
    window = nil
    if layout() then
        layout().detach("uiSettings")
    end
    if cursorOwned then
        showCursor(cursorWasShowing)
        cursorOwned = false
        cursorWasShowing = false
    end
end

--- Say why a value was refused, in the player's language.
--
-- The refusal carries a localization key rather than a sentence, so this is
-- the side that turns it into one. Refused and not clamped: a mistyped 20
-- quietly becoming 2 leaves the player with a scale they never chose.
local function report(accepted, reason)
    if accepted then
        return
    end
    outputChatBox(
        text("ui.scaleRejected", text(tostring(reason or "settings.error.unknown"))),
        255,
        196,
        96
    )
end

local function openPanel()
    if not layout() then
        return false
    end
    closePanel()
    local panel = layout().open("uiSettings", text("ui.title"))
    if not panel then
        return false
    end
    window = panel.window
    local width = panel.width

    panel.label(18, 32, width - 36, 24, text("ui.currentScale", layout().scale()))
    panel.label(18, 58, width - 36, 22, text("ui.scaleRange"))

    local smaller = panel.button(18, 86, 210, 30, text("ui.smaller"))
    local larger = panel.button(242, 86, 210, 30, text("ui.larger"))

    panel.label(18, 126, 116, 24, text("ui.exactScale"))
    local exact = panel.edit(
        140, 122, 150, 30, string.format("%.2f", layout().scale())
    )
    guiSetProperty(exact, "NormalTextColour", "FF000000")
    local apply = panel.button(300, 122, 152, 30, text("ui.applyScale"))

    local editHud = panel.checkBox(
        18, 162, width - 36, 24, text("ui.editHud"), layout().hudEditMode()
    )
    panel.label(18, 188, width - 36, 22, text("ui.editHudExplanation"))

    local reset = panel.button(18, 216, width - 36, 32, text("ui.reset"))
    panel.label(18, 252, width - 36, 22, text("ui.resetExplanation"))
    local close = panel.button(18, 282, width - 36, 30, text("common.close"))

    addEventHandler("onClientGUIClick", smaller, function()
        report(layout().stepScale(-1))
    end, false)
    addEventHandler("onClientGUIClick", larger, function()
        report(layout().stepScale(1))
    end, false)
    addEventHandler("onClientGUIClick", apply, function()
        report(layout().setScale(guiGetText(exact)))
    end, false)
    addEventHandler("onClientGUIClick", editHud, function()
        layout().setHudEditMode(guiCheckBoxGetSelected(editHud))
    end, false)
    addEventHandler("onClientGUIClick", reset, function()
        layout().reset()
        outputChatBox(text("ui.resetDone"), 235, 235, 235)
    end, false)
    addEventHandler("onClientGUIClick", close, closePanel, false)

    if not cursorOwned then
        cursorWasShowing = isCursorShowing()
        cursorOwned = true
    end
    showCursor(true)
    return true
end

function isUiSettingsOpen()
    return isElement(window) == true
end

--- Open the panel, wherever the player asked from.
function openUiSettings()
    return openPanel()
end

addCommandHandler(COMMAND, openPanel)

-- The panel writes its labels and its control geometry once, when it is built,
-- so both a language change and a scale change have to rebuild it.
if ANKIGTA.Locale then
    ANKIGTA.Locale.onChange(function()
        if isElement(window) then
            openPanel()
        end
    end)
end

if ANKIGTA.Layout then
    ANKIGTA.Layout.onChange(function()
        if isElement(window) then
            openPanel()
        end
    end)
end

addEventHandler("onClientResourceStop", resourceRoot, closePanel)

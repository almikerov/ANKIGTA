ANKIGTA = ANKIGTA or {}

-- Where every ANKIGTA surface sits and how big it is.
--
-- Before this, each window read `guiGetScreenSize()` and laid itself out in
-- absolute pixels. Two things follow from taking that away: one UI Scale that
-- reaches every window at once, and a placement that survives a resolution
-- change instead of leaving a window somewhere the player cannot grab it.
--
-- Placement is stored normalized -- a fraction of the screen, not a pixel --
-- so the same file describes the same corner at 1280x720 and 3840x2160. It is
-- client-owned and therefore outside Change History (ADR 0028): where a window
-- sits is not a decision anyone undoes.
--
-- Two kinds of surface live here. A CEGUI window is dragged by its own title
-- bar, and MTA reports the move through `onClientGUIMove`. A dx-drawn surface
-- -- Review Mode and the HUD -- has no title bar of its own, so this module
-- carries the drag arithmetic for it and the surface only has to say where the
-- cursor went.

local SCALE_KEY = "uiScale"
local PLACEMENT_KEY = "uiPlacement"

-- What the `+` and `-` buttons move UI Scale by. Deliberately not the schema's
-- `step`, which would be a validation rule: the buttons move in 0.05, but a
-- value typed by hand only has to be a two-decimal number in range.
local SCALE_STEP = 0.05

-- The grab area of a dx-drawn surface, in design pixels. CEGUI windows carry
-- their own title bar and never consult this.
local TITLE_HEIGHT = 26

local Layout = {
    scaleStep = SCALE_STEP,
    titleHeight = TITLE_HEIGHT,
    --- Every surface this version knows, by key.
    surfaces = {},
    --- Normalized position per surface, for the ones the player has moved.
    placements = {},
    --- The live CEGUI window per surface, so a scale or resolution change can
    --- reach a window that is already open.
    attached = {},
    --- Modules to tell when the scale changed and their controls need
    --- rebuilding at the new size.
    listeners = {},
    hudEdit = false,
    dragState = false,
    -- Set while this module is the one moving windows, so the `onClientGUIMove`
    -- it causes is not mistaken for the player dragging one.
    repositioning = false,
}

local function schema()
    return ANKIGTA.Settings
end

local function schemaDefault(key, fallback)
    if schema() then
        local value = schema().default(key)
        if value ~= nil then
            return value
        end
    end
    return fallback
end

Layout.scaleValue = schemaDefault(SCALE_KEY, 1)

local function clamp(value, low, high)
    if high < low then
        return low
    end
    if value < low then
        return low
    end
    if value > high then
        return high
    end
    return value
end

local function roundTo(value, decimals)
    local factor = 10 ^ decimals
    return math.floor(value * factor + 0.5) / factor
end

--- Describe a surface, or refine one already described.
--
-- `width`/`height` are design pixels at scale 1. `relativeWidth`/
-- `relativeHeight` size a surface against the screen instead, for the ones
-- that are a share of it rather than a fixed panel. `follows` names a parent
-- surface a modal is centred on. `editModeOnly` marks a surface that only
-- moves while Edit HUD layout is on.
function Layout.define(key, spec)
    if type(key) ~= "string" or type(spec) ~= "table" then
        return false, "invalid_surface"
    end
    local surface = Layout.surfaces[key] or {}
    for name, value in pairs(spec) do
        surface[name] = value
    end
    Layout.surfaces[key] = surface
    return true
end

function Layout.screen()
    local width, height = guiGetScreenSize()
    return tonumber(width) or 0, tonumber(height) or 0
end

function Layout.scale()
    return Layout.scaleValue
end

--- How big this surface is now, and the scale that produced it.
--
-- The requested UI Scale is honoured only as far as the screen can show it. A
-- window taller than the screen has a title bar nobody can grab and buttons
-- nobody can reach, and no amount of dragging fixes that -- so the rendered
-- size is capped while the stored setting is left exactly as the player set
-- it. Clamping the setting instead would leave them with a value they never
-- chose the next time they played at a larger resolution.
function Layout.size(key)
    local surface = Layout.surfaces[key]
    if not surface then
        return false, "unknown_surface"
    end
    local screenWidth, screenHeight = Layout.screen()
    local width = (surface.width or screenWidth * (surface.relativeWidth or 1))
        * Layout.scaleValue
    local height = (surface.height or screenHeight * (surface.relativeHeight or 1))
        * Layout.scaleValue
    local fit = 1
    if width > 0 and height > 0 then
        fit = math.min(1, screenWidth / width, screenHeight / height)
    end
    return math.floor(width * fit), math.floor(height * fit),
        Layout.scaleValue * fit
end

--- The scale a surface's own controls should be drawn at.
function Layout.controlScale(key)
    local _width, _height, scale = Layout.size(key)
    return scale or Layout.scaleValue
end

--- The grab area of a dx-drawn surface, in screen pixels.
function Layout.handleHeight(key)
    local surface = Layout.surfaces[key] or {}
    local width, height, scale = Layout.size(key)
    if not width then
        return 0
    end
    if surface.wholeSurfaceDrags then
        return height
    end
    return math.floor((surface.titleHeight or TITLE_HEIGHT) * scale)
end

--- Where this surface goes, in screen pixels, already clamped on screen.
function Layout.rect(key)
    local surface = Layout.surfaces[key]
    if not surface then
        return false, "unknown_surface"
    end
    local width, height, scale = Layout.size(key)
    local screenWidth, screenHeight = Layout.screen()
    local x, y
    local placement = Layout.placements[key]
    local parentX, parentY, parentWidth, parentHeight
    if surface.follows then
        parentX, parentY, parentWidth, parentHeight = Layout.rect(surface.follows)
    end
    if parentX then
        -- A modal warning belongs to the window that raised it, so it is
        -- centred on that window rather than remembered on its own.
        x = parentX + (parentWidth - width) / 2
        y = parentY + (parentHeight - height) / 2
    elseif placement then
        x = placement.x * screenWidth
        y = placement.y * screenHeight
    else
        local margin = (surface.margin or 0) * scale
        x = (screenWidth - width - 2 * margin) * (surface.anchorX or 0.5) + margin
        y = (screenHeight - height - 2 * margin) * (surface.anchorY or 0.5) + margin
    end
    -- The whole surface is kept on screen. Since the size is already capped to
    -- the screen, that is always possible, and it is what keeps the title
    -- reachable after a resolution, aspect or scale change.
    x = clamp(x, 0, screenWidth - width)
    y = clamp(y, 0, screenHeight - height)
    return math.floor(x + 0.5), math.floor(y + 0.5), width, height, scale
end

--- Put a surface somewhere, without writing it down.
--
-- What a drag in progress uses: the surface follows the cursor immediately,
-- and the file is written once, when the drag ends.
function Layout.moveTo(key, x, y)
    local surface = Layout.surfaces[key]
    if not surface then
        return false, "unknown_surface"
    end
    if surface.follows then
        return false, "follows_parent"
    end
    local screenWidth, screenHeight = Layout.screen()
    if screenWidth <= 0 or screenHeight <= 0 then
        return false, "no_screen"
    end
    local width, height = Layout.size(key)
    x = clamp(tonumber(x) or 0, 0, screenWidth - width)
    y = clamp(tonumber(y) or 0, 0, screenHeight - height)
    Layout.placements[key] = {x = x / screenWidth, y = y / screenHeight}
    -- Everything, including the surface that just moved: the clamp may have
    -- corrected where a drag was heading, and the modal warnings that follow
    -- this window have to catch up either way.
    Layout.reposition()
    return true
end

--- Every placement, as the settings file stores it.
function Layout.snapshot()
    local snapshot = {}
    for key, spot in pairs(Layout.placements) do
        snapshot[key] = {x = spot.x, y = spot.y}
    end
    return snapshot
end

local function persist()
    if Layout.pendingWrite and isTimer(Layout.pendingWrite) then
        killTimer(Layout.pendingWrite)
    end
    Layout.pendingWrite = false
    if not (ANKIGTA.ClientSettings and ANKIGTA.ClientSettings.set) then
        -- The store is what owns the file. Without it the placement still
        -- governs this session; it simply does not outlive it.
        return false, "no_settings_store"
    end
    local written, reason = ANKIGTA.ClientSettings.set(
        PLACEMENT_KEY, Layout.snapshot()
    )
    if not written then
        -- The window stays where the player put it for this session; the file
        -- did not take it. Saying so beats a placement that silently is not
        -- there the next time they play.
        outputDebugString(
            "[ANKIGTA] ui_placement_not_stored: " .. tostring(reason),
            2
        )
    end
    return written, reason
end

Layout.persist = persist

--- Write the placement once the player stops moving the window.
--
-- CEGUI reports a drag as a stream of moves, one per frame. Writing the
-- settings file on each of them would rewrite it a hundred times to record one
-- decision, so the write waits for the movement to stop.
local WRITE_DELAY = 400

local function schedulePersist()
    if Layout.pendingWrite and isTimer(Layout.pendingWrite) then
        killTimer(Layout.pendingWrite)
    end
    Layout.pendingWrite = setTimer(persist, WRITE_DELAY, 1)
    return true
end

--- Put a surface somewhere and write it down.
function Layout.remember(key, x, y)
    local moved, reason = Layout.moveTo(key, x, y)
    if not moved then
        return false, reason
    end
    schedulePersist()
    return true
end

--- Put every attached window where the layout says it goes.
--
-- Re-entrant on purpose: `guiSetPosition` raises `onClientGUIMove`, which is
-- the same event a drag raises, and without the guard the two would be
-- indistinguishable.
function Layout.reposition()
    if Layout.repositioning then
        return false
    end
    Layout.repositioning = true
    for key, window in pairs(Layout.attached) do
        if isElement(window) then
            local x, y, width, height = Layout.rect(key)
            if x then
                guiSetPosition(window, x, y, false)
                guiSetSize(window, width, height, false)
            end
        end
    end
    Layout.repositioning = false
    return true
end

--- Re-read the screen and put everything back where it belongs.
--
-- MTA has no resolution-change event, so this is polled rather than delivered.
-- It is cheap and idempotent: nothing happens unless the screen actually
-- changed size.
function Layout.refresh()
    local screenWidth, screenHeight = Layout.screen()
    if screenWidth == Layout.screenWidth
        and screenHeight == Layout.screenHeight
    then
        return false
    end
    Layout.screenWidth = screenWidth
    Layout.screenHeight = screenHeight
    Layout.reposition()
    return true
end

-- Rebuilding on a scale change ----------------------------------------------

--- Be told when the scale changed.
--
-- A window writes its control geometry once, when it is built, so it cannot
-- notice a new scale on its own: without being told, "the scale applies at
-- once" would mean "at once, but close every window first".
function Layout.onChange(callback)
    if type(callback) == "function" then
        table.insert(Layout.listeners, callback)
    end
    return true
end

local function announce()
    for _, callback in ipairs(Layout.listeners) do
        -- One window failing to rebuild must not stop the rest from trying.
        local ok, failure = pcall(callback)
        if not ok then
            outputDebugString(
                "[ANKIGTA] layout_listener_failed error=" .. tostring(failure),
                2
            )
        end
    end
end

-- Scale ----------------------------------------------------------------------

function Layout.setScale(value)
    local number = tonumber(value)
    if number == nil then
        return false, "settings.error.not_a_number"
    end
    if ANKIGTA.ClientSettings and ANKIGTA.ClientSettings.set then
        -- Through the store, so the same schema validates it and the same file
        -- keeps it. `applySettings` puts the accepted value in force.
        return ANKIGTA.ClientSettings.set(SCALE_KEY, number)
    end
    local valid, reason = schema().validate(SCALE_KEY, number)
    if not valid then
        return false, reason
    end
    return Layout.applySettings(number)
end

--- Move UI Scale one button step, without leaving the allowed range.
function Layout.stepScale(direction)
    local rule = schema().definition(SCALE_KEY).rule
    local wanted = roundTo(
        Layout.scaleValue + SCALE_STEP * (tonumber(direction) or 0),
        2
    )
    wanted = clamp(wanted, rule.minimum, rule.maximum)
    if wanted == Layout.scaleValue then
        return false, "settings.error.out_of_range"
    end
    return Layout.setScale(wanted)
end

--- Take the stored client settings and put them in force.
--
-- Called by the client settings store, which owns the file. Nothing is written
-- back from here: that would be this module answering its own question.
function Layout.applySettings(scale, placement)
    local changedScale = false
    local number = tonumber(scale)
    if number ~= nil and number ~= Layout.scaleValue then
        Layout.scaleValue = number
        changedScale = true
    end
    if type(placement) == "table" then
        local accepted = {}
        for key, spot in pairs(placement) do
            -- A placement for a surface this version no longer has is dropped
            -- rather than carried around forever.
            if Layout.surfaces[key] and type(spot) == "table" then
                local x, y = tonumber(spot.x), tonumber(spot.y)
                if x and y then
                    accepted[key] = {x = clamp(x, 0, 1), y = clamp(y, 0, 1)}
                end
            end
        end
        Layout.placements = accepted
    end
    Layout.reposition()
    if changedScale then
        announce()
    end
    return true
end

--- Put every surface back where it shipped.
--
-- Both halves of the layout, because both can be the reason a player wants it
-- back: a window dragged somewhere awkward, and a scale that made everything
-- too small to read. Twenty clicks on `-` is not a way out.
function Layout.reset()
    Layout.placements = {}
    Layout.hudEdit = false
    Layout.dragState = false
    local scale = schemaDefault(SCALE_KEY, 1)
    if ANKIGTA.ClientSettings and ANKIGTA.ClientSettings.set then
        ANKIGTA.ClientSettings.set(PLACEMENT_KEY, {})
        return ANKIGTA.ClientSettings.set(SCALE_KEY, scale)
    end
    return Layout.applySettings(scale, {})
end

-- Edit HUD layout ------------------------------------------------------------

--- The HUD moves only while this is on.
--
-- The HUD has no title bar, and the whole of it is the grab area. Leaving that
-- live all the time would mean every click near the counters could drag them.
function Layout.setHudEditMode(enabled)
    Layout.hudEdit = enabled == true
    if not Layout.hudEdit then
        Layout.dragState = false
    end
    return true
end

function Layout.hudEditMode()
    return Layout.hudEdit == true
end

-- Dragging a dx-drawn surface ------------------------------------------------

--- Did this click land on the surface's grab area?
function Layout.beginDrag(key, cursorX, cursorY)
    local surface = Layout.surfaces[key]
    if not surface or surface.follows then
        return false
    end
    if surface.editModeOnly and not Layout.hudEdit then
        return false
    end
    local x, y, width = Layout.rect(key)
    if not x then
        return false
    end
    local handle = Layout.handleHeight(key)
    cursorX, cursorY = tonumber(cursorX) or -1, tonumber(cursorY) or -1
    if cursorX < x or cursorX > x + width
        or cursorY < y or cursorY > y + handle
    then
        return false
    end
    Layout.dragState = {
        key = key,
        offsetX = cursorX - x,
        offsetY = cursorY - y,
    }
    return true
end

function Layout.dragging(key)
    if not Layout.dragState then
        return false
    end
    if key ~= nil and Layout.dragState.key ~= key then
        return false
    end
    return true
end

function Layout.dragTo(cursorX, cursorY)
    local state = Layout.dragState
    if not state then
        return false
    end
    return Layout.moveTo(
        state.key,
        (tonumber(cursorX) or 0) - state.offsetX,
        (tonumber(cursorY) or 0) - state.offsetY
    )
end

--- Finish a drag and write the placement down.
function Layout.endDrag()
    local state = Layout.dragState
    Layout.dragState = false
    if not state then
        return false
    end
    persist()
    return true
end

-- CEGUI windows --------------------------------------------------------------

local function scaled(value, scale)
    return math.floor((tonumber(value) or 0) * scale + 0.5)
end

--- Keep a window in its surface's place, and follow the player when they move
--- it.
function Layout.attach(key, window)
    Layout.attached[key] = window
    addEventHandler("onClientGUIMove", window, function()
        if Layout.repositioning then
            return
        end
        local x, y = guiGetPosition(window, false)
        if type(x) ~= "number" then
            return
        end
        Layout.remember(key, x, y)
    end, false)
    return true
end

function Layout.detach(key)
    Layout.attached[key] = nil
    return true
end

--- A control factory that speaks design pixels.
--
-- The window code keeps the coordinates it was written with; this turns them
-- into whatever the current scale makes of them. A window that did its own
-- multiplication would be a window that could forget to.
function Layout.builder(key, window, scale)
    local surface = Layout.surfaces[key] or {}
    local function at(create)
        return function(x, y, width, height, ...)
            return create(
                scaled(x, scale),
                scaled(y, scale),
                scaled(width, scale),
                scaled(height, scale),
                ...
            )
        end
    end
    local builder = {
        key = key,
        window = window,
        scale = scale,
        -- Design pixels, so `builder.width - 32` still means what it meant.
        width = surface.width or 0,
        height = surface.height or 0,
    }
    builder.label = at(function(x, y, width, height, text, parent)
        return guiCreateLabel(x, y, width, height, text, false, parent or window)
    end)
    builder.button = at(function(x, y, width, height, text, parent)
        return guiCreateButton(x, y, width, height, text, false, parent or window)
    end)
    builder.edit = at(function(x, y, width, height, text, parent)
        return guiCreateEdit(x, y, width, height, text, false, parent or window)
    end)
    builder.checkBox = at(function(x, y, width, height, text, selected, parent)
        return guiCreateCheckBox(
            x, y, width, height, text, selected == true, false, parent or window
        )
    end)
    builder.gridList = at(function(x, y, width, height, parent)
        return guiCreateGridList(x, y, width, height, false, parent or window)
    end)
    return builder
end

--- Create this surface's window where the layout says it goes.
function Layout.open(key, title, spec)
    if spec then
        Layout.define(key, spec)
    end
    local x, y, width, height, scale = Layout.rect(key)
    if not x then
        return false, y
    end
    local window = guiCreateWindow(x, y, width, height, title or "", false)
    if not window then
        return false, "window_not_created"
    end
    -- Movable so the player can put it where they want, and explicitly not
    -- sizable: the size is UI Scale's to decide, and a hand-resized window
    -- would have its controls at the wrong size the moment it was reopened.
    if guiWindowSetMovable then
        guiWindowSetMovable(window, true)
    end
    if guiWindowSetSizable then
        guiWindowSetSizable(window, false)
    end
    Layout.attach(key, window)
    return Layout.builder(key, window, scale)
end

--- Create a modal that belongs to another surface and travels with it.
function Layout.openChild(key, parentKey, title, width, height)
    Layout.define(key, {
        width = width,
        height = height,
        follows = parentKey,
    })
    local x, y, actualWidth, actualHeight, scale = Layout.rect(key)
    if not x then
        return false, y
    end
    local window = guiCreateWindow(
        x, y, actualWidth, actualHeight, title or "", false
    )
    if not window then
        return false, "window_not_created"
    end
    if guiWindowSetMovable then
        -- It follows its parent, so it has no placement of its own to keep.
        guiWindowSetMovable(window, false)
    end
    if guiWindowSetSizable then
        guiWindowSetSizable(window, false)
    end
    Layout.attached[key] = window
    return Layout.builder(key, window, scale)
end

-- The surfaces ---------------------------------------------------------------

Layout.define("f7", {width = 900, height = 360})
Layout.define("cardPicker", {width = 620, height = 320})
Layout.define("study", {width = 420, height = 240})
Layout.define("connection", {width = 430, height = 150})
Layout.define("connectionSettings", {width = 470, height = 330})
-- The settings panel sizes itself: it has a row per setting and a row per
-- loaded map, so it redefines this surface as it renders.
Layout.define("settings", {width = 760, height = 560})
-- Review Mode is a share of the screen rather than a panel: the card is the
-- content, and a fixed pixel size would waste a 4K screen and overflow a 720p
-- one.
Layout.define("review", {relativeWidth = 0.7, relativeHeight = 0.7})
-- The HUD sits top-right by default, out of the way of the radar and the
-- weapon icon, and the whole of it drags -- but only in Edit HUD layout.
Layout.define("hud", {
    width = 520,
    height = 34,
    anchorX = 1,
    anchorY = 0,
    margin = 12,
    wholeSurfaceDrags = true,
    editModeOnly = true,
})

addEventHandler("onClientResourceStart", resourceRoot, function()
    Layout.screenWidth, Layout.screenHeight = Layout.screen()
    -- Polled, because MTA reports no resolution change. Half a second is far
    -- below noticing and far above costing anything.
    setTimer(Layout.refresh, 500, 0)
end)

addEventHandler("onClientResourceStop", resourceRoot, function()
    -- A placement moved seconds before the resource stopped is still a
    -- placement the player chose.
    if Layout.pendingWrite then
        persist()
    end
end)

ANKIGTA.Layout = Layout

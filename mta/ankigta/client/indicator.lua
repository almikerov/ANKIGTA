ANKIGTA = ANKIGTA or {}

-- Next Card Indicator: how the card Anki chose next is shown in the world.
--
-- The queue is global, but the indicator is not: it can only point at an
-- instance that is actually here, in this interior and dimension. A marker
-- floating over an entity the player cannot reach would be worse than none.
--
-- The temporary sphere is a display, not an Activation Zone. It never creates
-- or resizes one; where it coincides with a real zone, one emphasized sphere
-- is drawn rather than two overlapping ones.

local function text(key)
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.text(key)
    end
    return key
end

-- The counters, in the order the HUD reads them. `statistics.*` finally has a
-- call site: the keys existed while the HUD spelled the labels out in English.
local COUNTER_KEYS = {
    {"statistics.total", "total"},
    {"statistics.new", "new"},
    {"statistics.learning", "learning"},
    {"statistics.due", "due"},
    {"statistics.early", "early"},
}

local MODE_SPHERE_AND_MINIMAP = "sphere_and_minimap"
local MODE_MINIMAP_ONLY = "minimap_only"
local MODE_NONE = "none"

-- Deliberately no sphere-only mode: a sphere with no minimap marker tells the
-- player where the card is only once they are already looking at it.
local MODES = {
    [MODE_SPHERE_AND_MINIMAP] = true,
    [MODE_MINIMAP_ONLY] = true,
    [MODE_NONE] = true,
}

local Indicator = {
    mode = (ANKIGTA.Settings and ANKIGTA.Settings.default("indicatorMode"))
        or MODE_NONE,
}

function Indicator.availableModes()
    return {MODE_SPHERE_AND_MINIMAP, MODE_MINIMAP_ONLY, MODE_NONE}
end

function Indicator.setMode(mode)
    if not MODES[mode] then
        return false, "invalid_indicator_mode"
    end
    Indicator.mode = mode
    return true
end

local function cardKey(cardIdentity)
    if type(cardIdentity) ~= "table" then
        return nil
    end
    local cardId = tonumber(cardIdentity.cardId)
    if cardId == nil then
        return nil
    end
    -- Anki Card Identity is the pair, never the number alone: the same cardId
    -- in another collection is another card (CONTEXT.md).
    return tostring(cardIdentity.collectionUuid) .. "\0" .. tostring(cardId)
end

-- Which candidates carry which card, for the candidate list currently in hand.
--
-- A marker is wanted for one card, and the world holds thousands of entities
-- carrying every other one. Walking all of them per rendered frame to find the
-- handful that carry this card is most of a two-millisecond budget spent
-- rejecting entities that were never eligible for the marker.
--
-- Keyed on the candidate list itself. The list is replaced wholesale whenever
-- the server sends one, so a new list is a new table, and an entity's Anki
-- Card Identity does not change under a list that is still the same one --
-- that would be a Spatial Link changing, which arrives as a new list.
local byCard = {byList = false, buckets = nil}

local function candidatesCarrying(candidates, key)
    if byCard.byList ~= candidates then
        local buckets = {}
        for _, candidate in ipairs(candidates or {}) do
            local candidateKey = cardKey(candidate.cardIdentity)
            if candidateKey ~= nil then
                local bucket = buckets[candidateKey]
                if bucket == nil then
                    bucket = {}
                    buckets[candidateKey] = bucket
                end
                bucket[#bucket + 1] = candidate
            end
        end
        byCard.byList = candidates
        byCard.buckets = buckets
    end
    return byCard.buckets[key] or {}
end

--- Which entity, if any, should carry the marker for the next card.
--
-- A card may be linked to several entities. Only the nearest reachable one is
-- marked: marking all of them would turn a hint into clutter.
function Indicator.selectTarget(player, candidates, cardIdentity)
    if type(player) ~= "table" then
        return false
    end
    local key = cardKey(cardIdentity)
    if key == nil then
        return false
    end
    -- Same order as the Activation Zone uses (`shared/nearest.lua`): two
    -- entities carrying the same card at the same distance resolve on their
    -- Map Entity identity, not on where the snapshot happened to put them.
    return (ANKIGTA.Nearest.select(
        player,
        candidatesCarrying(candidates, key),
        function(candidate)
            return candidate.eligible == true
                and candidate.present ~= false
                and candidate.interior == player.interior
                and candidate.dimension == player.dimension
        end
    ))
end

--- What to draw for the next card, given the mode and the world.
function Indicator.plan(player, candidates, cardIdentity)
    if Indicator.mode == MODE_NONE then
        return {blip = false, sphere = false, emphasized = false}
    end
    local target = Indicator.selectTarget(player, candidates, cardIdentity)
    if not target then
        return {blip = false, sphere = false, emphasized = false}
    end

    local plan = {
        blip = true,
        sphere = Indicator.mode == MODE_SPHERE_AND_MINIMAP,
        -- An Activation Zone already occupies this spot, so the indicator
        -- emphasizes that sphere instead of drawing a second one on top.
        emphasized = target.hasActivationZone == true,
        mapId = target.mapId,
        entityId = target.entityId,
        x = target.x,
        y = target.y,
        z = target.z,
    }
    if plan.sphere and plan.emphasized then
        plan.sphereRadius = tonumber(target.radius)
    end
    return plan
end

-- Rendering ------------------------------------------------------------------

local STATISTICS_EVENT = "ankigta:statistics"
local NEXT_CARD_EVENT = "ankigta:nextCard"

local hud = {
    counts = false,
    cardIdentity = false,
    candidates = {},
    blip = false,
    pulse = 0,
}

local function clearBlip()
    if isElement(hud.blip) then
        destroyElement(hud.blip)
    end
    hud.blip = false
end

function Indicator.hudState()
    return {
        counts = hud.counts,
        hasBlip = isElement(hud.blip) == true,
    }
end

local function playerObservation()
    local x, y, z = getElementPosition(localPlayer)
    return {
        x = x or 0,
        y = y or 0,
        z = z or 0,
        interior = getElementInterior(localPlayer) or 0,
        dimension = getElementDimension(localPlayer) or 0,
    }
end

--- Reconcile the world marker with the current plan.
function Indicator.refresh()
    local current = Indicator.plan(
        playerObservation(),
        hud.candidates,
        hud.cardIdentity
    )
    if not current.blip then
        clearBlip()
        return current
    end
    if not isElement(hud.blip) then
        -- Blip 41 is Anki-agnostic; the marker means "next card", not a
        -- gameplay objective.
        hud.blip = createBlip(current.x, current.y, current.z, 41)
    else
        setElementPosition(hud.blip, current.x, current.y, current.z)
    end
    if isElement(hud.blip) then
        setElementInterior(hud.blip, getElementInterior(localPlayer) or 0)
        setElementDimension(hud.blip, getElementDimension(localPlayer) or 0)
    end
    return current
end

--- What the counters read, as one line.
function Indicator.hudText()
    local counts = hud.counts
    if type(counts) ~= "table" then
        return false
    end
    local parts = {}
    for index, counter in ipairs(COUNTER_KEYS) do
        parts[index] = string.format(
            "%s %d",
            text(counter[1]),
            tonumber(counts[counter[2]]) or 0
        )
    end
    -- The product name is not a word to translate.
    return "ANKIGTA  " .. table.concat(parts, "   ")
end

function Indicator.render()
    local line = Indicator.hudText()
    if line then
        local x, y, width, height, scale = ANKIGTA.Layout.rect("hud")
        if ANKIGTA.Layout.hudEditMode() then
            -- The HUD has no title bar, so Edit HUD layout says so by showing
            -- the box the player is about to grab.
            dxDrawRectangle(x, y, width, height, tocolor(60, 90, 130, 140))
            dxDrawText(
                text("ui.hudHandle"),
                x,
                y - math.floor(20 * scale),
                x + width,
                y,
                tocolor(160, 200, 255, 235),
                scale,
                "default-bold",
                "right"
            )
        end
        dxDrawText(
            line,
            x,
            y,
            x + width,
            y + height,
            tocolor(235, 235, 235, 220),
            scale,
            "default-bold",
            "right"
        )
    end

    local current = Indicator.refresh()
    if not current.sphere then
        return
    end
    -- A pulse rather than a second sphere: where an Activation Zone already
    -- occupies this spot, the indicator emphasizes that one.
    hud.pulse = (hud.pulse + 1) % 120
    local emphasis = current.emphasized and (0.5 + 0.5 * math.abs(60 - hud.pulse) / 60) or 1
    dxDrawMaterialLine3D(
        current.x,
        current.y,
        current.z - 1,
        current.x,
        current.y,
        current.z + 2,
        nil,
        (current.sphereRadius or 3) * emphasis,
        tocolor(120, 200, 255, 160)
    )
end

addEvent(STATISTICS_EVENT, true)
addEventHandler(STATISTICS_EVENT, resourceRoot, function(counts)
    hud.counts = type(counts) == "table" and counts or false
end)

addEvent(NEXT_CARD_EVENT, true)
addEventHandler(NEXT_CARD_EVENT, resourceRoot, function(cardIdentity, candidates)
    hud.cardIdentity = type(cardIdentity) == "table" and cardIdentity or false
    hud.candidates = type(candidates) == "table" and candidates or {}
    Indicator.refresh()
end)

addEventHandler("onClientRender", root, function()
    if Indicator.mode ~= MODE_NONE or hud.counts then
        Indicator.render()
    end
end)

-- Moving the HUD -------------------------------------------------------------
--
-- Only in Edit HUD layout. The HUD is drawn over the game rather than in a
-- window, so without a mode of its own every click near the counters would be
-- a click that could drag them.

local function reviewModeHoldsTheMouse()
    -- Review Mode is modal (story 48). A click meant for a card is not a click
    -- that also drags the HUD out from behind it.
    return type(isReviewModeActive) == "function" and isReviewModeActive()
end

addEventHandler("onClientClick", root, function(button, state, cursorX, cursorY)
    if button ~= "left" or not ANKIGTA.Layout.hudEditMode() then
        return
    end
    if reviewModeHoldsTheMouse() then
        return
    end
    if state == "down" then
        if ANKIGTA.Layout.beginDrag("hud", cursorX, cursorY) then
            cancelEvent()
        end
        return
    end
    if state == "up" and ANKIGTA.Layout.dragging("hud") then
        ANKIGTA.Layout.endDrag()
        cancelEvent()
    end
end)

addEventHandler("onClientCursorMove", root, function(
    _relativeX,
    _relativeY,
    absoluteX,
    absoluteY
)
    if ANKIGTA.Layout.dragging("hud") then
        ANKIGTA.Layout.dragTo(absoluteX, absoluteY)
    end
end)

addEventHandler("onClientResourceStop", resourceRoot, function()
    clearBlip()
end)

ANKIGTA.Indicator = Indicator

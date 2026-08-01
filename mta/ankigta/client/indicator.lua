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
    mode = MODE_NONE,
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

local function distanceSquared(a, b)
    local dx = a.x - b.x
    local dy = a.y - b.y
    local dz = a.z - b.z
    return dx * dx + dy * dy + dz * dz
end

local function sameCard(candidate, cardIdentity)
    return type(candidate.cardIdentity) == "table"
        and type(cardIdentity) == "table"
        and candidate.cardIdentity.collectionUuid == cardIdentity.collectionUuid
        and tonumber(candidate.cardIdentity.cardId)
            == tonumber(cardIdentity.cardId)
end

--- Which entity, if any, should carry the marker for the next card.
--
-- A card may be linked to several entities. Only the nearest reachable one is
-- marked: marking all of them would turn a hint into clutter.
function Indicator.selectTarget(player, candidates, cardIdentity)
    if type(player) ~= "table" or type(cardIdentity) ~= "table" then
        return false
    end
    local best, bestDistance = false, nil
    for _, candidate in ipairs(candidates or {}) do
        if sameCard(candidate, cardIdentity)
            and candidate.eligible == true
            and candidate.present ~= false
            and candidate.interior == player.interior
            and candidate.dimension == player.dimension
        then
            local distance = distanceSquared(player, candidate)
            if bestDistance == nil or distance < bestDistance then
                best, bestDistance = candidate, distance
            end
        end
    end
    return best
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

function Indicator.render()
    local counts = hud.counts
    if type(counts) == "table" then
        local screenWidth = guiGetScreenSize()
        dxDrawText(
            string.format(
                "ANKIGTA  Total %d   New %d   Learning %d   Due %d   Early %d",
                counts.total or 0,
                counts.new or 0,
                counts.learning or 0,
                counts.due or 0,
                counts.early or 0
            ),
            screenWidth - 520,
            12,
            screenWidth - 12,
            34,
            tocolor(235, 235, 235, 220),
            1,
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

addEventHandler("onClientResourceStop", resourceRoot, function()
    clearBlip()
end)

ANKIGTA.Indicator = Indicator

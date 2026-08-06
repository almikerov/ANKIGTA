ANKIGTA = ANKIGTA or {}

-- What ANKIGTA puts on the map, and what it stands over.
--
-- Two answers, and one module because they are two answers about the same
-- spots. The **Next Card Indicator** says how the card Anki chose next is
-- marked; **Show every Map Entity on the map** says whether the rest of the
-- world is marked at all. Where they meet -- an entity that is the next card
-- and is also one of the known ones -- the next card is the more specific
-- answer, so it is the mark that is drawn and the other is not put on top of
-- it.
--
-- The queue is global, but the indicator is not: it can only point at an
-- instance that is actually here, in this interior and dimension. A marker
-- floating over an entity the player cannot reach would be worse than none.
--
-- The temporary **beam** is a display, not an Activation Zone. It never creates
-- or resizes one; where it coincides with a real zone, one emphasized beam is
-- drawn rather than two overlapping marks. It was called a sphere and never was
-- one -- `WorldMarks.beam` draws `dxDrawMaterialLine3D`, a standing bar as wide
-- as the zone's radius. The sphere is the *zone*, which `Draw radius` draws
-- through `WorldMarks.sphere`. The shape is unchanged by the renaming: what it
-- looks like is the owner's to judge, and nobody has asked for another.

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

local MODE_BEAM_AND_MINIMAP = "beam_and_minimap"
local MODE_MINIMAP_ONLY = "minimap_only"
local MODE_NONE = "none"

-- Deliberately no beam-only mode: a mark in the world with no minimap blip
-- tells the player where the card is only once they are already looking at it.
local MODES = {
    [MODE_BEAM_AND_MINIMAP] = true,
    [MODE_MINIMAP_ONLY] = true,
    [MODE_NONE] = true,
}

local function settingsDefault(key)
    return ANKIGTA.Settings and ANKIGTA.Settings.default(key) or nil
end

local Indicator = {
    mode = settingsDefault("indicatorMode") or MODE_NONE,
    --- Whether every known Map Entity is on the map, not only the next card.
    showEntitiesOnMap = settingsDefault("showEntitiesOnMap") == true,
}

function Indicator.availableModes()
    return {MODE_BEAM_AND_MINIMAP, MODE_MINIMAP_ONLY, MODE_NONE}
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
        return {blip = false, beam = false, emphasized = false}
    end
    local target = Indicator.selectTarget(player, candidates, cardIdentity)
    if not target then
        return {blip = false, beam = false, emphasized = false}
    end

    local plan = {
        blip = true,
        beam = Indicator.mode == MODE_BEAM_AND_MINIMAP,
        -- A corona already marks this spot, so the indicator emphasizes that
        -- mark instead of putting a second one on top of it.
        emphasized = target.hasCorona == true,
        mapId = target.mapId,
        entityId = target.entityId,
        x = target.x,
        y = target.y,
        z = target.z,
    }
    if plan.beam then
        -- As wide as the Activation Zone actually in force, never as the
        -- shipped default. This read `tonumber(target.radius)` and fell back to
        -- 3 at the draw, so every entity following the global was marked at
        -- three metres however wide its zone really was -- and the mark is the
        -- only thing telling the player where the card will open.
        plan.beamWidth = ANKIGTA.WorldMarks
            and ANKIGTA.WorldMarks.radiusInForce(target.radius)
            or tonumber(target.radius)
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
    -- Where the live candidates come from, when something owns the runtime
    -- index. `client/spatial.lua` does, and fills in the position the Runtime
    -- Instance is at now; the event carries identities only.
    candidateSource = false,
    blip = false,
    -- Which Map Entity the blip above is standing on, so the map knows not to
    -- put a second mark there. `false` while nothing is marked.
    blipEntity = false,
    pulse = 0,
}

--- Read the candidates from `source` rather than from the last event.
function Indicator.setCandidateSource(source)
    hud.candidateSource = type(source) == "function" and source or false
    return true
end

--- The three things a Map Entity can be on the map, and what each looks like.
--
-- One table, because "which of them are ready" is one question with three
-- answers and a colour per answer is what makes it readable at a glance. Three
-- distinct colours: green for one that will really open a card, grey for one
-- ANKIGTA knows and cannot study through, and the indicator's own blue for the
-- one the scheduler chose.
--
-- The next card also carries a sprite, and that is what a player sees: GTA
-- draws the sprite in place of the colour where a blip has one --
-- `CMarkerSA::SetColor` says so in its own words, "Sets the color of the marker
-- when MARKER_SPRITE_NONE is used" (`Client/game_sa/CMarkerSA.cpp`, read
-- 2026-08-06, SHA-256
-- 31cdb7ca9b8cfc4f0fc347903d9b7295c600016740f1387ca2a53f8955310852). Sprite 41
-- is what the Next Card Indicator has always used and it is the strongest mark
-- on the map, which is right for the one entity the player is being sent to.
-- The colour is set with it so that the answer to "what does this state look
-- like" is in one place rather than two.
local STATE_CONNECTED = "connected"
local STATE_DISCONNECTED = "disconnected"
local STATE_NEXT_CARD = "next_card"

local STATE_APPEARANCE = {
    [STATE_CONNECTED] = {icon = 0, red = 60, green = 220, blue = 120, alpha = 220},
    [STATE_DISCONNECTED] = {icon = 0, red = 160, green = 160, blue = 160, alpha = 200},
    -- Blip 41 is Anki-agnostic; the mark means "next card", not a gameplay
    -- objective.
    [STATE_NEXT_CARD] = {icon = 41, red = 120, green = 200, blue = 255, alpha = 255},
}

--- What one of the three states looks like on the map.
function Indicator.stateAppearance(state)
    return STATE_APPEARANCE[state]
end

local function clearBlip()
    if isElement(hud.blip) then
        destroyElement(hud.blip)
    end
    hud.blip = false
    hud.blipEntity = false
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
        hud.candidateSource and hud.candidateSource() or hud.candidates,
        hud.cardIdentity
    )
    if not current.blip then
        clearBlip()
        return current
    end
    if not isElement(hud.blip) then
        local look = STATE_APPEARANCE[STATE_NEXT_CARD]
        hud.blip = createBlip(
            current.x,
            current.y,
            current.z,
            look.icon,
            2,
            look.red,
            look.green,
            look.blue,
            look.alpha
        )
    else
        setElementPosition(hud.blip, current.x, current.y, current.z)
    end
    if isElement(hud.blip) then
        setElementInterior(hud.blip, getElementInterior(localPlayer) or 0)
        setElementDimension(hud.blip, getElementDimension(localPlayer) or 0)
    end
    -- Written down whether or not the blip could be made: what the map has to
    -- know is which entity the indicator has claimed, and it has claimed this
    -- one either way.
    hud.blipEntity = {mapId = current.mapId, entityId = current.entityId}
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
    -- The product name is not a word the table holds.
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
    if not current.beam then
        return
    end
    -- A pulse rather than a second mark: where a corona already marks this
    -- spot, the indicator emphasizes that one.
    hud.pulse = (hud.pulse + 1) % 120
    local emphasis = current.emphasized and (0.5 + 0.5 * math.abs(60 - hud.pulse) / 60) or 1
    -- Through the marks module, which is where the one rule about how far
    -- ANKIGTA draws lives. A mark that reached for `dxDrawMaterialLine3D`
    -- itself would be a second answer to a question with one.
    --
    -- Guarded like every other reach into it: a running client can be handed
    -- one changed `cache="false"` script a restart before a newly added one,
    -- and an unguarded call in a render handler is an error per frame.
    if not ANKIGTA.WorldMarks then
        return
    end
    ANKIGTA.WorldMarks.beam(
        current.x,
        current.y,
        current.z,
        (current.beamWidth or 3) * emphasis,
        tocolor(120, 200, 255, 160)
    )
end

-- Every Map Entity on the map ------------------------------------------------
--
-- The map is the one surface that can show a Map Entity the player cannot see,
-- so this reads the *authored* position rather than a Runtime Instance's: a
-- blip is wanted for an entity three districts away, and that entity has no
-- element here to read a position off. What follows an object as it moves is
-- the corona, which is attached to it.

--- How often the map is brought into line with the world.
--
-- The same quarter-second the world marks poll at. What changes between two
-- frames is where the player is standing, and the set of blips only has to
-- follow that closely enough to be read.
local MAP_POLL_INTERVAL_MS = 250

--- How many entity blips ANKIGTA will put on the map at once.
--
-- Said rather than left to be discovered in a world that has grown. GTA San
-- Andreas has 175 radar trace slots in total -- `MAX_MARKERS` in
-- `game_sa/CRadarSA.h` -- and `CRadarSA::GetFreeMarker` answers NULL once they
-- are all taken. Nothing reports that: `CClientRadarMarker::CreateMarker`
-- leaves the blip with no trace behind it, so the element exists, `isElement`
-- says yes, and there is simply nothing on the radar. Worse, the manager
-- destroys and re-creates every trace in ordering order whenever the list
-- changes (`CClientRadarMarkerManager::OrderMarkers`), so which blips lose is
-- decided by ordering rather than by anything the player did.
--
-- Read 2026-08-06:
--   Client/game_sa/CRadarSA.h
--     a6383fd583502fa5480812b0b468491e028402bc8fc54faeaff122700c43f933
--   Client/game_sa/CRadarSA.cpp
--     632fd7cebca76a43dd077d78cc62d15306f0855482c5d31a44b924805e3c8772
--   Client/mods/deathmatch/logic/CClientRadarMarker.cpp
--     ac4ac1e0a9a73c883961c4338cdfd1d0c407836baf75cecca57520d06a38f592
--   Client/mods/deathmatch/logic/CClientRadarMarkerManager.cpp
--     a853d18ba34789dbaf80c2acfa1ba7df6cb05942624b1a9128a5e86b48e60ba6
--
-- 64 leaves the large majority of those slots to the game and to every other
-- resource, and is already more marks than a map can be read at a glance. Past
-- it, the nearest 64 to the player are the ones drawn -- nearest, because the
-- map is read to decide where to go next.
local MAP_BLIP_LIMIT = 64

function Indicator.mapBlipLimit()
    return MAP_BLIP_LIMIT
end

--- Is every known Map Entity on the map?
--
-- Independent of `indicatorMode` in both directions: turning this on does not
-- decide how the next card is marked, and turning the indicator off does not
-- take the rest of the world off the map.
function Indicator.setShowEntitiesOnMap(value)
    Indicator.showEntitiesOnMap = value == true
    Indicator.refreshMap()
    return true
end

--- Which entity gets a blip, and what it says about that entity.
--
-- Pure: what ANKIGTA knows arrives in `entities`, what the player has chosen
-- and where they are standing arrive in `view`. Nothing here reads an element,
-- a setting or a clock, which is what makes the rules checkable without a game
-- running -- and the rules are the interesting part.
--
-- `view` is `{showEntitiesOnMap, nextCard, player}`, where `nextCard` is the
-- `{mapId, entityId}` the Next Card Indicator has already marked or `false`
-- when it is marking nothing. Each entry of `entities` is `{mapId, entityId, x,
-- y, z, dimension, connected}`.
function Indicator.mapPlan(view, entities)
    view = type(view) == "table" and view or {}
    if view.showEntitiesOnMap ~= true then
        return {}
    end
    local marked = type(view.nextCard) == "table" and view.nextCard or false
    local player = type(view.player) == "table" and view.player or {}
    local fromX = tonumber(player.x) or 0
    local fromY = tonumber(player.y) or 0
    local fromZ = tonumber(player.z) or 0

    local wanted = {}
    for _, entity in ipairs(entities or {}) do
        -- Where an entity is both the next card and connected, next card wins:
        -- it is the more specific answer and it is the one the player is
        -- looking for. One state per entity, decided here -- so what the map
        -- says about a spot is a question about a plan, answerable from outside
        -- the frame it would be drawn in.
        local state = STATE_DISCONNECTED
        if marked ~= false
            and entity.mapId == marked.mapId
            and entity.entityId == marked.entityId
        then
            state = STATE_NEXT_CARD
        elseif entity.connected == true then
            state = STATE_CONNECTED
        end
        local deltaX = (tonumber(entity.x) or 0) - fromX
        local deltaY = (tonumber(entity.y) or 0) - fromY
        local deltaZ = (tonumber(entity.z) or 0) - fromZ
        wanted[#wanted + 1] = {
            mapId = entity.mapId,
            entityId = entity.entityId,
            x = tonumber(entity.x) or 0,
            y = tonumber(entity.y) or 0,
            z = tonumber(entity.z) or 0,
            dimension = tonumber(entity.dimension) or 0,
            state = state,
            -- Squared, and named so. Only the ordering reads it, and a square
            -- root per entity per poll buys nothing an ordering can use.
            distanceSquared = deltaX * deltaX + deltaY * deltaY + deltaZ * deltaZ,
        }
    end

    table.sort(wanted, function(left, right)
        -- The next card first, whatever the distance: it is the one mark the
        -- player is being sent to, and dropping it for being far away would
        -- drop the only reason they are looking.
        local leftIsNext = left.state == STATE_NEXT_CARD
        local rightIsNext = right.state == STATE_NEXT_CARD
        if leftIsNext ~= rightIsNext then
            return leftIsNext
        end
        if left.distanceSquared ~= right.distanceSquared then
            return left.distanceSquared < right.distanceSquared
        end
        -- Total, so the set does not churn between two polls that found the
        -- same world.
        if left.mapId ~= right.mapId then
            return left.mapId < right.mapId
        end
        return left.entityId < right.entityId
    end)

    local plan = {}
    for index, entry in ipairs(wanted) do
        if index > MAP_BLIP_LIMIT then
            break
        end
        plan[#plan + 1] = entry
    end
    return plan
end

--- The blips this module put on the map, by Map Entity.
local mapBlips = {}

--- What one Map Entity is filed under here.
--
-- The panel's own key, with no second spelling behind it: everything that
-- reaches this walks through `refreshMap`, which has already found the panel
-- before there is anything to file. A fallback here would be a third answer to
-- a question with one, and the day the pair stopped being joined by `/` it
-- would be a blip that quietly never matched itself again.
local function mapKey(mapId, entityId)
    return ANKIGTA.Panel.entityKey(mapId, entityId)
end

local function destroyMapBlip(key)
    local existing = mapBlips[key]
    if not existing then
        return
    end
    mapBlips[key] = nil
    if isElement(existing.blip) then
        destroyElement(existing.blip)
    end
end

--- Take every entity blip off the map.
function Indicator.clearMap()
    for key in pairs(mapBlips) do
        destroyMapBlip(key)
    end
end

--- Bring the map into line with the plan.
--
-- Reconciled rather than rebuilt, for the reason the coronas are -- and here
-- with a sharper edge. `CClientRadarMarkerManager::OrderMarkers` destroys and
-- re-creates *every* radar trace on the client whenever the list changes, so a
-- blip replaced four times a second re-cuts the whole map, including the game's
-- own icons and every other resource's.
--
-- Which is also why each write below is guarded by what changed rather than
-- made unconditionally: `setElementDimension` on a blip goes through
-- `CClientRadarMarker::RelateDimension`, which asks for that re-order whether or
-- not the dimension is different. Setting a blip's own dimension back onto it
-- is not a no-op. (Both files as recorded at `MAP_BLIP_LIMIT` above.)
local function reconcileMapBlips(plan)
    local keep = {}
    for _, entry in ipairs(plan) do
        -- The next card is marked by the Next Card Indicator's own blip, which
        -- already stands here -- so this puts nothing on top of it. One mark
        -- per entity, and which mark it is was decided in the plan.
        if entry.state ~= STATE_NEXT_CARD then
            local key = mapKey(entry.mapId, entry.entityId)
            local look = STATE_APPEARANCE[entry.state]
            local existing = mapBlips[key]
            if existing and isElement(existing.blip) then
                keep[key] = true
                if existing.state ~= entry.state then
                    setBlipColor(
                        existing.blip,
                        look.red,
                        look.green,
                        look.blue,
                        look.alpha
                    )
                    setBlipIcon(existing.blip, look.icon)
                    existing.state = entry.state
                end
                -- An authored position does not usually move, but a map
                -- reloaded with an object somewhere else is exactly the case
                -- the panel re-reads the world for.
                if existing.x ~= entry.x
                    or existing.y ~= entry.y
                    or existing.z ~= entry.z
                then
                    setElementPosition(existing.blip, entry.x, entry.y, entry.z)
                    existing.x, existing.y, existing.z = entry.x, entry.y, entry.z
                end
                if existing.dimension ~= entry.dimension then
                    setElementDimension(existing.blip, entry.dimension)
                    existing.dimension = entry.dimension
                end
            else
                destroyMapBlip(key)
                local blip = createBlip(
                    entry.x,
                    entry.y,
                    entry.z,
                    look.icon,
                    2,
                    look.red,
                    look.green,
                    look.blue,
                    look.alpha
                )
                if isElement(blip) then
                    keep[key] = true
                    -- MTA makes a blip in dimension 0, so saying so again would
                    -- be asking for a re-order to change nothing.
                    if entry.dimension ~= 0 then
                        setElementDimension(blip, entry.dimension)
                    end
                    mapBlips[key] = {
                        blip = blip,
                        state = entry.state,
                        x = entry.x,
                        y = entry.y,
                        z = entry.z,
                        dimension = entry.dimension,
                    }
                end
            end
        end
    end
    for key in pairs(mapBlips) do
        if not keep[key] then
            destroyMapBlip(key)
        end
    end
end

--- Look at what ANKIGTA knows, decide, and put the blips where it says.
function Indicator.refreshMap()
    -- The next card first, and unconditionally: the map is told about a mark
    -- that already exists rather than working one out for itself and
    -- disagreeing with it, and the next card is marked whether or not anything
    -- else on the map is.
    local current = Indicator.refresh()
    -- Which Map Entity exist is the panel's answer. A running client can be
    -- handed this changed `cache="false"` script one restart before a newly
    -- added one, so the reach is guarded like every other -- and the blip above
    -- has already been seen to either way.
    if not ANKIGTA.Panel or not ANKIGTA.Panel.mapEntities then
        return false
    end
    local plan = Indicator.mapPlan({
        showEntitiesOnMap = Indicator.showEntitiesOnMap,
        nextCard = current.blip and hud.blipEntity or false,
        player = playerObservation(),
    }, ANKIGTA.Panel.mapEntities())
    reconcileMapBlips(plan)
    return plan
end

addEvent(STATISTICS_EVENT, true)
addEventHandler(STATISTICS_EVENT, resourceRoot, function(counts)
    hud.counts = type(counts) == "table" and counts or false
end)

addEvent(NEXT_CARD_EVENT, true)
addEventHandler(NEXT_CARD_EVENT, resourceRoot, function(cardIdentity, candidates)
    hud.cardIdentity = type(cardIdentity) == "table" and cardIdentity or false
    hud.candidates = type(candidates) == "table" and candidates or {}
    -- The whole map rather than the one blip: the card that has just become the
    -- next one is an entity that was reading as connected a moment ago, and the
    -- one it replaced has to stop reading as the next card.
    Indicator.refreshMap()
end)

addEventHandler("onClientRender", root, function()
    if Indicator.mode ~= MODE_NONE or hud.counts then
        Indicator.render()
    end
end)

--- The map, on the same cadence the world marks use.
--
-- On a timer rather than per frame: the set of blips is decided by what
-- ANKIGTA knows and where the player is standing, and neither changes at frame
-- rate. Started when the resource starts, so the map fills in for a player who
-- never opens F7 -- the same reason the coronas do.
local mapTimer = false

addEventHandler("onClientResourceStart", resourceRoot, function()
    mapTimer = setTimer(Indicator.refreshMap, MAP_POLL_INTERVAL_MS, 0)
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
    if mapTimer and isTimer(mapTimer) then
        killTimer(mapTimer)
    end
    mapTimer = false
    clearBlip()
    Indicator.clearMap()
end)

ANKIGTA.Indicator = Indicator

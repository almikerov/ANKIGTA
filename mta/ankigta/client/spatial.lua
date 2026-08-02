ANKIGTA = ANKIGTA or {}

-- The world-polling half of the Activation Zone and the Next Card Indicator.
--
-- Tickets 22 and 23 built the decisions and left this out on purpose: the rules
-- are testable without a game, and the polling is not. The consequence was that
-- nothing in a running resource ever handed `Activation.update` a player
-- position or a candidate list, so no card could open by walking up to it.
-- This is that half.
--
-- The split of authority follows Implementation Decision 14: the server owns
-- the persistent Map Entity records and which Spatial Link is worth watching,
-- and this side owns the mapping to the Runtime Instance that is here right
-- now. So the server sends identities and metadata, never coordinates, and the
-- current position always comes off the live element.
--
-- ## Cadence
--
-- Every 250 ms, not every frame.
--
-- The budget is 2 ms of average frame time for everything ANKIGTA draws and
-- decides (story 58). One full pass over the reference world -- 5,000 Spatial
-- Link, all streamed, all eligible, all in the player's own interior -- is
-- most of a millisecond; ticket 30 measured the whole per-frame path at about
-- 1.2 ms back when the scan ran on every rendered frame, and the benchmark
-- still reports the pass on its own as `pollMsMax`. Running it per frame
-- spends a large fraction of the budget on the scan and leaves the HUD and the
-- marker to share the rest. At 250 ms and 60 fps it is one pass every fifteen
-- frames, and the arithmetic is in the report next to the number it produced.
--
-- The prior attempt reached the same shape from the other direction -- a 250 ms
-- timer over 500 bindings, with a per-render-frame full-map scan deliberately
-- rejected (`docs/design/prior-attempt-review.md`). That is a calibration
-- point rather than our threshold; what decides it is `spatial_frame` in
-- `python -m tests.perf`, which reads this interval out of the resource rather
-- than restating it, so changing the number here moves the measurement.
--
-- What 250 ms costs is latency: the smallest automatic delay is zero, and at
-- zero a card opens up to a quarter of a second after the player crosses the
-- edge of the zone. The default delay is one second, so for the default this is
-- a quarter of the shortest countdown.
--
-- The marker does not wait for the poll. It is drawn per frame over the handful
-- of entities carrying one card, and reads their positions then, so it follows
-- a moving Runtime Instance frame by frame rather than in 250 ms steps.

local CANDIDATES_EVENT = "ankigta:spatialCandidates"
local NEXT_CARD_EVENT = "ankigta:nextCard"
local OPEN_REQUEST_EVENT = "ankigta:requestSpatialOpen"

local POLL_INTERVAL_MS = 250

--- The element types a Map Entity may be (CONTEXT.md).
local MANAGED_TYPES = {"object", "vehicle", "ped", "marker"}

--- Kilometres per hour per unit of `getElementVelocity`.
--
-- GTA stores velocity per physics step rather than per second -- the step is
-- `CTimer::ms_fTimeStep`, read through `CGameSA::GetTimeStep` -- and MTA
-- exposes no speed accessor of its own, so the conversion is the caller's. At
-- the fixed 50 Hz step and one unit to the metre that is 50 * 3.6.
--
-- It is an approximation, and the one number in this file a machine cannot
-- check: ticket 22's manual checklist drives the speed gate against the game's
-- own speedometer, which is what settles it.
local KMH_PER_VELOCITY_UNIT = 180

local Spatial = {
    --- Every Spatial Link the server says is worth watching, in order.
    links = {},
    --- The same, by Map Entity, so a marker can be named by identity alone.
    linkByEntity = {},
    --- Which Map Entity carry the card the scheduler chose next, as the
    --- descriptors from `links` that they name.
    bearers = {},
    --- Managed elements this client knows about, and the ones streamed in.
    known = {},
    streamed = {},
    timer = false,
    --- Handed to `Activation.update`, and rebuilt in place: this is the table
    --- the reference world puts five thousand entries in, four times a second.
    candidates = {},
}

local function managedEntityId(element)
    local entityId = getElementData(element, "ankigtaEntityId")
    if type(entityId) ~= "string" or entityId == "" then
        return false
    end
    return entityId
end

--- Rebuild the runtime index from what the client currently holds.
--
-- Run when the link set changes rather than per poll: it walks every object,
-- vehicle and ped the client knows about, which is the whole world rather than
-- the part of it that is near. Between rebuilds the stream events keep it
-- current.
local function indexWorld()
    local known, streamed = {}, {}
    for _, kind in ipairs(MANAGED_TYPES) do
        for _, element in ipairs(getElementsByType(kind)) do
            local entityId = managedEntityId(element)
            if entityId then
                known[entityId] = element
                if isElementStreamedIn(element) then
                    streamed[entityId] = element
                end
            end
        end
    end
    Spatial.known = known
    Spatial.streamed = streamed
end

--- One candidate, filled in from the live element.
--
-- Returns `nil` where there is nothing live to fill it in from. A Map Entity
-- whose Runtime Instance is unstreamed or destroyed has no zone at all, and
-- leaving it out of the list is how that is said -- its Spatial Link is
-- untouched either way.
local function liveCandidate(link, into)
    local element = Spatial.streamed[link.entityId]
    if not element or not isElement(element) then
        return nil
    end
    local x, y, z = getElementPosition(element)
    if type(x) ~= "number" then
        return nil
    end
    into.mapId = link.mapId
    into.entityId = link.entityId
    into.cardIdentity = link.cardIdentity
    into.radius = link.radius
    into.eligible = link.eligible ~= false
    into.present = true
    into.hasActivationZone = link.showRadius == true
    into.x = x
    into.y = y
    into.z = z
    into.interior = getElementInterior(element) or 0
    into.dimension = getElementDimension(element) or 0
    return into
end

local function fill(list, links)
    local count = 0
    for _, link in ipairs(links) do
        local slot = list[count + 1]
        if slot == nil then
            slot = {}
            list[count + 1] = slot
        end
        if liveCandidate(link, slot) ~= nil then
            count = count + 1
        end
    end
    -- Trim rather than rebuild: the table is reused across polls, and a stale
    -- tail would be candidates that are no longer there.
    for index = #list, count + 1, -1 do
        list[index] = nil
    end
    return list
end

--- Every watched Spatial Link that has a Runtime Instance right now.
function Spatial.candidateList()
    return fill(Spatial.candidates, Spatial.links)
end

--- The same, for the entities carrying the card the scheduler chose next.
--
-- A fresh table each call, unlike the polled one. This runs per frame over the
-- entities carrying a single card -- usually one -- and the indicator groups
-- candidates by Anki Card Identity keyed on the list itself, so handing it the
-- same table with different contents would hand it a stale grouping.
function Spatial.markerList()
    return fill({}, Spatial.bearers)
end

--- What the player looks like to the activation rules.
function Spatial.observe()
    local x, y, z = getElementPosition(localPlayer)
    local vehicle = getPedOccupiedVehicle(localPlayer)
    local moving = isElement(vehicle) and vehicle or localPlayer
    local vx, vy, vz = getElementVelocity(moving)
    local speed = 0
    if type(vx) == "number" then
        speed = math.sqrt(vx * vx + vy * vy + vz * vz) * KMH_PER_VELOCITY_UNIT
    end
    return {
        x = tonumber(x) or 0,
        y = tonumber(y) or 0,
        z = tonumber(z) or 0,
        interior = getElementInterior(localPlayer) or 0,
        dimension = getElementDimension(localPlayer) or 0,
        speedKmh = speed,
        -- Review Mode is modal (story 48). While a card is open the world is
        -- not walked at all, and nothing else may open one.
        reviewOpen = type(isReviewModeActive) == "function"
            and isReviewModeActive() == true,
    }
end

--- One observation. Returns the card it asked the server to open, or `false`.
--
-- Asking is all this does. The card is opened by the server through the same
-- `openReviewModeFor` that a manual opening goes through, so there is one path
-- into Review Mode rather than a spatial one beside it.
function Spatial.tick()
    local decision = ANKIGTA.Activation.update(
        getTickCount() / 1000,
        Spatial.observe(),
        Spatial.candidateList()
    )
    if not decision then
        return false
    end
    triggerServerEvent(
        OPEN_REQUEST_EVENT,
        resourceRoot,
        decision.mapId,
        decision.entityId,
        decision.cardIdentity
    )
    return decision
end

function Spatial.polling()
    return Spatial.timer ~= false and isTimer(Spatial.timer)
end

local function stopPolling()
    if Spatial.timer and isTimer(Spatial.timer) then
        killTimer(Spatial.timer)
    end
    Spatial.timer = false
end

--- Poll while there is something to poll for, and not otherwise.
--
-- The server sends links only while a session is active and sends an empty set
-- when study pauses, so this is also how `Pause studying` turns the Activation
-- Zone off (story 46).
local function syncPolling()
    if #Spatial.links == 0 then
        stopPolling()
        ANKIGTA.Activation.cancel("no_candidates")
        return
    end
    if Spatial.polling() then
        return
    end
    Spatial.timer = setTimer(Spatial.tick, POLL_INTERVAL_MS, 0)
end

--- The cadence, so a report and a benchmark can state it rather than assume it.
function Spatial.pollIntervalMs()
    return POLL_INTERVAL_MS
end

function Spatial.diagnostics()
    local known, streamed = 0, 0
    for _ in pairs(Spatial.known) do
        known = known + 1
    end
    for _ in pairs(Spatial.streamed) do
        streamed = streamed + 1
    end
    return {
        links = #Spatial.links,
        bearers = #Spatial.bearers,
        knownInstances = known,
        streamedInstances = streamed,
        polling = Spatial.polling(),
        pollIntervalMs = POLL_INTERVAL_MS,
    }
end

local function entityKey(mapId, entityId)
    return tostring(mapId) .. "/" .. tostring(entityId)
end

--- Adopt a link set the server sent.
local function setLinks(links)
    local accepted, byEntity = {}, {}
    for _, link in ipairs(type(links) == "table" and links or {}) do
        if type(link) == "table"
            and type(link.mapId) == "string"
            and type(link.entityId) == "string"
        then
            accepted[#accepted + 1] = link
            byEntity[entityKey(link.mapId, link.entityId)] = link
        end
    end
    Spatial.links = accepted
    Spatial.linkByEntity = byEntity
    -- The marker's entities are named out of the link set, so a new set makes
    -- the old naming meaningless rather than merely out of date.
    Spatial.bearers = {}
    indexWorld()
    syncPolling()
end

addEvent(CANDIDATES_EVENT, true)
addEventHandler(CANDIDATES_EVENT, resourceRoot, function(links)
    setLinks(links)
end)

addEvent(NEXT_CARD_EVENT, true)
addEventHandler(NEXT_CARD_EVENT, resourceRoot, function(_cardIdentity, bearers)
    -- The event names Map Entity; everything else about them -- radius,
    -- `Show radius`, which card they carry -- is already in the link set, and
    -- a second copy arriving alongside is a second copy that can disagree.
    local accepted = {}
    for _, bearer in ipairs(type(bearers) == "table" and bearers or {}) do
        if type(bearer) == "table" then
            local link = Spatial.linkByEntity[
                entityKey(bearer.mapId, bearer.entityId)
            ]
            if link then
                accepted[#accepted + 1] = link
            end
        end
    end
    Spatial.bearers = accepted
end)

-- Streaming keeps the index current between link changes. An element the
-- client has never seen is picked up here too, which is what happens when a
-- map loads after the link set arrived.
addEventHandler("onClientElementStreamIn", root, function()
    local entityId = managedEntityId(source)
    if entityId then
        Spatial.known[entityId] = source
        Spatial.streamed[entityId] = source
    end
end)

addEventHandler("onClientElementStreamOut", root, function()
    local entityId = managedEntityId(source)
    if entityId then
        Spatial.streamed[entityId] = nil
    end
end)

addEventHandler("onClientElementDestroy", root, function()
    local entityId = managedEntityId(source)
    if entityId then
        Spatial.known[entityId] = nil
        Spatial.streamed[entityId] = nil
    end
end)

addEventHandler("onClientResourceStop", resourceRoot, function()
    stopPolling()
end)

if ANKIGTA.Indicator then
    -- The marker's candidates come from here rather than from the event, so it
    -- points at where the Runtime Instance is now.
    ANKIGTA.Indicator.setCandidateSource(Spatial.markerList)
end

ANKIGTA.Spatial = Spatial

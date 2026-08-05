ANKIGTA = ANKIGTA or {}

-- Activation Zone: a physical sphere around a live Runtime Instance inside
-- which its linked card may open.
--
-- Two ways in, and the entity says which. `Automatic` is the zone deciding on
-- the player's behalf once its delay and the speed threshold are satisfied.
-- `Key` is the zone *offering*, and the player taking it with a press.
--
-- `Key` is not a slower `Automatic`. The delay and the speed threshold exist
-- because a card that opens by itself has to be sure the player meant to be
-- there; a press carries that certainty already. So in `Key` neither of them
-- stands between the offer and the card -- the offer holds for as long as the
-- player is in the zone, and ends when they leave it.
--
-- Which entity is nearest is answered once, by `shared/nearest.lua`, and only
-- then does that entity say how it opens. The alternative -- one winner per
-- mode -- would mean two entities offering at once and no way to say which the
-- press meant.
--
-- The decision is kept separate from the world-polling that feeds it, so the
-- interesting rules -- which entity wins, when the countdown survives, what
-- cancels it -- are testable without a game running.

local DEFAULT_RADIUS = 3
local MIN_RADIUS = 0.5
local MAX_RADIUS = 50
local RADIUS_STEP = 0.5

local DEFAULT_DELAY_SECONDS = 0
local MIN_DELAY_SECONDS = 0
local MAX_DELAY_SECONDS = 60

-- The upper-bound gate is always applied. Zero therefore means that a card can
-- open only while the player is not moving.
local DEFAULT_MAX_SPEED_KMH = 0

-- Defaults come from the shared schema where it is loaded, so the schema and
-- this module cannot drift into disagreeing about what "default" means.
local function schemaDefault(key, fallback)
    if ANKIGTA.Settings then
        local value = ANKIGTA.Settings.default(key)
        if value ~= nil then
            return value
        end
    end
    return fallback
end

--- The schema's own answer about a value, where the schema is loaded.
--
-- An incremental reload can hand this client one script ahead of another, and
-- the rules below are worth having in force either way: a module that refused
-- every value until a sibling had loaded would be a module that stops working
-- because something else has not started.
local function schemaAccepts(key, value)
    if not ANKIGTA.Settings then
        return true
    end
    return ANKIGTA.Settings.validate(key, value)
end

local Activation = {
    settings = {
        defaultRadius = schemaDefault("activationRadius", DEFAULT_RADIUS),
        delaySeconds = schemaDefault(
            "activationDelaySeconds",
            DEFAULT_DELAY_SECONDS
        ),
        maxSpeedKmh = schemaDefault(
            "maxActivationSpeedKmh",
            DEFAULT_MAX_SPEED_KMH
        ),
        activationType = schemaDefault("activationType", "automatic"),
        activationKey = schemaDefault("activationKey", "e"),
    },
    countdown = false,
    --- The card standing offered right now, and the key that takes it.
    --
    -- `false` when nothing is offered. Only ever one, because only one entity
    -- is the nearest, and only one card can open.
    offered = false,
}

local function round(value, places)
    local factor = 10 ^ places
    return math.floor(value * factor + 0.5) / factor
end

--- Validate a per-entity Activation Zone radius.
-- Invalid values are rejected rather than clamped: silently turning 200 into 50
-- would hide a mistake behind a zone the user never chose.
function Activation.validRadius(value)
    local number = tonumber(value)
    if number == nil then
        return false, "radius_not_a_number"
    end
    if number < MIN_RADIUS or number > MAX_RADIUS then
        return false, "radius_out_of_range"
    end
    if round(number / RADIUS_STEP, 6) % 1 ~= 0 then
        return false, "radius_not_on_step"
    end
    return true
end

function Activation.validDelay(value)
    local number = tonumber(value)
    if number == nil then
        return false, "delay_not_a_number"
    end
    if number < MIN_DELAY_SECONDS or number > MAX_DELAY_SECONDS then
        return false, "delay_out_of_range"
    end
    if round(number, 2) ~= number then
        return false, "delay_too_precise"
    end
    return true
end

function Activation.validSpeed(value)
    local number = tonumber(value)
    if number == nil or number < 0 then
        return false, "speed_invalid"
    end
    return true
end

-- --- the key that takes an offer ------------------------------------------
--
-- Bound here rather than beside the polling, because this is the module that
-- knows which key is in force: the global one, or the one the offered entity
-- names instead. Whoever opens cards registers itself, so this file asks the
-- server for nothing and knows nothing about how a card is opened -- there is
-- one way in and it is not this one's business what it is.

--- The key `bindKey` accepted, or `false` if none is bound.
local boundKey = false
local opener = false

--- Who to tell when the offer is taken.
function Activation.setOpener(handler)
    opener = type(handler) == "function" and handler or false
    return true
end

--- The key a press would arrive on, for whoever has to name it.
function Activation.boundKey()
    return boundKey
end

--- The offer, or `false`.
--
-- Read by whatever draws `<KEY> to view`: the prompt names the key that is
-- really bound rather than the one the setting asked for, so a key MTA refused
-- shows as no prompt instead of as an instruction that does nothing.
function Activation.offer()
    return Activation.offered
end

--- Take the offer. Returns the card to open, or `false`.
--
-- Cleared as it is taken, so one press is one request. If nothing opens -- the
-- companion is down, say -- the next observation puts the offer back, because
-- the player is still standing in the zone.
function Activation.take()
    local offer = Activation.offered
    if not offer then
        return false
    end
    Activation.offered = false
    return {
        mapId = offer.mapId,
        entityId = offer.entityId,
        cardIdentity = offer.cardIdentity,
    }
end

local function pressed()
    local taken = Activation.take()
    if taken and opener then
        opener(taken)
    end
end

--- Listen on this key and no other.
--
-- Idempotent, because it runs on every observation: the key in force changes
-- when the player walks from an entity that names its own to one that does not.
local function rebind(key)
    if boundKey == key then
        return boundKey
    end
    if boundKey then
        unbindKey(boundKey, "down", pressed)
        boundKey = false
    end
    if type(key) == "string" and key ~= "" and bindKey(key, "down", pressed) then
        boundKey = key
    end
    return boundKey
end

--- Which way in this candidate offers, and on which key.
--
-- The entity's own answer where it has one, the global where it has not. Two
-- lines rather than a resolved value sent from the server: the global lives on
-- this side already, so changing it moves every entity that follows it without
-- the candidate set being sent again.
local function typeOf(candidate)
    local own = candidate and candidate.activationType
    if own == "automatic" or own == "key" then
        return own
    end
    return Activation.settings.activationType
end

--- Could anything in this world be waiting for a press?
--
-- Answered from the global and from one flag the candidate set carries, never
-- by looking at the candidates: this decides whether the zones are walked at
-- all, and walking them to find out would be the thing it exists to avoid.
--
-- Whoever hands over a candidate set says whether any entity in it names its
-- own activation type. That is one pass per set rather than one per
-- observation, and a set arrives when the server has something new to say.
local anyEntityMode = false

function Activation.noteEntityModes(any)
    anyEntityMode = any == true
    return true
end

local function keyModePossible()
    return Activation.settings.activationType == "key" or anyEntityMode
end

local function keyOf(candidate)
    local own = candidate and candidate.activationKey
    if type(own) == "string" and own ~= "" then
        return own
    end
    return Activation.settings.activationKey
end

function Activation.configure(settings)
    if type(settings) ~= "table" then
        return false, "invalid_settings"
    end
    if settings.activationType ~= nil then
        local ok, reason =
            schemaAccepts("activationType", settings.activationType)
        if not ok then
            return false, reason
        end
        Activation.settings.activationType = settings.activationType
    end
    if settings.activationKey ~= nil then
        local ok, reason =
            schemaAccepts("activationKey", settings.activationKey)
        if not ok then
            return false, reason
        end
        Activation.settings.activationKey = settings.activationKey
        if not Activation.offered then
            -- Nothing is being offered on another key right now, so the new
            -- global takes effect at once rather than at the next observation.
            rebind(settings.activationKey)
        end
    end
    if settings.defaultRadius ~= nil then
        local ok, reason = Activation.validRadius(settings.defaultRadius)
        if not ok then
            return false, reason
        end
        Activation.settings.defaultRadius = tonumber(settings.defaultRadius)
    end
    if settings.delaySeconds ~= nil then
        local ok, reason = Activation.validDelay(settings.delaySeconds)
        if not ok then
            return false, reason
        end
        Activation.settings.delaySeconds = tonumber(settings.delaySeconds)
    end
    if settings.maxSpeedKmh ~= nil then
        local ok, reason = Activation.validSpeed(settings.maxSpeedKmh)
        if not ok then
            return false, reason
        end
        Activation.settings.maxSpeedKmh = tonumber(settings.maxSpeedKmh)
    end
    return true
end

--- The radius a newly created Map Entity inherits.
function Activation.radiusForNewEntity()
    return Activation.settings.defaultRadius
end

local function candidateKey(candidate)
    return tostring(candidate.mapId) .. "/" .. tostring(candidate.entityId)
end

--- How many candidates there are, whose zone the player is in, and which of
--- those is nearest.
--
-- One pass. A zone exists only where its Runtime Instance does: an unstreamed
-- or destroyed instance has no zone, though its Spatial Link is untouched.
--
-- Collecting the ones inside into a list and then picking the nearest from it
-- read more plainly, and it walked the world twice and allocated a table on
-- every observation. This runs against every streamed Spatial Link, sixty
-- times a second, inside a two-millisecond budget for everything ANKIGTA draws
-- and decides; the second walk is a third of it.
--
-- The order comes from `shared/nearest.lua` rather than from a comparison
-- written here, so the Activation Zone and the Next Card Indicator cannot
-- drift into disagreeing about which entity is nearest.
--
-- Distance is tested before eligibility, which reads backwards: eligibility is
-- the interesting rule and distance is arithmetic. It is the order that costs
-- least, and the two are conditions of the same `and` -- every candidate that
-- ends up inside satisfies both, whichever was asked first. Almost every
-- Spatial Link in a loaded world is far away, and one axis rejects it.
local function observeZones(player, candidates)
    local tracked, inside = 0, 0
    local best, bestDistance = false, nil
    local defaultRadius = Activation.settings.defaultRadius
    -- Everything the loop reads on every candidate, read once. Each of these
    -- is a table lookup per Spatial Link per observation, and the world holds
    -- thousands of them.
    local nearest = ANKIGTA.Nearest
    local withinRadius, beats = nearest.withinRadius, nearest.beats
    local interior, dimension = player.interior, player.dimension
    local originX = player.x
    for _, candidate in ipairs(candidates or {}) do
        tracked = tracked + 1
        local radius = candidate.radius
        if type(radius) ~= "number" then
            radius = tonumber(radius) or defaultRadius
        end
        -- One axis, before anything else is read: this is the rejection almost
        -- every candidate takes, and `withinRadius` makes it again for the few
        -- that survive it.
        local offset = candidate.x - originX
        if radius > 0 and offset <= radius and offset >= -radius
            and candidate.eligible == true
            and candidate.present ~= false
            and candidate.interior == interior
            and candidate.dimension == dimension
        then
            local distance = withinRadius(player, candidate, radius)
            if distance ~= nil then
                inside = inside + 1
                if beats(candidate, distance, best, bestDistance) then
                    best, bestDistance = candidate, distance
                end
            end
        end
    end
    return tracked, inside, best, bestDistance
end

--- Nothing is being walked up to any more, whichever of the two it was.
--
-- The offer goes with the countdown, always. They are the two ways of saying
-- which entity is being activated right now and there is only ever one, so a
-- caller that means "stop" means both. The one place that wants an offer
-- afterwards sets it *after* calling this, which reads in the order it happens.
function Activation.cancel(reason)
    Activation.offered = false
    if not Activation.countdown then
        return false
    end
    Activation.countdown = false
    return true, reason or "cancelled"
end

function Activation.pending()
    return Activation.countdown
end

-- What the last observation that walked the world saw.
--
-- An observation that stopped at a gate -- a review is open, the player is too
-- fast -- never looks, and says so through `reason` while leaving the counts at
-- what the last real look found.
--
-- "Why did nothing open" has no cheap answer from a player's machine, and the
-- benchmark has nothing to assert against either: the update function reports
-- an opening and is otherwise silent. This is the seam for both -- how many
-- candidates were tracked, how many of their zones the player is inside, which
-- one is nearest and how far, and what is open right now.
local observation = {
    observedAt = false,
    tracked = 0,
    inZone = 0,
    nearestMapId = false,
    nearestEntityId = false,
    nearestDistance = false,
    -- Why nothing is counting down, when nothing is.
    reason = "not_observed",
    -- The key the offer standing right now is taken on, or `false`.
    offeredKey = false,
    -- The last card activation asked to open, kept until the next observation
    -- that runs with the review closed.
    openMapId = false,
    openEntityId = false,
}

local function note(fields)
    for key, value in pairs(fields) do
        observation[key] = value
    end
end

--- The activation state, as one flat table.
function Activation.diagnostics()
    local countdown = Activation.countdown
    return {
        observedAt = observation.observedAt,
        tracked = observation.tracked,
        inZone = observation.inZone,
        nearestMapId = observation.nearestMapId,
        nearestEntityId = observation.nearestEntityId,
        nearestDistance = observation.nearestDistance,
        reason = observation.reason,
        openMapId = observation.openMapId,
        openEntityId = observation.openEntityId,
        countingDown = countdown ~= false and countdown ~= nil,
        countdownKey = countdown and countdown.key or false,
        countdownStartedAt = countdown and countdown.startedAt or false,
        defaultRadius = Activation.settings.defaultRadius,
        delaySeconds = Activation.settings.delaySeconds,
        maxSpeedKmh = Activation.settings.maxSpeedKmh,
        activationType = Activation.settings.activationType,
        activationKey = Activation.settings.activationKey,
        boundKey = boundKey,
        offeredKey = observation.offeredKey,
        offeredMapId = Activation.offered and Activation.offered.mapId or false,
        offeredEntityId = Activation.offered
            and Activation.offered.entityId or false,
    }
end

--- Advance the activation state by one observation.
-- `now` is in seconds. Returns `false` when nothing should happen, or a table
-- describing the card to open.
function Activation.update(now, player, candidates)
    if type(player) ~= "table" then
        note({reason = "no_observation"})
        return false
    end
    if player.reviewOpen == true then
        -- An open card outranks the world. Map, runtime and link changes may
        -- happen underneath it; activation recalculates once it closes. The
        -- world is not walked at all here, so the counts stay at what the last
        -- observation that did look saw.
        --
        -- The offer goes with it: a prompt drawn behind an open card is an
        -- offer of the thing already on screen.
        Activation.offered = false
        note({observedAt = now, reason = "review_open", offeredKey = false})
        return false
    end
    -- Nothing is open once an observation runs with the review closed, so the
    -- report cannot go on naming a card the player already finished.
    note({observedAt = now, openMapId = false, openEntityId = false})

    -- Measured before the zones are walked and acted on after, because the
    -- answer depends on which entity wins: the threshold gates a card that
    -- opens by itself, and not one the player asked for by pressing a key.
    --
    -- Where nothing can be waiting for a press it still short-circuits the walk
    -- outright, which is what it always did: at this speed nothing may open
    -- whatever is around, so measuring every zone and discarding the answer is
    -- a scan for a decision already made.
    local speed = tonumber(player.speedKmh) or 0
    local tooFast = speed > Activation.settings.maxSpeedKmh
    if tooFast and not keyModePossible() then
        Activation.cancel("too_fast")
        note({
            reason = "too_fast",
            inZone = 0,
            nearestMapId = false,
            nearestEntityId = false,
            nearestDistance = false,
            offeredKey = false,
        })
        return false
    end

    local tracked, inside, target, targetDistanceSquared =
        observeZones(player, candidates)
    note({
        tracked = tracked,
        inZone = inside,
        nearestMapId = false,
        nearestEntityId = false,
        nearestDistance = false,
    })
    if not target then
        Activation.cancel("left_zone")
        rebind(Activation.settings.activationKey)
        note({reason = "no_zone", offeredKey = false})
        return false
    end

    local key = candidateKey(target)
    note({
        nearestMapId = target.mapId,
        nearestEntityId = target.entityId,
        nearestDistance = math.sqrt(targetDistanceSquared),
    })

    if typeOf(target) == "key" then
        -- No countdown and no clock. The press is the certainty the delay waits
        -- for, so the offer stands from the moment the player is inside until
        -- the moment they are not.
        Activation.cancel("offered")
        local bound = rebind(keyOf(target))
        Activation.offered = bound and {
            mapId = target.mapId,
            entityId = target.entityId,
            cardIdentity = target.cardIdentity,
            -- The key that is really bound, never the one the setting asked
            -- for: a name MTA refused would otherwise be drawn over the entity
            -- as an instruction that does nothing.
            key = bound,
        } or false
        note({reason = "offered", offeredKey = bound or false})
        return false
    end

    -- The nearest entity opens by itself, so nothing is being offered -- and
    -- the key goes back to the global one, which is what a press anywhere else
    -- in the world would arrive on.
    Activation.offered = false
    rebind(Activation.settings.activationKey)
    if tooFast then
        Activation.cancel("too_fast")
        note({reason = "too_fast", offeredKey = false})
        return false
    end

    local countdown = Activation.countdown

    if not countdown or countdown.key ~= key then
        -- Re-target rather than inherit the previous entity's elapsed time, so
        -- walking past one zone into another cannot open the second instantly.
        Activation.countdown = {
            key = key,
            candidate = target,
            startedAt = now,
        }
        countdown = Activation.countdown
    end

    if now - countdown.startedAt < Activation.settings.delaySeconds then
        note({reason = "counting_down"})
        return false
    end

    Activation.countdown = false
    note({
        reason = "opened",
        openMapId = target.mapId,
        openEntityId = target.entityId,
    })
    return {
        mapId = target.mapId,
        entityId = target.entityId,
        cardIdentity = target.cardIdentity,
    }
end

-- Bound from the moment this loads rather than from the first offer. A key
-- nobody has bound is a key that reaches the game instead, and the first thing
-- the player would notice is the press doing whatever GTA does with it.
rebind(Activation.settings.activationKey)

ANKIGTA.Activation = Activation

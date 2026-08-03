ANKIGTA = ANKIGTA or {}

-- Activation Zone: a physical sphere around a live Runtime Instance inside
-- which its linked card may open by itself.
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
    },
    countdown = false,
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

function Activation.configure(settings)
    if type(settings) ~= "table" then
        return false, "invalid_settings"
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

function Activation.cancel(reason)
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
        note({observedAt = now, reason = "review_open"})
        return false
    end
    -- Nothing is open once an observation runs with the review closed, so the
    -- report cannot go on naming a card the player already finished.
    note({observedAt = now, openMapId = false, openEntityId = false})

    local speed = tonumber(player.speedKmh) or 0
    if speed > Activation.settings.maxSpeedKmh then
        -- Also without walking the world: at this speed nothing may open
        -- whatever is around, and the scan is the expensive part.
        Activation.cancel("too_fast")
        note({
            reason = "too_fast",
            inZone = 0,
            nearestMapId = false,
            nearestEntityId = false,
            nearestDistance = false,
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
        note({reason = "no_zone"})
        return false
    end

    local key = candidateKey(target)
    note({
        nearestMapId = target.mapId,
        nearestEntityId = target.entityId,
        nearestDistance = math.sqrt(targetDistanceSquared),
    })
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

ANKIGTA.Activation = Activation

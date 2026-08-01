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

local DEFAULT_DELAY_SECONDS = 1
local MIN_DELAY_SECONDS = 0
local MAX_DELAY_SECONDS = 60

-- Effectively "no gate" by default: a speed limit is always applied, but the
-- default is far above anything reachable on foot or in a car.
local DEFAULT_MAX_SPEED_KMH = 10000

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

local function distanceSquared(a, b)
    return ANKIGTA.Nearest.distanceSquared(a, b)
end

local function candidateKey(candidate)
    return tostring(candidate.mapId) .. "/" .. tostring(candidate.entityId)
end

--- Entities whose zone the player is currently inside.
-- A zone exists only where its Runtime Instance does: an unstreamed or
-- destroyed instance has no zone, though its Spatial Link is untouched.
local function eligibleCandidates(player, candidates)
    local inside = {}
    for _, candidate in ipairs(candidates or {}) do
        local radius = tonumber(candidate.radius)
            or Activation.settings.defaultRadius
        if candidate.eligible == true
            and candidate.present ~= false
            and candidate.interior == player.interior
            and candidate.dimension == player.dimension
            and radius > 0
            and distanceSquared(player, candidate) <= radius * radius
        then
            table.insert(inside, candidate)
        end
    end
    return inside
end

-- Ties are broken on the Map Entity's identity rather than on snapshot order;
-- see `shared/nearest.lua` for why that is the difference between a choice and
-- an accident.
local function nearest(player, candidates)
    return ANKIGTA.Nearest.select(player, candidates)
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

--- Advance the activation state by one observation.
-- `now` is in seconds. Returns `false` when nothing should happen, or a table
-- describing the card to open.
function Activation.update(now, player, candidates)
    if type(player) ~= "table" then
        return false
    end
    if player.reviewOpen == true then
        -- An open card outranks the world. Map, runtime and link changes may
        -- happen underneath it; activation recalculates once it closes.
        return false
    end

    local speed = tonumber(player.speedKmh) or 0
    if speed > Activation.settings.maxSpeedKmh then
        Activation.cancel("too_fast")
        return false
    end

    local inside = eligibleCandidates(player, candidates)
    if #inside == 0 then
        Activation.cancel("left_zone")
        return false
    end

    local target = nearest(player, inside)
    local key = candidateKey(target)
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
        return false
    end

    Activation.countdown = false
    return {
        mapId = target.mapId,
        entityId = target.entityId,
        cardIdentity = target.cardIdentity,
    }
end

ANKIGTA.Activation = Activation

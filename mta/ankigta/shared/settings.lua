ANKIGTA = ANKIGTA or {}

-- The settings schema, shared by both sides so they cannot disagree about what
-- a setting is.
--
-- Authority is per setting (ADR 0014). The server owns the world and study
-- state because it is the thing that persists; the client owns presentation,
-- input and audio because those are properties of one player's machine; the
-- companion add-on owns the connection because it is the side that publishes
-- it. A side that does not own a setting may read it, never write it.
--
-- Two kinds of setting stay out of Change History: connection settings, which
-- are a local override rather than shared state, and UI placement, which is
-- nobody's idea of a decision worth undoing.

local SERVER = "server"
local CLIENT = "client"
local ADDON = "addon"

local Settings = {
    SERVER = SERVER,
    CLIENT = CLIENT,
    ADDON = ADDON,
}

local function numeric(minimum, maximum, step, decimals)
    return {
        kind = "number",
        minimum = minimum,
        maximum = maximum,
        step = step,
        decimals = decimals,
    }
end

local function choice(values)
    return {kind = "choice", values = values}
end

local function toggle()
    return {kind = "boolean"}
end

--- Every user-facing setting, its owner, its default and its rules.
Settings.schema = {
    -- World and study: persisted, shared, undoable.
    activationRadius = {
        authority = SERVER,
        default = 3,
        rule = numeric(0.5, 50, 0.5),
    },
    activationDelaySeconds = {
        authority = SERVER,
        default = 1,
        rule = numeric(0, 60, nil, 2),
    },
    maxActivationSpeedKmh = {
        authority = SERVER,
        default = 10000,
        rule = numeric(0, 100000, nil, 2),
    },
    allowEarlyReview = {authority = SERVER, default = false, rule = toggle()},
    pauseOnReviewerOpen = {authority = SERVER, default = true, rule = toggle()},
    includeInStudy = {authority = SERVER, default = true, rule = toggle()},

    -- Presentation, input and audio: this player's machine only.
    indicatorMode = {
        authority = CLIENT,
        default = "none",
        rule = choice({"sphere_and_minimap", "minimap_only", "none"}),
    },
    reviewProtection = {authority = CLIENT, default = true, rule = toggle()},
    disablePlayerControls = {authority = CLIENT, default = true, rule = toggle()},
    closeAfterRating = {authority = CLIENT, default = true, rule = toggle()},
    cardAudioEnabled = {authority = CLIENT, default = true, rule = toggle()},
    muteGameWorld = {authority = CLIENT, default = false, rule = toggle()},
    uiScale = {authority = CLIENT, default = 1, rule = numeric(0.5, 3, nil, 2)},
    language = {
        authority = CLIENT,
        default = "auto",
        rule = choice({"auto", "ru", "en"}),
    },
    uiPlacement = {
        authority = CLIENT,
        default = "default",
        rule = {kind = "opaque"},
        excludedFromHistory = true,
    },

    -- The connection: owned by the add-on, overridable locally on each side,
    -- and never part of shared history.
    -- No default: the add-on publishes these, or the user sets them manually.
    -- Inventing one here would mean shipping a value that fails its own rule.
    connectionPort = {
        authority = ADDON,
        optional = true,
        rule = numeric(1, 65535, 1),
        localOverride = true,
        excludedFromHistory = true,
    },
    connectionToken = {
        authority = ADDON,
        optional = true,
        rule = {kind = "secret"},
        localOverride = true,
        excludedFromHistory = true,
    },
}

function Settings.definition(key)
    return Settings.schema[key]
end

function Settings.authorityOf(key)
    local definition = Settings.schema[key]
    return definition and definition.authority or false
end

--- May this side write this setting?
function Settings.canWrite(side, key)
    local definition = Settings.schema[key]
    if not definition then
        return false, "unknown_setting"
    end
    if definition.authority == side then
        return true
    end
    -- A manual connection override is local to whichever side made it, so both
    -- sides may write it even though the add-on owns the published value.
    if definition.localOverride and (side == SERVER or side == CLIENT) then
        return true
    end
    return false, "wrong_authority"
end

function Settings.inChangeHistory(key)
    local definition = Settings.schema[key]
    if not definition then
        return false
    end
    return definition.excludedFromHistory ~= true
end

function Settings.default(key)
    local definition = Settings.schema[key]
    if not definition then
        return nil
    end
    return definition.default
end

local function roundTo(value, decimals)
    local factor = 10 ^ decimals
    return math.floor(value * factor + 0.5) / factor
end

--- Validate a proposed value.
--
-- Returns `true`, or `false` plus a localization key. Out-of-range input is
-- rejected rather than clamped: silently turning a mistyped 200 into 50 leaves
-- the user with a setting they never chose and no idea it happened.
function Settings.validate(key, value)
    local definition = Settings.schema[key]
    if not definition then
        return false, "settings.error.unknown"
    end
    local rule = definition.rule

    if rule.kind == "boolean" then
        if type(value) ~= "boolean" then
            return false, "settings.error.not_a_boolean"
        end
        return true
    end

    if rule.kind == "choice" then
        for _, allowed in ipairs(rule.values) do
            if value == allowed then
                return true
            end
        end
        return false, "settings.error.not_a_choice"
    end

    if rule.kind == "number" then
        local number = tonumber(value)
        if number == nil then
            return false, "settings.error.not_a_number"
        end
        if number < rule.minimum or number > rule.maximum then
            return false, "settings.error.out_of_range"
        end
        if rule.step and roundTo(number / rule.step, 6) % 1 ~= 0 then
            return false, "settings.error.not_on_step"
        end
        if rule.decimals and roundTo(number, rule.decimals) ~= number then
            return false, "settings.error.too_precise"
        end
        return true
    end

    if rule.kind == "secret" then
        if type(value) ~= "string" then
            return false, "settings.error.not_a_string"
        end
        return true
    end

    return true
end

ANKIGTA.Settings = Settings

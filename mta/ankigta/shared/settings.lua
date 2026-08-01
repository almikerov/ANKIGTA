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
-- Authority also decides Change History: only what the server owns is
-- journalled, because the history is a table in the server's own database and
-- undo cannot reach across the boundary to a file on the player's machine
-- (ADR 0028). Connection settings and UI placement stay out for that reason
-- too, rather than each for a reason of its own.

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
    },

    -- The connection: owned by the add-on, overridable locally on each side.
    -- No default: the add-on publishes these, or the user sets them manually.
    -- Inventing one here would mean shipping a value that fails its own rule.
    connectionPort = {
        authority = ADDON,
        optional = true,
        rule = numeric(1, 65535, 1),
        localOverride = true,
    },
    connectionToken = {
        authority = ADDON,
        optional = true,
        rule = {kind = "secret"},
        localOverride = true,
    },
}

-- The schema is a hash, so it has no order of its own. The settings panel needs
-- one to lay its rows out in, and this is it: world and study first, then the
-- machine's own presentation, then the connection the add-on owns.
Settings.order = {
    "activationRadius",
    "activationDelaySeconds",
    "maxActivationSpeedKmh",
    "allowEarlyReview",
    "includeInStudy",
    "indicatorMode",
    "reviewProtection",
    "disablePlayerControls",
    "closeAfterRating",
    "cardAudioEnabled",
    "muteGameWorld",
    "uiScale",
    "language",
    "uiPlacement",
    "connectionPort",
    "connectionToken",
}

--- Every setting, in the order the panel should show them.
--
-- A key missing from `Settings.order` is still returned, sorted, after the ones
-- that are listed. Forgetting to add a new setting here is a layout mistake;
-- letting that mistake hide the setting from the only screen that can change it
-- would make it an unreachable setting instead.
function Settings.orderedKeys()
    local keys = {}
    local listed = {}
    for _, key in ipairs(Settings.order) do
        if Settings.schema[key] then
            listed[key] = true
            table.insert(keys, key)
        end
    end

    local missing = {}
    for key in pairs(Settings.schema) do
        if not listed[key] then
            table.insert(missing, key)
        end
    end
    table.sort(missing)
    for _, key in ipairs(missing) do
        table.insert(keys, key)
    end

    return keys
end

function Settings.definition(key)
    return Settings.schema[key]
end

function Settings.authorityOf(key)
    local definition = Settings.schema[key]
    return definition and definition.authority or false
end

--- Why may this side write this setting -- because it owns it, or because the
--- setting allows a local override?
--
-- The two are not interchangeable. An authoritative write is the value; an
-- override is one side's local replacement for it, and the store has to put
-- them in different places.
function Settings.writeKind(side, key)
    local definition = Settings.schema[key]
    if not definition then
        return false, "unknown_setting"
    end
    if definition.authority == side then
        return "authority"
    end
    -- A manual connection override is local to whichever side made it, so both
    -- sides may write it even though the add-on owns the published value.
    if definition.localOverride and (side == SERVER or side == CLIENT) then
        return "local_override"
    end
    return false, "wrong_authority"
end

--- May this side write this setting at all?
function Settings.canWrite(side, key)
    local kind, reason = Settings.writeKind(side, key)
    if not kind then
        return false, reason
    end
    return true
end

--- Stamp a local override with the side that made it.
--
-- ADR 0014: an override has priority over the published value **only on its
-- own side**. Without the stamp, an override read back later is just a value,
-- and whichever side finds it would adopt it as its own.
function Settings.overrideBy(side, key, value)
    local definition = Settings.schema[key]
    if not definition then
        return false, "unknown_setting"
    end
    if definition.localOverride ~= true then
        return false, "not_a_local_override"
    end
    local allowed, reason = Settings.canWrite(side, key)
    if not allowed then
        return false, reason
    end
    local valid, why = Settings.validate(key, value)
    if not valid then
        return false, why
    end
    return {key = key, side = side, value = Settings.normalize(key, value)}
end

--- Does an override govern this side?
--
-- Only the side that made it. A companion override is the value this side must
-- agree with, never a value it adopts.
function Settings.overrideAppliesTo(side, record)
    return type(record) == "table" and record.side == side
end

--- Does changing this setting belong in Change History?
--
-- Only if the server owns it. History is one table in the server's database,
-- and undo has no way back across the authority boundary: the player's own
-- presentation, input and audio live in a file on their machine, and the
-- connection belongs to the add-on. Asking authority rather than a per-setting
-- flag means a new client setting cannot arrive claiming to be undoable while
-- nothing records it -- which is exactly how `indicatorMode`, `uiScale` and six
-- others came to lie about themselves (ADR 0028).
--
-- `excludedFromHistory` remains as an override for a server setting that should
-- not be journalled. It is the exception, so it is written down per setting;
-- the rule is not.
function Settings.inChangeHistory(key)
    local definition = Settings.schema[key]
    if not definition then
        return false
    end
    if definition.excludedFromHistory == true then
        return false
    end
    return definition.authority == SERVER
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

--- The value as it should be stored, once validated.
--
-- A number typed into a text field arrives as a string; storing it that way
-- would make `40001` and `"40001"` two different ports later on.
function Settings.normalize(key, value)
    local definition = Settings.schema[key]
    if definition and definition.rule.kind == "number" then
        return tonumber(value)
    end
    return value
end

ANKIGTA.Settings = Settings

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
-- Change History follows from authority rather than from a per-setting flag
-- (ADR 0028): the history is the server's, and the server can only put back a
-- value it holds. A setting owned by the client or the add-on is therefore
-- never recorded, and nothing has to remember to say so.

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

--- A colour the user picks, as `#RRGGBB`.
--
-- Text rather than three numbers because that is what a colour picker hands
-- back and what a person reads back out of a settings file. The alpha is not
-- in it: opacity is a separate setting with a separate range, and packing it
-- into the same string would make "half-transparent blue" one value that no
-- control can edit half of.
local function colour()
    return {kind = "colour"}
end

--- Where the movable surfaces sit, as a fraction of the screen.
--
-- Normalized rather than absolute so the same file describes the same corner
-- on 1280x720 and on 3840x2160. Pixels would put a window off screen the first
-- time the player changed resolution.
local function placement()
    return {kind = "placement"}
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
        default = 0,
        rule = numeric(0, 60, nil, 2),
    },
    maxActivationSpeedKmh = {
        authority = SERVER,
        default = 0,
        rule = numeric(0, 100000, nil, 2),
    },
    -- Which cards the session takes. `allowEarlyReview` was a boolean whose
    -- name described neither of its states: off did not mean "no review" and
    -- on did not mean "early only". A mode says which one is in force, and
    -- leaves room for the one that shows text instead of a card (ticket 05).
    reviewMode = {
        authority = SERVER,
        default = "allow_due",
        rule = choice({"allow_due", "allow_all"}),
    },
    includeInStudy = {authority = SERVER, default = true, rule = toggle()},
    -- What a corona looks like where the entity does not say otherwise. Owned
    -- by the server for the same reason `activationRadius` is: these are the
    -- defaults behind a value stored on the Map Entity itself, and a default
    -- kept on one player's machine would describe a marker every other player
    -- sees differently.
    coronaColour = {authority = SERVER, default = "#3cc8ff", rule = colour()},
    coronaOpacity = {
        authority = SERVER,
        default = 0.5,
        rule = numeric(0, 1, nil, 2),
    },

    -- Presentation, input and audio: this player's machine only.
    -- A way of looking rather than a property of the thing looked at: while it
    -- is on, the selected row's Activation Zone is drawn. `Show corona` is the
    -- other half of the pair and lives on the entity, because that one is a
    -- property of the thing.
    drawRadius = {authority = CLIENT, default = false, rule = toggle()},
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
    -- No `step`: the buttons move UI Scale in 0.05, but a value typed by hand
    -- only has to be a two-decimal number in range. Making the button's step a
    -- validation rule would reject 1.23, which the user is entitled to type.
    uiScale = {authority = CLIENT, default = 1, rule = numeric(0.5, 2, nil, 2)},
    language = {
        authority = CLIENT,
        default = "auto",
        rule = choice({"auto", "ru", "en"}),
    },
    uiPlacement = {authority = CLIENT, default = {}, rule = placement()},

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
-- one to lay its rows out in. Language and the companion port are the two
-- things a player needs first; the remaining world, study and presentation
-- settings follow them.
Settings.order = {
    "language",
    "connectionPort",
    "activationRadius",
    "activationDelaySeconds",
    "maxActivationSpeedKmh",
    "reviewMode",
    "includeInStudy",
    "drawRadius",
    "coronaColour",
    "coronaOpacity",
    "indicatorMode",
    "reviewProtection",
    "disablePlayerControls",
    "closeAfterRating",
    "cardAudioEnabled",
    "muteGameWorld",
    "uiScale",
    "uiPlacement",
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

--- Is this setting the kind of change Undo can put back?
--
-- ADR 0028: Change History is the server's, and Undo works by having the
-- server rewrite what it holds. A value that lives on the player's machine or
-- inside the add-on is not something it holds, so it is never recorded. That
-- follows from authority rather than from a flag repeated once per setting --
-- which is how `indicatorMode`, `uiScale` and six others came to claim they
-- were undoable while nothing recorded them. Only a *server*-owned setting has
-- to say so itself.
function Settings.inChangeHistory(key)
    local definition = Settings.schema[key]
    if not definition then
        return false
    end
    if definition.authority ~= SERVER then
        return false
    end
    return definition.excludedFromHistory ~= true
end

local function copied(value)
    if type(value) ~= "table" then
        return value
    end
    local result = {}
    for key, item in pairs(value) do
        result[key] = copied(item)
    end
    return result
end

function Settings.default(key)
    local definition = Settings.schema[key]
    if not definition then
        return nil
    end
    -- A table default is handed out as a copy. Sharing the schema's own table
    -- would let whoever stores into it edit the default for everyone else --
    -- and the first window that remembers where it sits does exactly that.
    return copied(definition.default)
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

    if rule.kind == "colour" then
        if type(value) ~= "string" then
            return false, "settings.error.not_a_colour"
        end
        -- Exactly `#RRGGBB`. Three-digit shorthand and a named colour are
        -- things a browser understands and `tocolor` does not, so accepting
        -- them here would store a value the world cannot be drawn in.
        if not string.match(value, "^#%x%x%x%x%x%x$") then
            return false, "settings.error.not_a_colour"
        end
        return true
    end

    if rule.kind == "secret" then
        if type(value) ~= "string" then
            return false, "settings.error.not_a_string"
        end
        return true
    end

    if rule.kind == "placement" then
        if type(value) ~= "table" then
            return false, "settings.error.not_a_placement"
        end
        for surface, spot in pairs(value) do
            if type(surface) ~= "string" or type(spot) ~= "table" then
                return false, "settings.error.not_a_placement"
            end
            local x, y = tonumber(spot.x), tonumber(spot.y)
            -- Outside 0..1 is not a spot on any screen, so it is an edited or
            -- corrupted file rather than a place a window was ever dragged to.
            if x == nil or y == nil
                or x < 0 or x > 1 or y < 0 or y > 1
            then
                return false, "settings.error.not_a_placement"
            end
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
    if definition and definition.rule.kind == "colour" then
        -- One case, so the same colour chosen in a colour picker and typed by
        -- hand is one stored value rather than two that compare unequal.
        return string.lower(value)
    end
    if definition and definition.rule.kind == "placement" then
        -- Rebuilt rather than passed through: a placement read back out of
        -- JSON may carry its coordinates as text, and anything else the file
        -- happened to contain is not part of a placement.
        local result = {}
        for surface, spot in pairs(value) do
            result[surface] = {x = tonumber(spot.x), y = tonumber(spot.y)}
        end
        return result
    end
    return value
end

--- A stored `#RRGGBB` as the three channels a colour is drawn from.
--
-- Here rather than beside the drawing, because this is where the format is
-- decided: the rule above says what a colour may be, and one reader of it
-- keeps "what a colour looks like" from being answered twice.
--
-- Returns `nil` for anything the rule would have rejected, so a corrupted
-- value falls back to a default rather than being drawn as black.
function Settings.colourChannels(value)
    if type(value) ~= "string" or not string.match(value, "^#%x%x%x%x%x%x$") then
        return nil
    end
    return tonumber(string.sub(value, 2, 3), 16),
        tonumber(string.sub(value, 4, 5), 16),
        tonumber(string.sub(value, 6, 7), 16)
end

ANKIGTA.Settings = Settings

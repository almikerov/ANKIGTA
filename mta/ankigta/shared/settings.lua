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

--- Free text the user types, bounded so a field name stays a field name.
--
-- Bounded rather than open: this is stored, sent to the client on every
-- settings snapshot, and compared against a note type's field names. Anki's
-- own field names are short, and a value longer than any of them can only be
-- a mistake or a paste.
local function text(maximumLength)
    return {kind = "text", maximumLength = maximumLength}
end

--- The keys ANKIGTA has already bound, and what each one does.
--
-- Here rather than at the three `bindKey` calls, because two different
-- questions read it: the client binds through it, and `activationKey` is
-- refused when it names one of these. A second list would answer the second
-- question about a binding the first had since moved.
Settings.reservedKeys = {
    panel = "F7",
    dismiss = "escape",
}

--- Is this key one ANKIGTA already answers to?
function Settings.keyIsReserved(name)
    for _, reserved in pairs(Settings.reservedKeys) do
        if reserved == name then
            return true
        end
    end
    return false
end

--- Every key `activationKey` may name, spelt the way MTA spells it.
--
-- MTA's own table (`Client/core/CKeyBinds.cpp`, `g_bindableKeys`, read
-- 2026-08-05, SHA-256
-- d87c62055f7763f9ea3057a092b73cc074abfa45b9f0f7b2941a19ee6d61d542): letters
-- and digits are lowercase and unshifted, the function keys are uppercase, and
-- `F8` is absent because MTA keeps it for its console. Keyboard only -- a mouse
-- button is a key `bindKey` accepts and not one to open a card with.
--
-- A list rather than "any string": `bindKey` refuses a name it does not know,
-- and a refusal there is a setting that reads as saved and binds nothing.
--
-- It is also what a *captured* key is checked against. The key is pressed now
-- rather than chosen from a list, so the panel has to name the key that was
-- pressed -- and a physical key MTA has no word for is refused here rather than
-- stored under a name `bindKey` will not take.
Settings.bindableKeys = {
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F9", "F10", "F11", "F12",
    "space", "enter", "tab", "backspace", "capslock",
    "lshift", "rshift", "lctrl", "rctrl", "lalt", "ralt",
    "insert", "delete", "home", "end", "pgup", "pgdn",
    "arrow_l", "arrow_u", "arrow_r", "arrow_d",
    "num_0", "num_1", "num_2", "num_3", "num_4",
    "num_5", "num_6", "num_7", "num_8", "num_9", "num_enter",
    "escape",
}

local function keyName()
    return {kind = "key", values = Settings.bindableKeys}
end

--- The keys a player may actually end up with.
--
-- `bindableKeys` is every key ANKIGTA is willing to bind and this is the part of
-- it that is still free. The panel takes a key by listening for it rather than
-- by offering a list, so this is what separates the two refusals a press can
-- earn: a name absent from `bindableKeys` is a key MTA cannot name, and a name
-- present there but absent here is one ANKIGTA already answers to.
function Settings.offeredKeys()
    local free = {}
    for _, name in ipairs(Settings.bindableKeys) do
        if not Settings.keyIsReserved(name) then
            free[#free + 1] = name
        end
    end
    return free
end

--- A colour the user picks, as `#rrggbb`.
--
-- Text rather than three numbers because that is what the picker hands back
-- and what a person reads out of a settings file. Prose here says colour and
-- identifiers say color, which is what the rest of this resource already does
-- (`ZONE_COLOR`, `settings.colorHex`); one spelling in code is worth more than
-- agreement with the sentence above it.
local function color()
    return {kind = "color"}
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
--
-- `entityOverride` names the `map_entity_metadata` column a Map Entity says its
-- own answer in. It is what makes a setting overridable on a link -- the panel
-- offers a way to clear those overrides everywhere by reading this, the store
-- finds the column by reading this, and neither keeps a list of its own. A
-- setting that gains an override gains both by gaining this field.
--
-- Every such column is NULL where the entity has nothing of its own to say.
-- One spelling for "follows the global", so clearing an override is one
-- statement whatever the setting is; a column that said it with `''` or `-1`
-- would need the sweep to know which, which is the list this avoids.
Settings.schema = {
    -- World and study: persisted, shared, undoable.
    activationRadius = {
        authority = SERVER,
        default = 3,
        rule = numeric(0.5, 50, 0.5),
        entityOverride = {column = "radius_override", field = "radius"},
    },
    -- Which of the two ways in this entity offers. `automatic` is the zone and
    -- its delay deciding on the player's behalf; `key` is the zone offering and
    -- the player taking it. Not a slower `automatic`: a press is the certainty
    -- the delay and the speed gate exist to wait for, so in `key` neither of
    -- them stands between the offer and the card.
    activationType = {
        authority = SERVER,
        default = "automatic",
        rule = choice({"automatic", "key"}),
        entityOverride = {column = "activation_type_override", field = "activationType"},
    },
    -- Which key takes the offer. Overridable per entity for the same reason the
    -- radius is: one object can be the odd one out without moving everything
    -- else.
    activationKey = {
        authority = SERVER,
        default = "e",
        rule = keyName(),
        entityOverride = {column = "activation_key_override", field = "activationKey"},
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
    -- What walking up to a linked Map Entity does. `allowEarlyReview` was a
    -- boolean whose name described neither of its states: off did not mean "no
    -- review" and on did not mean "early only". A mode says which one is in
    -- force, and left room for the third.
    --
    -- `allow_due` opens only cards the scheduler calls due and `allow_all`
    -- opens them whether they are due or not. `show_text` opens nothing at
    -- all: the entity carries a Text Label instead, nothing is presented and
    -- nothing is rated (ADR 0029), so no session is built and the one door
    -- into Review Mode refuses to open.
    reviewMode = {
        authority = SERVER,
        default = "allow_due",
        rule = choice({"allow_due", "allow_all", "show_text"}),
    },
    -- The Text Label: what it says, how it looks, and how far it carries.
    --
    -- Server-owned like the Activation Zone radius, and for the same reason:
    -- these belong to the world and to the link rather than to one player's
    -- machine, and the first three are answerable on the Map Entity itself.
    --
    -- Empty means "whichever field comes first with words in it", which is the
    -- right answer for a player who has not chosen and for a note type nobody
    -- had in mind when they did. On an entity, empty is how the override is
    -- cleared -- the same thing an emptied radius box says -- so an entity
    -- cannot ask for "the first field" while the global names one. That is the
    -- price of one spelling for "nothing of its own" (NULL) across every
    -- override, and it is the spelling the sweep that clears them reads.
    textLabelField = {
        authority = SERVER,
        default = "",
        rule = text(128),
        entityOverride = {
            column = "text_label_field_override",
            field = "textLabelField",
        },
    },
    -- Chosen freely rather than from a safe palette. A label is picked to
    -- stand out against whatever it hangs on, and no list of twelve colours
    -- covers a city; what keeps a free choice legible is the dark outline the
    -- renderer always draws under it, not the palette.
    textLabelColor = {
        authority = SERVER,
        default = "#ffffff",
        rule = color(),
        entityOverride = {
            column = "text_label_color_override",
            field = "textLabelColor",
        },
    },
    textLabelSize = {
        authority = SERVER,
        default = 1,
        rule = numeric(0.25, 5, nil, 2),
        entityOverride = {
            column = "text_label_size_override",
            field = "textLabelSize",
        },
    },
    -- Its own distance, and global only. The Activation Zone radius is about
    -- standing close enough to open a card and is unused in this mode; a label
    -- covers nothing and demands nothing, so it carries further than a zone
    -- you have to stand in, and it is not gated on speed either -- reading one
    -- while driving past is the point (ADR 0029).
    --
    -- The maximum is `client/world_marks.lua`'s draw distance, which is the
    -- ceiling on everything ANKIGTA draws. Beyond it nothing is drawn whatever
    -- this says, and a setting that reads as saved and changes nothing is a
    -- control arguing with the thing that obeys it. The two numbers are pinned
    -- together by a test rather than by one file reading the other: the
    -- ceiling is the client's, and this table is shared.
    textLabelDistance = {
        authority = SERVER,
        default = 25,
        rule = numeric(1, 150, nil, 1),
    },
    -- Whether an entity wears a corona at all, and what it looks like where the
    -- entity does not say otherwise. Owned by the server for the same reason
    -- `activationRadius` is: these are the defaults behind a value stored on
    -- the Map Entity itself, and a default kept on one player's machine would
    -- describe a marker every other player sees differently.
    --
    -- `showCorona` was the entity's alone until it needed a way back: an
    -- entity that has been told to show one, months ago, could only be told
    -- otherwise one at a time. A global behind it is what "put these back the
    -- way the rest of them are" means.
    showCorona = {
        authority = SERVER,
        default = false,
        rule = toggle(),
        entityOverride = {column = "show_corona_override", field = "showCorona"},
    },
    coronaColor = {
        authority = SERVER,
        default = "#3cc8ff",
        rule = color(),
        entityOverride = {column = "corona_color_override", field = "coronaColor"},
    },
    coronaOpacity = {
        authority = SERVER,
        default = 0.6,
        rule = numeric(0, 1, nil, 2),
        entityOverride = {column = "corona_opacity_override", field = "coronaOpacity"},
    },
    -- No `includeInStudy`. Which maps take part is not a preference: a Map
    -- Entity is in play when its map is loaded, which the world already
    -- answers. The switch offered a row per map ANKIGTA had ever seen --
    -- including the editor's own scratch resources -- and was the only thing
    -- narrowing study at all.

    -- Presentation, input and audio: this player's machine only.
    -- A way of looking rather than a property of the thing looked at: while it
    -- is on, the selected row's Activation Zone is drawn for as long as the
    -- panel is open. The answer outlives F7 and the drawing does not -- it is
    -- about the row being worked on, and nothing is being worked on with the
    -- window shut. `Show corona` is the other half of the pair and is a
    -- property of the thing, everyone sees it, and it is there whether or not
    -- anybody has a window open -- so it is server-owned and overridable above.
    --
    -- `shownWith` because the two were pulled apart correctly and then left on
    -- different screens: both answer "what do I see around this row", both are
    -- reached while a row is selected, and walking to Settings for one and back
    -- to the list for the other is two journeys for one decision. It stays the
    -- client's and stays two-valued -- an entity has nothing to say about a way
    -- of looking, so there is no global here for one to follow.
    drawRadius = {
        authority = CLIENT,
        default = false,
        rule = toggle(),
        shownWith = "entity",
    },
    indicatorMode = {
        authority = CLIENT,
        default = "none",
        rule = choice({"beam_and_minimap", "minimap_only", "none"}),
    },
    -- Which of ANKIGTA's own objects are on the map, and which of them are
    -- ready to be studied. Deliberately not a fourth value of `indicatorMode`:
    -- that setting answers "how is the *next card* marked" and has three values
    -- about one entity, and this answers "is the rest of the world marked at
    -- all". The player's own machine, like every other way of looking.
    showEntitiesOnMap = {authority = CLIENT, default = false, rule = toggle()},
    -- Selecting a row and looking at it are the same intention almost every
    -- time, so a click does both. "Almost every time" is not "every time" --
    -- arrowing down fifty rows with the camera flying to each is not a way to
    -- read a list -- so this is the way to say no. The player's own machine
    -- decides where the player's own camera goes, hence CLIENT.
    focusOnSelect = {authority = CLIENT, default = true, rule = toggle()},
    -- How visible the panel is while the mouse is elsewhere. Under the cursor,
    -- or while a field is being typed into, it is fully opaque whatever this
    -- says: a panel being used is not in anybody's way.
    --
    -- The floor is a rule, not a warning. Zero would be a window that is still
    -- there, still eats the cursor, and cannot be seen -- so a value below the
    -- minimum is refused like any other out-of-range number, and no stored
    -- value can make the panel invisible.
    panelIdleOpacity = {
        authority = CLIENT,
        default = 0.6,
        rule = numeric(0.2, 1, nil, 2),
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
-- one to lay its rows out in.
--
-- UI Scale first. It is the setting a player reaches for before any other --
-- nothing else on this panel can be read comfortably until the interface is a
-- readable size -- and on a list this long it was second from last, at the
-- bottom of a scroll. The companion port follows it, because nothing works at
-- all until Anki is reachable; then the world, study and presentation settings.
Settings.order = {
    "uiScale",
    "connectionPort",
    "activationRadius",
    -- Which way in, and the key that takes it, next to the zone they are about.
    "activationType",
    "activationKey",
    "activationDelaySeconds",
    "maxActivationSpeedKmh",
    "reviewMode",
    -- What `Show text` puts on the object, straight under the mode that is the
    -- only reason any of them does anything.
    "textLabelField",
    "textLabelColor",
    "textLabelSize",
    "textLabelDistance",
    -- Whether the entity wears a mark at all and what that mark looks like.
    -- `drawRadius` was at the head of this group and is not a member of it: it
    -- is a way of looking rather than a property of anything, and it is on the
    -- entity pane beside `Show corona` now.
    "showCorona",
    "coronaColor",
    "coronaOpacity",
    -- What ANKIGTA puts on the map: how the next card is marked, and whether
    -- everything else is marked at all.
    "indicatorMode",
    "showEntitiesOnMap",
    "focusOnSelect",
    "panelIdleOpacity",
    "reviewProtection",
    "disablePlayerControls",
    "closeAfterRating",
    "cardAudioEnabled",
    "muteGameWorld",
    "uiPlacement",
    "connectionToken",
}

--- Which surface offers this setting.
--
-- `"settings"` unless the schema says otherwise, so a setting belongs to the
-- Settings list by existing. A setting that names another surface is offered
-- there instead of being listed twice -- `drawRadius` is on the entity pane,
-- beside the `Show corona` it is half a decision with.
function Settings.shownWith(key)
    local definition = Settings.schema[key]
    return definition and definition.shownWith or "settings"
end

--- Every setting the Settings list shows, in the order it should show them.
--
-- A key missing from `Settings.order` is still returned, sorted, after the ones
-- that are listed. Forgetting to add a new setting here is a layout mistake;
-- letting that mistake hide the setting from the only screen that can change it
-- would make it an unreachable setting instead.
--
-- A setting `shownWith` somewhere else is not that mistake: it is reachable,
-- named, and on a screen this list is not. So it is left out here rather than
-- appended to the end of a list it does not belong to.
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
        if not listed[key] and Settings.shownWith(key) == "settings" then
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

--- Where a Map Entity says its own answer to this setting, if it may have one.
function Settings.entityOverrideColumn(key)
    local definition = Settings.schema[key]
    local override = definition and definition.entityOverride
    return override and override.column or false
end

--- What that answer is called everywhere outside the database.
--
-- The store's column and the field the snapshot, the panel and Change History
-- use are two names for one answer, and both are declared here: a store that
-- knew the second would be keeping a list of its own, which is the thing this
-- ticket exists to stop.
function Settings.entityOverrideField(key)
    local definition = Settings.schema[key]
    local override = definition and definition.entityOverride
    return override and override.field or false
end

--- Every setting a link can override, in the order the panel lays them out.
--
-- Derived from the schema, so the control that clears an override everywhere is
-- offered for a setting by that setting having an override -- never by being
-- named in a list here or in the panel or in the store. The set has grown three
-- times in three tickets; a list would be missing the fourth.
function Settings.entityOverridableKeys()
    local keys = {}
    for _, key in ipairs(Settings.orderedKeys()) do
        if Settings.entityOverrideColumn(key) then
            keys[#keys + 1] = key
        end
    end
    return keys
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

--- A number as its own rule says it should read.
--
-- Every server-to-client hop packs a non-integer Lua number into a 32-bit
-- float, so a stored `0.6` arrives as `0.60000001999999997` and a field showing
-- it says `0.60000002`. Measured on the owner's running server rather than
-- guessed: `triggerClientEvent` and `setElementData` both do it, and `0.25`
-- comes through untouched only because a power-of-two fraction is exact in
-- single precision -- which is the whole of why retreating to a default of
-- `0.5` would have appeared to work while `0.55` and `0.1` kept the tail.
--
-- So a value is put back to the precision the setting's own rule declares,
-- once, at the boundary where a number becomes something a person reads --
-- rather than at each of the places that show one, or for the one setting the
-- tail was noticed on.
--
-- A rule with no `decimals` declares no precision, and none of them needs one:
-- those settings step in whole or half units, and both are exact on the wire.
function Settings.rounded(key, value)
    local definition = Settings.schema[key]
    local rule = definition and definition.rule
    if not rule or rule.kind ~= "number" or not rule.decimals then
        return value
    end
    local number = tonumber(value)
    if number == nil then
        return value
    end
    return roundTo(number, rule.decimals)
end

--- Values a setting used to be told in, and what they are called now.
--
-- A stored setting is the player's answer, and renaming the word for it in this
-- file must not read as them never having answered: an unrecognized value is
-- discarded on load, so `indicatorMode` would have gone quietly back to `none`
-- for anybody who had chosen the mark.
--
-- `sphere_and_minimap` named a shape nothing ever drew. What stands over the
-- next card is a beam -- `dxDrawMaterialLine3D`, a standing bar as wide as the
-- Activation Zone's radius -- and the sphere is the *zone*, drawn by
-- `client/world_marks.lua` for the row being worked on.
--
-- Read by `validate`, which asks whether this is an answer the setting can
-- have, and applied by `normalize`, which says how that answer is stored. The
-- same two steps a colour goes through: `#FFAA00` is valid and stores lowercase.
local RENAMED_VALUES = {
    indicatorMode = {sphere_and_minimap = "beam_and_minimap"},
}

local function renamedValue(key, value)
    local renames = RENAMED_VALUES[key]
    if not renames or type(value) ~= "string" then
        return nil
    end
    return renames[value]
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
        -- The same answer under the name it used to be stored as. Valid,
        -- because it is one of the choices; `normalize` is what respells it.
        if renamedValue(key, value) then
            return true
        end
        return false, "settings.error.not_a_choice"
    end

    -- A key name, and one nobody here is already listening for. Shadowing F7
    -- would leave the panel's own key opening a card instead, which is a
    -- setting that quietly breaks a different feature -- so it is refused, and
    -- the reason says which kind of no it is.
    if rule.kind == "key" then
        local known = false
        for _, allowed in ipairs(rule.values) do
            if value == allowed then
                known = true
                break
            end
        end
        if not known then
            return false, "settings.error.not_a_key"
        end
        if Settings.keyIsReserved(value) then
            return false, "settings.error.key_in_use"
        end
        return true
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

    -- Words the user typed, and no rule about which words: a note type's
    -- fields are named by whoever made it, so anything this refused beyond a
    -- length would be refusing a field that really exists. Bytes rather than
    -- characters, because the bound is about what is stored and sent.
    if rule.kind == "text" then
        if type(value) ~= "string" then
            return false, "settings.error.not_a_string"
        end
        if rule.maximumLength and #value > rule.maximumLength then
            return false, "settings.error.too_long"
        end
        return true
    end

    -- `#rrggbb`, because that is what the page draws with and what the picker
    -- it is chosen in hands back. No alpha: opacity is its own setting where
    -- anything has one, so a colour carrying a fourth channel would be two
    -- answers to one question.
    if rule.kind == "color" then
        if type(value) ~= "string"
            or not string.find(value, "^#%x%x%x%x%x%x$")
        then
            return false, "settings.error.not_a_color"
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
    if definition and definition.rule.kind == "choice" then
        -- One spelling for one answer, so a value stored under an older name is
        -- put back into the one the rule offers today.
        return renamedValue(key, value) or value
    end
    if definition and definition.rule.kind == "color" then
        -- One spelling for one colour: `#FFAA00` and `#ffaa00` compared as
        -- text are two different stored values for the same thing.
        if type(value) ~= "string" then
            return value
        end
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

--- A stored `#rrggbb` as the three channels something is drawn in.
--
-- Here rather than beside the drawing, because this is where the format is
-- decided: the rule above says what a colour may be, and one reader of it
-- keeps "what a colour looks like" from being answered twice.
--
-- Returns `nil` for anything the rule would have refused, so a corrupted or
-- hand-edited value falls back to a default rather than being drawn as black
-- -- black is a colour somebody could have chosen, and this never is.
function Settings.colorChannels(value)
    if type(value) ~= "string" or not string.find(value, "^#%x%x%x%x%x%x$") then
        return nil
    end
    return tonumber(string.sub(value, 2, 3), 16),
        tonumber(string.sub(value, 4, 5), 16),
        tonumber(string.sub(value, 6, 7), 16)
end

ANKIGTA.Settings = Settings

ANKIGTA = ANKIGTA or {}

-- Which Map Entity is showing what, in Review Mode `Show text`.
--
-- The server decides this and the client draws it. Everything the decision
-- needs is here -- the Spatial Links, the cached words behind their cards, the
-- global settings and each entity's own overrides -- and none of it is on the
-- player's machine. Sending resolved lines rather than a note and a rule also
-- keeps the per-frame work on the client down to reading a position and
-- drawing text.
--
-- Nothing in this file consults a card's state, a session or a scheduler. A
-- Text Label is not a presentation of an Anki Card and cannot be rated
-- (ADR 0029), so whether the card is due has no bearing on whether its words
-- are drawn -- and neither has whether Anki is running.

local TextLabels = {}

local function schema()
    return ANKIGTA.Settings
end

--- The three globals a Text Label falls back on.
--
-- Read through the schema's own default where the store has nothing, so a
-- fresh database draws the same label a configured one with untouched settings
-- does.
function TextLabels.globals()
    local function value(key)
        local stored = ANKIGTA.SettingsStore.get(key)
        if stored == nil then
            return schema().default(key)
        end
        return stored
    end
    return {
        textLabelField = value("textLabelField"),
        textLabelColor = value("textLabelColor"),
        textLabelSize = value("textLabelSize"),
    }
end

--- What one entity ends up with: its own answer, or the global behind it.
--
-- `overrides` is `Store.overridesOf(row)`, in which a field is absent exactly
-- when the entity's column is NULL -- the one spelling of "nothing of its own"
-- every override in this resource uses. So there is no sentinel to reserve and
-- no empty string to tell apart from an unanswered question.
--
-- Each own answer is checked against the schema's rule for the setting it
-- overrides before it is used: a row hand-edited in SQLite must not be able to
-- put a colour the picker would refuse into a `tocolor` call.
function TextLabels.styleFor(overrides, globals)
    overrides = type(overrides) == "table" and overrides or {}
    globals = type(globals) == "table" and globals or {}
    local style = {overridden = false}
    for _, key in ipairs({"textLabelField", "textLabelColor", "textLabelSize"}) do
        local own = overrides[key]
        if own ~= nil and schema().validate(key, own) then
            style[key] = own
            style.overridden = true
        else
            local global = globals[key]
            if global == nil or not schema().validate(key, global) then
                global = schema().default(key)
            end
            style[key] = global
        end
    end
    return style
end

--- What one row would show, whether or not anything is currently drawing it.
--
-- Returns `false` for a row that is not a Text Label at all -- unlinked, on a
-- map that is not loaded, or standing for a Map Entity that has left the map
-- data and so has nothing to hang a label on.
--
-- A linked row whose words are not cached yet still comes back, with no lines
-- and a reason. Silence there would be indistinguishable from a note that says
-- nothing, and the panel has to be able to tell the player which it is.
function TextLabels.forRow(row, notes, globals, loadedMaps)
    if type(row) ~= "table" or row.link_state ~= "active" then
        return false
    end
    if type(loadedMaps) == "table" and loadedMaps[row.map_id] ~= true then
        return false
    end
    if row.entity_state == "entity_missing" then
        return false
    end
    local cardId = tonumber(row.card_id)
    if type(row.collection_uuid) ~= "string" or cardId == nil then
        return false
    end

    local style = TextLabels.styleFor(ANKIGTA.Store.overridesOf(row), globals)
    local label = {
        mapId = row.map_id,
        entityId = row.entity_id,
        color = style.textLabelColor,
        size = style.textLabelSize,
        requestedField = style.textLabelField,
        overridden = style.overridden,
        fieldName = "",
        fallback = false,
        reason = "not_cached",
        lines = {},
        truncated = false,
    }

    local fields = type(notes) == "table"
        and notes[ANKIGTA.Store.cachedNoteKey(row.collection_uuid, cardId)]
        or nil
    if type(fields) ~= "table" then
        -- The link is real and its words have simply not been read yet: the
        -- companion has never been connected since it was made. Said rather
        -- than drawn as an empty label.
        return label
    end

    local built = ANKIGTA.TextLabel.build(fields, style.textLabelField)
    label.fieldName = built.fieldName
    label.fallback = built.fallback
    label.reason = built.reason
    label.lines = built.lines
    label.truncated = built.truncated
    return label
end

--- Every Text Label the world should be showing, in store order.
--
-- Store order rather than distance order: which of them is near is the
-- client's question, asked of live elements this side never sees.
function TextLabels.build(rows, notes, globals, loadedMaps)
    local labels = {}
    for _, row in ipairs(type(rows) == "table" and rows or {}) do
        local label = TextLabels.forRow(row, notes, globals, loadedMaps)
        -- A label with nothing to say is not sent. There is no such thing as
        -- an empty Text Label: an object wearing a blank line reads as broken,
        -- and the row in the panel is where "this note has no words" is said.
        if label and #label.lines > 0 then
            labels[#labels + 1] = label
        end
    end
    return labels
end

ANKIGTA.TextLabels = TextLabels

ANKIGTA = ANKIGTA or {}

-- The client's half of the settings (ADR 0014): presentation, input and audio,
-- which are properties of this one machine rather than of the shared world.
-- They are kept in a private client-side file, so a resource restart brings
-- back what the player chose here rather than what the server thinks.
--
-- Nothing here reaches Change History. History is server-owned and undoing a
-- value that lives on another machine is not a thing the server can do; the
-- schema already marks which settings that applies to, and this side simply
-- has none of the shared ones.

local SIDE = "client"
local SERVER_SIDE = "server"
local SETTINGS_EVENT = "ankigta:settings"
local SETTINGS_PATH = "@ankigta-settings.json"
local CANDIDATE_PATH = "@ankigta-settings.json.tmp"

local ClientSettings = {
    side = SIDE,
    values = {},
    -- What the server last said about the settings it owns. Kept apart from
    -- `values` so a setting this side does not own can never be written back
    -- to the local file as if it were the player's own choice.
    serverValues = {},
    loaded = false,
}

local function schema()
    return ANKIGTA.Settings
end

local function isOwned(key)
    return schema().writeKind(SIDE, key) == "authority"
end

local function discard(key, reason)
    outputDebugString(
        "[ANKIGTA] discarded_stored_setting: "
            .. tostring(key) .. " (" .. tostring(reason) .. ")",
        2
    )
end

local function decodeJson(value)
    if type(value) ~= "string" then
        return false
    end
    local decoded = fromJSON(value)
    if type(decoded) == "table"
        and #decoded == 1
        and type(decoded[1]) == "table"
    then
        return decoded[1]
    end
    return decoded
end

local function encodeJson(value)
    local encoded = toJSON(value, true)
    if not encoded then
        return false
    end
    if string.sub(encoded, 1, 1) == "["
        and string.sub(encoded, -1) == "]"
    then
        return string.sub(encoded, 2, -2)
    end
    return encoded
end

local function readJson(path)
    if not fileExists(path) then
        return false
    end
    local handle = fileOpen(path, true)
    if not handle then
        return false
    end
    local contents = fileRead(handle, fileGetSize(handle))
    fileClose(handle)
    return decodeJson(contents)
end

local function readStored()
    if not fileExists(SETTINGS_PATH) then
        return {}
    end
    local decoded = readJson(SETTINGS_PATH)
    if type(decoded) ~= "table" then
        -- An unreadable file is not a reason to refuse to start: every setting
        -- falls back to its default and the player can set them again.
        discard(SETTINGS_PATH, "unreadable")
        return {}
    end
    return decoded
end

--- Write the whole file, then prove it can be read back before replacing.
local function writeStored(values)
    local encoded = encodeJson(values)
    if not encoded then
        return false, "settings_encode_failed"
    end
    if fileExists(CANDIDATE_PATH) then
        fileDelete(CANDIDATE_PATH)
    end
    local handle = fileCreate(CANDIDATE_PATH)
    if not handle then
        return false, "settings_write_failed"
    end
    fileWrite(handle, encoded)
    fileFlush(handle)
    fileClose(handle)
    if type(readJson(CANDIDATE_PATH)) ~= "table" then
        fileDelete(CANDIDATE_PATH)
        return false, "settings_validation_failed"
    end
    if fileExists(SETTINGS_PATH) and not fileDelete(SETTINGS_PATH) then
        fileDelete(CANDIDATE_PATH)
        return false, "settings_replace_failed"
    end
    if not fileRename(CANDIDATE_PATH, SETTINGS_PATH) then
        return false, "settings_replace_failed"
    end
    return true
end

--- Put the current values in force.
--
-- Applying is part of loading, not a separate courtesy: a stored setting that
-- nothing acts on is a setting the player did not really change.
function ClientSettings.apply()
    local values = ClientSettings.values
    if ANKIGTA.Layout then
        -- Before the rest: the modules below draw at whatever scale the layout
        -- manager is holding, so it has to be holding the stored one first.
        ANKIGTA.Layout.applySettings(values.uiScale, values.uiPlacement)
    end
    if ANKIGTA.Indicator then
        ANKIGTA.Indicator.setMode(values.indicatorMode)
    end
    if ANKIGTA.ZoneMarks then
        ANKIGTA.ZoneMarks.applySettings({drawRadius = values.drawRadius})
    end
    if setReviewProtection then
        setReviewProtection(values.reviewProtection, values.disablePlayerControls)
    end
    if setReviewAudio then
        setReviewAudio(values.cardAudioEnabled, values.muteGameWorld)
    end
    if setCloseAfterRating then
        setCloseAfterRating(values.closeAfterRating)
    end
    return true
end

--- Re-read the stored settings and put them in force.
function ClientSettings.load()
    local values = {}
    for key, definition in pairs(schema().schema) do
        if isOwned(key) and definition.default ~= nil then
            values[key] = definition.default
        end
    end

    for key, value in pairs(readStored()) do
        if not isOwned(key) then
            -- Either a setting another side owns, or one this version does not
            -- know. Neither is this store's to adopt.
            discard(key, "wrong_authority")
        else
            local valid, reason = schema().validate(key, value)
            if valid then
                values[key] = schema().normalize(key, value)
            else
                discard(key, reason)
            end
        end
    end

    ClientSettings.values = values
    ClientSettings.loaded = true
    ClientSettings.apply()
    return true
end

--- Take the world and study settings the server owns.
--
-- Read, never written: the values are checked against the same schema before
-- anything acts on them, and a key this side would be entitled to write is
-- refused outright -- being told a value is not the same as being governed.
function ClientSettings.receiveServerSettings(values)
    if type(values) ~= "table" then
        return false, "invalid_settings"
    end
    local accepted = {}
    for key, value in pairs(values) do
        if schema().writeKind(SERVER_SIDE, key) ~= "authority" then
            discard(key, "wrong_authority")
        else
            local valid, reason = schema().validate(key, value)
            if valid then
                accepted[key] = schema().normalize(key, value)
            else
                discard(key, reason)
            end
        end
    end

    for key, value in pairs(accepted) do
        ClientSettings.serverValues[key] = value
    end
    if ANKIGTA.Activation then
        ANKIGTA.Activation.configure({
            defaultRadius = accepted.activationRadius,
            delaySeconds = accepted.activationDelaySeconds,
            maxSpeedKmh = accepted.maxActivationSpeedKmh,
        })
    end
    if ANKIGTA.ZoneMarks then
        -- What a corona looks like where the entity says nothing of its own.
        -- Server-owned, so it arrives here rather than being read out of the
        -- local file, and reaches the marks by the same path the activation
        -- rules take.
        ANKIGTA.ZoneMarks.applySettings({
            coronaColour = accepted.coronaColour,
            coronaOpacity = accepted.coronaOpacity,
        })
    end
    return true
end

function ClientSettings.get(key)
    local definition = schema().definition(key)
    if not definition then
        return false, "settings.error.unknown"
    end
    if not isOwned(key) then
        -- The server owns it: report what it last told us, and admit it when
        -- it has told us nothing rather than answering with a default.
        local value = ClientSettings.serverValues[key]
        if value == nil then
            return false, "not_received"
        end
        return value
    end
    local value = ClientSettings.values[key]
    if value == nil then
        return definition.default
    end
    return value
end

function ClientSettings.set(key, value)
    local writeKind, writeReason = schema().writeKind(SIDE, key)
    if not writeKind then
        if writeReason == "unknown_setting" then
            return false, "settings.error.unknown"
        end
        return false, writeReason
    end
    if writeKind ~= "authority" then
        -- The connection override is written through the connection settings,
        -- which are the server's file to publish.
        return false, "not_a_stored_setting"
    end
    local valid, invalidReason = schema().validate(key, value)
    if not valid then
        return false, invalidReason
    end

    local previous = ClientSettings.values[key]
    ClientSettings.values[key] = schema().normalize(key, value)
    local written, writeError = writeStored(ClientSettings.values)
    if not written then
        ClientSettings.values[key] = previous
        return false, writeError
    end
    ClientSettings.apply()
    return true
end

--- Every setting this side owns, for a caller that wants them all.
function ClientSettings.all()
    local snapshot = {}
    for key in pairs(schema().schema) do
        if isOwned(key) then
            snapshot[key] = ClientSettings.get(key)
        end
    end
    return snapshot
end

addEvent(SETTINGS_EVENT, true)
addEventHandler(SETTINGS_EVENT, resourceRoot, function(values)
    ClientSettings.receiveServerSettings(values)
end)

addEventHandler("onClientResourceStart", resourceRoot, function()
    ClientSettings.load()
end)

ANKIGTA.ClientSettings = ClientSettings

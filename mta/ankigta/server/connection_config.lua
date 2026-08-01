ANKIGTA = ANKIGTA or {}

local CURRENT_PATH = "connection.json"
local LAST_KNOWN_GOOD_PATH = "connection.last-known-good.json"
local MANUAL_PATH = "connection-manual.json"
local MANUAL_CANDIDATE_PATH = "connection-manual.json.tmp"
local CONNECTION_FORMAT = "ankigta-connection"
local CONNECTION_FORMAT_VERSION = 1
local PROTOCOL_NAME = "ankigta-control"
local PROTOCOL_VERSION = 1

local ConnectionConfig = {}

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
        return false, "missing"
    end
    local handle = fileOpen(path, true)
    if not handle then
        return false, "unreadable"
    end
    local contents = fileRead(handle, fileGetSize(handle))
    fileClose(handle)
    local decoded = decodeJson(contents)
    if type(decoded) ~= "table" then
        return false, "invalid_json"
    end
    return decoded
end

-- This side of the connection. The MTA server is one override holder; the
-- companion add-on is the other, and its manual values are what this side has
-- to agree with rather than adopt.
local OVERRIDE_SIDE = "server"

-- Range, step and type all come from the shared schema. A second copy of
-- "1 to 65535" here is a copy that will one day disagree with the one the UI
-- shows.
local function portRejection(port)
    if type(port) ~= "number" then
        -- A published or stored port that is not a number is a malformed file,
        -- not a value to coerce.
        return "settings.error.not_a_number"
    end
    local ok, reason = ANKIGTA.Settings.validate("connectionPort", port)
    if ok then
        return false
    end
    return reason
end

local function validPort(port)
    return portRejection(port) == false
end

local function validTokenDigest(digest)
    return type(digest) == "string"
        and string.len(digest) == 64
        and string.match(digest, "^[0-9a-f]+$") ~= nil
end

local function validatePublished(value)
    if type(value) ~= "table"
        or value.format ~= CONNECTION_FORMAT
        or value.formatVersion ~= CONNECTION_FORMAT_VERSION
        or value.protocol ~= PROTOCOL_NAME
        or value.protocolVersion ~= PROTOCOL_VERSION
        or value.host ~= "127.0.0.1"
        or type(value.revision) ~= "number"
        or value.revision ~= math.floor(value.revision)
        or value.revision < 1
        or type(value.automatic) ~= "table"
        or not validPort(value.automatic.port)
        or type(value.automatic.token) ~= "string"
        or type(value.companion) ~= "table"
    then
        return false
    end
    if value.companion.mode == "automatic" then
        return true
    end
    return value.companion.mode == "manual"
        and validPort(value.companion.port)
        and validTokenDigest(value.companion.tokenDigest)
end

--- Is this a manual override this side may act on?
--
-- Returns `true`, or `false` plus the reason. The reason matters: a file this
-- side simply did not write is a different problem from a corrupt one.
local function validateManual(value)
    if type(value) ~= "table"
        or value.format ~= "ankigta-mta-connection-settings"
        or value.formatVersion ~= 1
    then
        return false, "manual_connection_config_invalid"
    end
    if value.mode == "automatic" then
        return true
    end
    if value.mode ~= "manual" then
        return false, "manual_connection_config_invalid"
    end
    if not ANKIGTA.Settings.overrideAppliesTo(
        OVERRIDE_SIDE,
        {side = value.overrideSide}
    ) then
        return false, "foreign_manual_connection_override"
    end
    local portReason = portRejection(value.port)
    if portReason then
        return false, portReason
    end
    if not ANKIGTA.Settings.validate("connectionToken", value.token) then
        return false, "settings.error.not_a_string"
    end
    return true
end

local function loadPublished()
    local current = readJson(CURRENT_PATH)
    if validatePublished(current) then
        return current, false
    end
    local previous = readJson(LAST_KNOWN_GOOD_PATH)
    if validatePublished(previous) then
        return previous, "connection_config_rollback"
    end
    return false, "connection_config_invalid"
end

local function loadManual()
    if not fileExists(MANUAL_PATH) then
        return {
            format = "ankigta-mta-connection-settings",
            formatVersion = 1,
            mode = "automatic",
        }
    end
    local manual = readJson(MANUAL_PATH)
    local ok, reason = validateManual(manual)
    if not ok then
        return false, reason
    end
    return manual
end

local function effectiveTokenDigest(token)
    return hash("sha256", token)
end

function ConnectionConfig.loadEffective()
    local published, warning = loadPublished()
    if not published then
        return false, warning
    end
    local manual, manualError = loadManual()
    if not manual then
        return false, manualError
    end

    local localMode = manual.mode
    local port = published.automatic.port
    local token = published.automatic.token
    if localMode == "manual" then
        port = manual.port
        token = manual.token
    end

    local expectedMode = published.companion.mode
    local expectedPort = published.automatic.port
    local expectedTokenDigest = effectiveTokenDigest(
        published.automatic.token
    )
    if expectedMode == "manual" then
        expectedPort = published.companion.port
        expectedTokenDigest = published.companion.tokenDigest
    end

    if port ~= expectedPort
        or effectiveTokenDigest(token) ~= expectedTokenDigest
    then
        return false, "effective_config_mismatch", {
            localMode = localMode,
            companionMode = expectedMode,
            localPort = port,
            companionPort = expectedPort,
            tokenConfigured = token ~= "",
        }
    end

    return {
        port = port,
        token = token,
        revision = published.revision,
        localMode = localMode,
        companionMode = expectedMode,
        tokenConfigured = token ~= "",
        tokenDisabled = token == "",
        signature = string.format(
            "%d:%s:%d:%s",
            published.revision,
            localMode,
            port,
            effectiveTokenDigest(token)
        ),
    }, false, warning
end

local function writeManual(value)
    local valid, invalidReason = validateManual(value)
    if not valid then
        return false, invalidReason
    end
    local encoded = encodeJson(value)
    if not encoded then
        return false, "manual_json_encode_failed"
    end
    if fileExists(MANUAL_CANDIDATE_PATH) then
        fileDelete(MANUAL_CANDIDATE_PATH)
    end
    local handle = fileCreate(MANUAL_CANDIDATE_PATH)
    if not handle then
        return false, "manual_write_failed"
    end
    fileWrite(handle, encoded)
    fileFlush(handle)
    fileClose(handle)
    local candidate = readJson(MANUAL_CANDIDATE_PATH)
    if not validateManual(candidate) then
        fileDelete(MANUAL_CANDIDATE_PATH)
        return false, "manual_validation_failed"
    end
    if fileExists(MANUAL_PATH) and not fileDelete(MANUAL_PATH) then
        fileDelete(MANUAL_CANDIDATE_PATH)
        return false, "manual_replace_failed"
    end
    if not fileRename(MANUAL_CANDIDATE_PATH, MANUAL_PATH) then
        return false, "manual_replace_failed"
    end
    return true
end

function ConnectionConfig.setManual(port, token, keepExistingToken)
    if keepExistingToken then
        local published, publishedError = loadPublished()
        if not published then
            return false, publishedError
        end
        local manual, manualError = loadManual()
        if not manual then
            return false, manualError
        end
        if manual.mode == "manual" then
            token = manual.token
        else
            token = published.automatic.token
        end
    end
    local portOverride, portReason = ANKIGTA.Settings.overrideBy(
        OVERRIDE_SIDE,
        "connectionPort",
        port
    )
    if not portOverride then
        return false, portReason
    end
    local tokenOverride, tokenReason = ANKIGTA.Settings.overrideBy(
        OVERRIDE_SIDE,
        "connectionToken",
        token
    )
    if not tokenOverride then
        return false, tokenReason
    end
    return writeManual({
        format = "ankigta-mta-connection-settings",
        formatVersion = 1,
        mode = "manual",
        port = portOverride.value,
        token = tokenOverride.value,
        -- Stamped, so the side that reads it back can tell whether it is its
        -- own override or someone else's.
        overrideSide = portOverride.side,
    })
end

function ConnectionConfig.useAutomatic()
    return writeManual({
        format = "ankigta-mta-connection-settings",
        formatVersion = 1,
        mode = "automatic",
    })
end

function ConnectionConfig.getSanitizedStatus()
    local effective, category, warningOrDetails = ConnectionConfig.loadEffective()
    if not effective then
        return {
            valid = false,
            category = category,
            details = warningOrDetails or false,
        }
    end
    return {
        valid = true,
        mode = effective.localMode,
        companionMode = effective.companionMode,
        port = effective.port,
        tokenConfigured = effective.tokenConfigured,
        tokenDisabled = effective.tokenDisabled,
        warningCategory = warningOrDetails or false,
    }
end

ANKIGTA.ConnectionConfig = ConnectionConfig

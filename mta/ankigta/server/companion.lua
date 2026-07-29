ANKIGTA = ANKIGTA or {}

local PROTOCOL_NAME = "ankigta-control"
local PROTOCOL_VERSION = 1
local HEALTH_PATH = "/v1/health"
local REQUEST_TIMEOUT_MS = 4900
local AUTO_RECONNECT_INTERVAL_MS = 2000
local STUDY_RIGHT = "resource.ankigta.study"
local CONNECT_EVENT = "ankigta:connectCompanion"
local SETTINGS_REQUEST_EVENT = "ankigta:requestConnectionSettings"
local SETTINGS_SNAPSHOT_EVENT = "ankigta:connectionSettingsSnapshot"
local SETTINGS_UPDATE_EVENT = "ankigta:updateConnectionSettings"

local Gateway = {
    generation = 0,
    pending = {},
    quarantinedCallbacks = 0,
    autoReconnectTimer = false,
    status = {
        state = "disconnected",
        category = false,
        requestId = false,
        httpStatus = false,
        warningCategory = false,
        config = false,
        study = {
            sessionActive = false,
            filteredDeckCreated = false,
            reviewModeOpened = false,
        },
    },
}

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

local function responseContentType(headers)
    if type(headers) ~= "table" then
        return false
    end
    for name, value in pairs(headers) do
        if string.lower(tostring(name)) == "content-type" then
            return string.lower(tostring(value))
        end
    end
    return false
end

local function isJsonContentType(headers)
    local contentType = responseContentType(headers)
    if not contentType then
        return false
    end
    local mediaType = string.match(contentType, "^%s*([^;]+)")
    if not mediaType then
        return false
    end
    mediaType = string.match(mediaType, "^%s*(.-)%s*$")
    return mediaType == "application/json"
end

local function validHealthPayload(payload)
    if type(payload) ~= "table"
        or type(payload.anki) ~= "table"
        or type(payload.anki.version) ~= "string"
        or payload.anki.version == ""
        or type(payload.anki.v3Scheduler) ~= "boolean"
        or type(payload.anki.fsrsEnabled) ~= "boolean"
        or type(payload.collection) ~= "table"
        or type(payload.collection.state) ~= "string"
        or type(payload.compatibility) ~= "table"
        or type(payload.compatibility.status) ~= "string"
        or type(payload.compatibility.previewReadOnlyCompatible) ~= "boolean"
        or type(payload.compatibility.sessionCompatible) ~= "boolean"
        or type(payload.compatibility.ratingCompatible) ~= "boolean"
        or type(payload.study) ~= "table"
        or payload.study.sessionActive ~= false
        or payload.study.ratingEnabled ~= false
    then
        return false
    end
    local validCollectionState = payload.collection.state == "open"
        or payload.collection.state == "absent"
        or payload.collection.state == "closing"
    local compatibility = payload.compatibility
    local validCompatibility = (
        compatibility.status == "supported"
        and compatibility.previewReadOnlyCompatible == true
        and compatibility.sessionCompatible == true
        and compatibility.ratingCompatible == true
    ) or (
        compatibility.status == "unsupported"
        and compatibility.previewReadOnlyCompatible == true
        and compatibility.sessionCompatible == false
        and compatibility.ratingCompatible == false
    )
    return validCollectionState and validCompatibility
end

local function validHealthEnvelope(response, expectedRequestId)
    if type(response) ~= "table"
        or response.protocol ~= PROTOCOL_NAME
        or response.protocolVersion ~= PROTOCOL_VERSION
        or response.requestId ~= expectedRequestId
        or type(response.ok) ~= "boolean"
    then
        return false
    end

    if response.ok then
        return validHealthPayload(response.payload)
            and (response.error == nil or response.error == false)
            and response.payload.collection.state == "open"
            and response.payload.compatibility.status == "supported"
    end

    if type(response.error) ~= "table"
        or type(response.error.category) ~= "string"
        or response.error.category == ""
        or type(response.error.message) ~= "string"
        or response.error.message == ""
    then
        return false
    end
    if response.error.category == "authorization_failure" then
        return response.payload == nil or response.payload == false
    end
    if not validHealthPayload(response.payload) then
        return false
    end
    if response.error.category == "collection_unavailable" then
        return response.payload.collection.state ~= "open"
    end
    if response.error.category == "compatibility_failure" then
        return response.payload.collection.state == "open"
            and response.payload.compatibility.status == "unsupported"
    end
    return false
end

local function canPresentTo(player)
    return isElement(player)
        and getElementType(player) == "player"
        and hasObjectPermissionTo(player, STUDY_RIGHT, false)
end

local function presentStatus(player)
    if canPresentTo(player) then
        triggerClientEvent(
            player,
            "ankigta:companionStatus",
            resourceRoot,
            Gateway.status
        )
        return
    end
    for _, candidate in ipairs(getElementsByType("player")) do
        if canPresentTo(candidate) then
            triggerClientEvent(
                candidate,
                "ankigta:companionStatus",
                resourceRoot,
                Gateway.status
            )
        end
    end
end

local function setStatus(request, state, category, httpStatus)
    local previous = Gateway.status
    local context = request.configContext or {}
    local warningCategory = context.warningCategory or false
    local changed = previous.state ~= state
        or previous.category ~= (category or false)
        or previous.warningCategory ~= warningCategory
    Gateway.status = {
        state = state,
        category = category or false,
        requestId = request.requestId,
        httpStatus = httpStatus or false,
        warningCategory = warningCategory,
        config = context.sanitized or false,
        elapsedMs = getTickCount() - request.startedAt,
        study = {
            sessionActive = false,
            filteredDeckCreated = false,
            reviewModeOpened = false,
        },
    }
    if changed then
        outputDebugString(
            string.format(
                "[ANKIGTA] companion_health requestId=%s state=%s category=%s httpStatus=%s warning=%s",
                request.requestId,
                state,
                tostring(category or false),
                tostring(httpStatus or false),
                tostring(warningCategory)
            )
        )
        presentStatus(request.player)
    end
end

local function settle(request, state, category, httpStatus)
    if request.settled then
        Gateway.quarantinedCallbacks = Gateway.quarantinedCallbacks + 1
        return false
    end

    request.settled = true
    if isTimer(request.timeoutTimer) then
        killTimer(request.timeoutTimer)
    end
    Gateway.pending[request.requestId] = nil
    setStatus(request, state, category, httpStatus)
    return true
end

local function timeoutRequest(requestId, generation)
    local request = Gateway.pending[requestId]
    if not request or request.generation ~= generation or request.settled then
        return
    end
    local handle = request.handle
    settle(request, "disconnected", "timeout", false)
    if handle then
        abortRemoteRequest(handle)
    end
end

local function healthCallback(body, info, requestId, generation)
    local request = Gateway.pending[requestId]
    if not request or request.generation ~= generation or request.settled then
        Gateway.quarantinedCallbacks = Gateway.quarantinedCallbacks + 1
        return
    end

    local httpStatus = type(info) == "table"
        and tonumber(info.statusCode)
        or false
    if type(info) ~= "table"
        or not httpStatus
        or httpStatus < 100
        or httpStatus > 599
    then
        settle(request, "disconnected", "transport_error", httpStatus)
        return
    end
    if not isJsonContentType(info.headers) then
        settle(request, "disconnected", "protocol_error", httpStatus)
        return
    end

    local response = decodeJson(body)
    if not validHealthEnvelope(response, requestId) then
        settle(request, "disconnected", "protocol_error", httpStatus)
        return
    end
    if httpStatus ~= 200 or response.ok ~= true then
        local category = response.error
            and response.error.category
            or "http_error"
        settle(request, "disconnected", category, httpStatus)
        return
    end

    settle(request, "connected", false, httpStatus)
end

local function validPort(port)
    return type(port) == "number"
        and port == math.floor(port)
        and port >= 1
        and port <= 65535
end

local function nextRequestId()
    Gateway.generation = Gateway.generation + 1
    return string.format(
        "health-%d-%d",
        getTickCount(),
        Gateway.generation
    )
end

function Gateway.requestHealth(
    port,
    requestId,
    player,
    token,
    configContext,
    silentConnecting
)
    if not validPort(port) then
        return false, "invalid_port"
    end
    if requestId == nil then
        requestId = nextRequestId()
    elseif type(requestId) ~= "string" or requestId == "" then
        return false, "invalid_request_id"
    end
    if Gateway.pending[requestId] then
        return false, "request_in_flight"
    end

    Gateway.generation = Gateway.generation + 1
    local request = {
        requestId = requestId,
        generation = Gateway.generation,
        startedAt = getTickCount(),
        player = player,
        settled = false,
        handle = false,
        timeoutTimer = false,
        configContext = configContext or false,
    }
    Gateway.pending[requestId] = request
    if not silentConnecting then
        setStatus(request, "connecting", false, false)
    end

    local envelope = encodeJson({
        protocol = PROTOCOL_NAME,
        protocolVersion = PROTOCOL_VERSION,
        requestId = requestId,
    })
    if not envelope then
        settle(request, "disconnected", "protocol_error", false)
        return false, "json_encode_failed"
    end

    request.timeoutTimer = setTimer(
        timeoutRequest,
        REQUEST_TIMEOUT_MS,
        1,
        requestId,
        request.generation
    )
    local headers = {
        ["Accept"] = "application/json",
        ["Content-Type"] = "application/json; charset=utf-8",
    }
    if type(token) == "string" and token ~= "" then
        headers["Authorization"] = "Bearer " .. token
    end
    request.handle = fetchRemote(
        string.format(
            "http://127.0.0.1:%d%s",
            port,
            HEALTH_PATH
        ),
        {
            method = "POST",
            postData = envelope,
            postIsBinary = false,
            headers = headers,
            queueName = "ankigta-health",
            connectionAttempts = 1,
            connectTimeout = 4000,
            maxRedirects = 0,
        },
        healthCallback,
        {
            requestId,
            request.generation,
        }
    )
    if not request.handle then
        settle(request, "disconnected", "transport_error", false)
        return false, "fetch_rejected"
    end
    return true, requestId
end

local function sanitizedConfig(effective, warningCategory)
    return {
        mode = effective.localMode,
        companionMode = effective.companionMode,
        port = effective.port,
        tokenConfigured = effective.tokenConfigured,
        tokenDisabled = effective.tokenDisabled,
        warningCategory = warningCategory or false,
    }
end

local function syntheticConfigFailure(player, category, details)
    local request = {
        requestId = nextRequestId(),
        startedAt = getTickCount(),
        player = player,
        configContext = {
            sanitized = details or false,
        },
    }
    setStatus(request, "disconnected", category, false)
end

function Gateway.connectConfigured(player, immediate)
    for _ in pairs(Gateway.pending) do
        return false, "request_in_flight"
    end
    local effective, category, warningCategory =
        ANKIGTA.ConnectionConfig.loadEffective()
    if not effective then
        syntheticConfigFailure(player, category, warningCategory)
        return false, category
    end

    local context = {
        warningCategory = warningCategory
            or (effective.tokenDisabled and "empty_token" or false),
        sanitized = sanitizedConfig(effective, warningCategory),
    }
    local silent = immediate ~= true
    return Gateway.requestHealth(
        effective.port,
        nil,
        player,
        effective.token,
        context,
        silent
    )
end

function Gateway.getStatus()
    local result = {}
    for key, value in pairs(Gateway.status) do
        result[key] = value
    end
    result.quarantinedCallbacks = Gateway.quarantinedCallbacks
    return result
end

local function sendSettingsSnapshot(player)
    if not canPresentTo(player) then
        return
    end
    triggerClientEvent(
        player,
        SETTINGS_SNAPSHOT_EVENT,
        resourceRoot,
        ANKIGTA.ConnectionConfig.getSanitizedStatus()
    )
end

addEvent(CONNECT_EVENT, true)
addEventHandler(CONNECT_EVENT, resourceRoot, function()
    if client and source == resourceRoot and canPresentTo(client) then
        Gateway.connectConfigured(client, true)
    end
end)

addEvent(SETTINGS_REQUEST_EVENT, true)
addEventHandler(SETTINGS_REQUEST_EVENT, resourceRoot, function()
    if client and source == resourceRoot then
        sendSettingsSnapshot(client)
    end
end)

addEvent(SETTINGS_UPDATE_EVENT, true)
addEventHandler(SETTINGS_UPDATE_EVENT, resourceRoot, function(update)
    if not client
        or source ~= resourceRoot
        or not canPresentTo(client)
        or type(update) ~= "table"
    then
        return
    end
    local changed, changeError = false, "invalid_manual_connection"
    if update.mode == "automatic" then
        changed, changeError = ANKIGTA.ConnectionConfig.useAutomatic()
    elseif update.mode == "manual" then
        changed, changeError = ANKIGTA.ConnectionConfig.setManual(
            update.port,
            update.token,
            update.keepToken == true
        )
    end
    if not changed then
        syntheticConfigFailure(client, changeError, false)
        sendSettingsSnapshot(client)
        return
    end
    sendSettingsSnapshot(client)
    Gateway.connectConfigured(client, true)
end)

addEventHandler("onResourceStart", resourceRoot, function()
    setTimer(function()
        Gateway.connectConfigured(false, false)
    end, 100, 1)
    Gateway.autoReconnectTimer = setTimer(function()
        Gateway.connectConfigured(false, false)
    end, AUTO_RECONNECT_INTERVAL_MS, 0)
end)

addEventHandler("onPlayerLogin", root, function()
    local player = source
    setTimer(function()
        presentStatus(player)
    end, 100, 1)
end)

function requestCompanionHealth(_port, _requestId, player)
    return Gateway.connectConfigured(player, true)
end

function connectCompanion(player)
    return Gateway.connectConfigured(player, true)
end

function getCompanionConnectionStatus()
    return Gateway.getStatus()
end

ANKIGTA.CompanionGateway = Gateway

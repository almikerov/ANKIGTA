ANKIGTA = ANKIGTA or {}

local PROTOCOL_NAME = "ankigta-control"
local PROTOCOL_VERSION = 1
local HEALTH_PATH = "/v1/health"
local REQUEST_TIMEOUT_MS = 4900
local LATE_CALLBACK_GRACE_MS = 500
local STUDY_RIGHT = "resource.ankigta.study"

local Gateway = {
    generation = 0,
    pending = {},
    quarantinedCallbacks = 0,
    status = {
        state = "disconnected",
        category = false,
        requestId = false,
        httpStatus = false,
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
    return payload.collection.state == "open"
        or payload.collection.state == "absent"
        or payload.collection.state == "closing"
end

local function validHealthEnvelope(response, expectedRequestId)
    if type(response) ~= "table"
        or response.protocol ~= PROTOCOL_NAME
        or response.protocolVersion ~= PROTOCOL_VERSION
        or response.requestId ~= expectedRequestId
        or type(response.ok) ~= "boolean"
        or not validHealthPayload(response.payload)
    then
        return false
    end

    if response.ok then
        return response.payload.collection.state == "open"
            and response.payload.compatibility.status == "supported"
    end

    return type(response.error) == "table"
        and type(response.error.category) == "string"
        and type(response.payload) == "table"
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
    end
end

local function setStatus(request, state, category, httpStatus)
    Gateway.status = {
        state = state,
        category = category or false,
        requestId = request.requestId,
        httpStatus = httpStatus or false,
        elapsedMs = getTickCount() - request.startedAt,
        study = {
            sessionActive = false,
            filteredDeckCreated = false,
            reviewModeOpened = false,
        },
    }
    outputDebugString(
        string.format(
            "[ANKIGTA] companion_health requestId=%s state=%s category=%s httpStatus=%s",
            request.requestId,
            state,
            tostring(category or false),
            tostring(httpStatus or false)
        )
    )
    presentStatus(request.player)
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
        setTimer(function(requestHandle)
            if getRemoteRequestInfo(requestHandle) then
                abortRemoteRequest(requestHandle)
            end
        end, LATE_CALLBACK_GRACE_MS, 1, handle)
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
    if type(info) ~= "table" or info.success ~= true or not httpStatus then
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

function Gateway.requestHealth(port, requestId, player)
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
    }
    Gateway.pending[requestId] = request
    setStatus(request, "connecting", false, false)

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
            headers = {
                ["Accept"] = "application/json",
                ["Content-Type"] = "application/json; charset=utf-8",
            },
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

function Gateway.getStatus()
    local result = {}
    for key, value in pairs(Gateway.status) do
        result[key] = value
    end
    result.quarantinedCallbacks = Gateway.quarantinedCallbacks
    return result
end

function requestCompanionHealth(port, requestId, player)
    return Gateway.requestHealth(port, requestId, player)
end

function getCompanionConnectionStatus()
    return Gateway.getStatus()
end

ANKIGTA.CompanionGateway = Gateway

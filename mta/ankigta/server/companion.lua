ANKIGTA = ANKIGTA or {}

local PROTOCOL_NAME = "ankigta-control"
local PROTOCOL_VERSION = 1
local HEALTH_PATH = "/v1/health"
local CARD_SEARCH_PATH = "/v1/cards/search"
local CARD_READ_PATH = "/v1/cards/read"
local CARD_STATE_REFRESHED_EVENT = "ankigta:cardStateRefreshed"
local SESSION_START_PATH = "/v1/session/start"
local SESSION_REBUILD_PATH = "/v1/session/rebuild"
local SESSION_PAUSE_PATH = "/v1/session/pause"
local SESSION_STOP_PATH = "/v1/session/stop"
local SESSION_CANCEL_PATH = "/v1/session/cancel"
local CARD_PICKER_SNAPSHOT_EVENT = "ankigta:cardPickerSnapshot"
local REQUEST_TIMEOUT_MS = 4900
local SESSION_TIMEOUT_MS = 30000
local AUTO_RECONNECT_INTERVAL_MS = 2000
local STUDY_RIGHT = "resource.ankigta.study"
local CONNECT_EVENT = "ankigta:connectCompanion"
local SETTINGS_REQUEST_EVENT = "ankigta:requestConnectionSettings"
local SETTINGS_SNAPSHOT_EVENT = "ankigta:connectionSettingsSnapshot"
local SETTINGS_UPDATE_EVENT = "ankigta:updateConnectionSettings"
local validPort

local Gateway = {
    generation = 0,
    pending = {},
    quarantinedCallbacks = 0,
    cardGeneration = 0,
    cardPending = {},
    cardStateGeneration = 0,
    cardStatePending = {},
    sessionGeneration = 0,
    sessionPending = {},
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
        or type(payload.study.sessionActive) ~= "boolean"
        or type(payload.study.ratingEnabled) ~= "boolean"
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
    local study = request.study or previous.study
    local changed = previous.state ~= state
        or previous.category ~= (category or false)
        or previous.warningCategory ~= warningCategory
        or toJSON(previous.study, true) ~= toJSON(study, true)
    Gateway.status = {
        state = state,
        category = category or false,
        requestId = request.requestId,
        httpStatus = httpStatus or false,
        warningCategory = warningCategory,
        config = context.sanitized or false,
        elapsedMs = getTickCount() - request.startedAt,
        study = study,
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
    if response.ok == true
        and type(response.payload) == "table"
        and type(response.payload.study) == "table"
    then
        request.study = response.payload.study
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

local function nextSessionRequestId()
    Gateway.sessionGeneration = Gateway.sessionGeneration + 1
    return string.format(
        "session-%d-%d",
        getTickCount(),
        Gateway.sessionGeneration
    )
end

local function sessionTimeout(requestId, generation)
    local request = Gateway.sessionPending[requestId]
    if not request
        or request.generation ~= generation
        or request.settled
    then
        return
    end
    local handle = request.handle
    request.settled = true
    Gateway.sessionPending[requestId] = nil
    if isTimer(request.timeoutTimer) then
        killTimer(request.timeoutTimer)
    end
    setStatus(request, "disconnected", "timeout", false)
    if handle then
        abortRemoteRequest(handle)
    end
end

local function sessionCallback(body, info, requestId, generation)
    local request = Gateway.sessionPending[requestId]
    if not request
        or request.generation ~= generation
        or request.settled
    then
        Gateway.quarantinedCallbacks = Gateway.quarantinedCallbacks + 1
        return
    end
    request.settled = true
    Gateway.sessionPending[requestId] = nil
    if isTimer(request.timeoutTimer) then
        killTimer(request.timeoutTimer)
    end
    local httpStatus = type(info) == "table"
        and tonumber(info.statusCode)
        or false
    local response = decodeJson(body)
    if type(info) ~= "table"
        or httpStatus ~= 200
        or not isJsonContentType(info.headers)
        or type(response) ~= "table"
        or response.protocol ~= PROTOCOL_NAME
        or response.protocolVersion ~= PROTOCOL_VERSION
        or response.requestId ~= requestId
        or response.ok ~= true
        or type(response.payload) ~= "table"
        or type(response.payload.session) ~= "table"
    then
        local category = type(response) == "table"
            and type(response.error) == "table"
            and response.error.category
            or "protocol_error"
        setStatus(request, "disconnected", category, httpStatus)
        return
    end
    request.study = response.payload.session
    setStatus(request, "connected", false, httpStatus)
end

function Gateway.requestSession(player, path, payload, token, configContext)
    for _ in pairs(Gateway.pending) do
        return false, "request_in_flight"
    end
    for _ in pairs(Gateway.sessionPending) do
        return false, "request_in_flight"
    end
    if not validPort(tonumber(configContext.port)) then
        return false, "invalid_port"
    end
    local requestId = nextSessionRequestId()
    local request = {
        requestId = requestId,
        generation = Gateway.sessionGeneration,
        startedAt = getTickCount(),
        player = player,
        configContext = configContext,
        settled = false,
        handle = false,
    }
    Gateway.sessionPending[requestId] = request
    request.timeoutTimer = setTimer(
        sessionTimeout,
        SESSION_TIMEOUT_MS,
        1,
        requestId,
        request.generation
    )
    local envelope = encodeJson({
        protocol = PROTOCOL_NAME,
        protocolVersion = PROTOCOL_VERSION,
        requestId = requestId,
        cardIdentities = payload.cardIdentities,
        allowEarlyReview = payload.allowEarlyReview == true,
    })
    if path == SESSION_PAUSE_PATH
        or path == SESSION_STOP_PATH
        or path == SESSION_CANCEL_PATH
    then
        envelope = encodeJson({
            protocol = PROTOCOL_NAME,
            protocolVersion = PROTOCOL_VERSION,
            requestId = requestId,
        })
    end
    if not envelope then
        sessionTimeout(requestId, request.generation)
        return false, "json_encode_failed"
    end
    local headers = {
        ["Accept"] = "application/json",
        ["Content-Type"] = "application/json; charset=utf-8",
    }
    if type(token) == "string" and token ~= "" then
        headers["Authorization"] = "Bearer " .. token
    end
    request.handle = fetchRemote(
        string.format("http://127.0.0.1:%d%s", configContext.port, path),
        {
            method = "POST",
            postData = envelope,
            postIsBinary = false,
            headers = headers,
            queueName = "ankigta-session",
            connectionAttempts = 1,
            connectTimeout = SESSION_TIMEOUT_MS,
            maxRedirects = 0,
        },
        sessionCallback,
        { requestId, generation = request.generation }
    )
    if not request.handle then
        sessionTimeout(requestId, request.generation)
        return false, "fetch_rejected"
    end
    return true, requestId
end

local function requestSessionWithConfig(player, path, payload)
    local effective, category, warningCategory =
        ANKIGTA.ConnectionConfig.loadEffective()
    if not effective then
        return false, category
    end
    local context = {
        port = effective.port,
        warningCategory = warningCategory or false,
        sanitized = false,
    }
    return Gateway.requestSession(
        player,
        path,
        payload or {},
        effective.token,
        context
    )
end

function Gateway.requestSessionStart(player, identities, allowEarlyReview)
    return requestSessionWithConfig(
        player,
        SESSION_START_PATH,
        {
            cardIdentities = identities or {},
            allowEarlyReview = allowEarlyReview == true,
        }
    )
end

function Gateway.requestSessionRebuild(player, identities, allowEarlyReview)
    return requestSessionWithConfig(
        player,
        SESSION_REBUILD_PATH,
        {
            cardIdentities = identities or {},
            allowEarlyReview = allowEarlyReview == true,
        }
    )
end

function Gateway.requestSessionPause(player)
    return requestSessionWithConfig(player, SESSION_PAUSE_PATH, {})
end

function Gateway.requestSessionStop(player)
    return requestSessionWithConfig(player, SESSION_STOP_PATH, {})
end

function Gateway.requestSessionCancel(player)
    return requestSessionWithConfig(player, SESSION_CANCEL_PATH, {})
end

validPort = function(port)
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

local function cardPickerFailure(player, category)
    if isElement(player) then
        triggerClientEvent(
            player,
            "ankigta:pendingMapSaveNotice",
            resourceRoot,
            "Card Picker unavailable: " .. tostring(category),
            category
        )
    end
end

local function cardStateFailure(player, category)
    if isElement(player) then
        triggerClientEvent(
            player,
            "ankigta:pendingMapSaveNotice",
            resourceRoot,
            "Card state refresh unavailable: " .. tostring(category),
            category
        )
    end
end

local function validCardView(card)
    if type(card) ~= "table"
        or type(card.identity) ~= "table"
        or type(card.identity.collectionUuid) ~= "string"
        or card.identity.collectionUuid == ""
        or type(card.identity.cardId) ~= "number"
        or card.identity.cardId <= 0
        or card.identity.cardId ~= math.floor(card.identity.cardId)
        or type(card.deck) ~= "table"
        or type(card.deck.id) ~= "number"
        or card.deck.id ~= math.floor(card.deck.id)
        or (card.deck.name ~= false and type(card.deck.name) ~= "string")
        or type(card.state) ~= "string"
        or (
            card.state ~= "new"
            and card.state ~= "learning"
            and card.state ~= "review"
            and card.state ~= "not_due"
            and card.state ~= "suspended"
            and card.state ~= "buried"
        )
        or type(card.due) ~= "number"
        or card.due ~= math.floor(card.due)
        or type(card.tags) ~= "table"
    then
        return false
    end
    for _, tag in ipairs(card.tags) do
        if type(tag) ~= "string" then
            return false
        end
    end
    return true
end

local function validCardPickerPayload(payload)
    if type(payload) ~= "table"
        or type(payload.cards) ~= "table"
        or type(payload.page) ~= "number"
        or payload.page ~= math.floor(payload.page)
        or payload.page < 0
        or type(payload.pageSize) ~= "number"
        or payload.pageSize ~= math.floor(payload.pageSize)
        or payload.pageSize < 1
        or type(payload.total) ~= "number"
        or payload.total ~= math.floor(payload.total)
        or payload.total < 0
        or type(payload.query) ~= "string"
        or (payload.deckFilter ~= false and type(payload.deckFilter) ~= "string")
    then
        return false
    end
    for _, card in ipairs(payload.cards) do
        if not validCardView(card) then
            return false
        end
    end
    return true
end

local function validCardReadPayload(payload)
    return type(payload) == "table"
        and validCardView(payload.card)
end

local function timeoutCardState(requestId, generation)
    local request = Gateway.cardStatePending[requestId]
    if not request
        or request.generation ~= generation
        or request.settled
    then
        return
    end
    request.settled = true
    Gateway.cardStatePending[requestId] = nil
    if request.handle then
        abortRemoteRequest(request.handle)
    end
    cardStateFailure(request.player, "timeout")
end

local function cardStateCallback(body, info, requestId, generation)
    local request = Gateway.cardStatePending[requestId]
    if not request
        or request.generation ~= generation
        or request.settled
    then
        Gateway.quarantinedCallbacks = Gateway.quarantinedCallbacks + 1
        return
    end
    request.settled = true
    Gateway.cardStatePending[requestId] = nil
    local httpStatus = type(info) == "table"
        and tonumber(info.statusCode)
        or false
    if type(info) ~= "table"
        or not isJsonContentType(info.headers)
        or (httpStatus ~= 200 and httpStatus ~= 404)
    then
        cardStateFailure(request.player, "protocol_error")
        return
    end
    local response = decodeJson(body)
    if type(response) ~= "table"
        or response.protocol ~= PROTOCOL_NAME
        or response.protocolVersion ~= PROTOCOL_VERSION
        or response.requestId ~= requestId
        or type(response.ok) ~= "boolean"
    then
        cardStateFailure(request.player, "protocol_error")
        return
    end
    local present = false
    if response.ok then
        if httpStatus ~= 200 or not validCardReadPayload(response.payload) then
            cardStateFailure(request.player, "protocol_error")
            return
        end
        present = true
    elseif not response.error
        or response.error.category ~= "card_missing"
        or httpStatus ~= 404
    then
        cardStateFailure(request.player, "protocol_error")
        return
    end
    local refreshed, changedOrError =
        ANKIGTA.Store.refreshSpatialLinkCardState(
            request.cardIdentity,
            present
        )
    if not refreshed then
        cardStateFailure(request.player, changedOrError)
        return
    end
    triggerEvent(
        CARD_STATE_REFRESHED_EVENT,
        resourceRoot,
        request.player,
        request.cardIdentity,
        present,
        changedOrError == true
    )
end

function Gateway.requestCardState(player, cardIdentity)
    if not canPresentTo(player) then
        return false, "forbidden"
    end
    if type(cardIdentity) ~= "table"
        or type(cardIdentity.collectionUuid) ~= "string"
        or cardIdentity.collectionUuid == ""
        or tonumber(cardIdentity.cardId) == nil
        or tonumber(cardIdentity.cardId) <= 0
    then
        return false, "invalid_anki_card_identity"
    end
    local effective, category = ANKIGTA.ConnectionConfig.loadEffective()
    if not effective then
        cardStateFailure(player, category)
        return false, category
    end
    Gateway.cardStateGeneration = Gateway.cardStateGeneration + 1
    local requestId = string.format(
        "card-state-%d-%d",
        getTickCount(),
        Gateway.cardStateGeneration
    )
    local request = {
        requestId = requestId,
        generation = Gateway.cardStateGeneration,
        player = player,
        cardIdentity = cardIdentity,
        settled = false,
        handle = false,
    }
    Gateway.cardStatePending[requestId] = request
    setTimer(
        timeoutCardState,
        REQUEST_TIMEOUT_MS,
        1,
        requestId,
        request.generation
    )
    local envelope = encodeJson({
        protocol = PROTOCOL_NAME,
        protocolVersion = PROTOCOL_VERSION,
        requestId = requestId,
        cardId = tonumber(cardIdentity.cardId),
    })
    if not envelope then
        request.settled = true
        Gateway.cardStatePending[requestId] = nil
        cardStateFailure(player, "protocol_error")
        return false, "json_encode_failed"
    end
    local headers = {
        ["Accept"] = "application/json",
        ["Content-Type"] = "application/json; charset=utf-8",
    }
    if type(effective.token) == "string" and effective.token ~= "" then
        headers["Authorization"] = "Bearer " .. effective.token
    end
    request.handle = fetchRemote(
        string.format(
            "http://127.0.0.1:%d%s",
            effective.port,
            CARD_READ_PATH
        ),
        {
            method = "POST",
            postData = envelope,
            postIsBinary = false,
            headers = headers,
            queueName = "ankigta-card-state",
            connectionAttempts = 1,
            connectTimeout = 4000,
            maxRedirects = 0,
        },
        cardStateCallback,
        {
            requestId,
            generation = request.generation,
        }
    )
    if not request.handle then
        request.settled = true
        Gateway.cardStatePending[requestId] = nil
        cardStateFailure(player, "transport_error")
        return false, "fetch_rejected"
    end
    return true, requestId
end

local function cardPickerCallback(body, info, requestId, generation)
    local request = Gateway.cardPending[requestId]
    if not request
        or request.generation ~= generation
        or request.settled
    then
        Gateway.quarantinedCallbacks = Gateway.quarantinedCallbacks + 1
        return
    end
    request.settled = true
    Gateway.cardPending[requestId] = nil
    local httpStatus = type(info) == "table"
        and tonumber(info.statusCode)
        or false
    if type(info) ~= "table"
        or httpStatus ~= 200
        or not isJsonContentType(info.headers)
    then
        cardPickerFailure(request.player, "protocol_error")
        return
    end
    local response = decodeJson(body)
    if type(response) ~= "table"
        or response.protocol ~= PROTOCOL_NAME
        or response.protocolVersion ~= PROTOCOL_VERSION
        or response.requestId ~= requestId
        or response.ok ~= true
        or (response.error ~= nil and response.error ~= false)
        or not validCardPickerPayload(response.payload)
    then
        cardPickerFailure(request.player, "protocol_error")
        return
    end
    local existingLinks = {}
    local rows = ANKIGTA.Store.listMapEntities()
    if type(rows) == "table" then
        for _, row in ipairs(rows) do
            if row.link_state == "active" or row.link_state == "card_missing" then
                table.insert(existingLinks, {
                    mapId = row.map_id,
                    entityId = row.entity_id,
                    collectionUuid = row.collection_uuid,
                    cardId = tonumber(row.card_id),
                })
            end
        end
    end
    response.payload.existingLinks = existingLinks
    triggerClientEvent(
        request.player,
        CARD_PICKER_SNAPSHOT_EVENT,
        resourceRoot,
        response.payload
    )
end

local function timeoutCardPicker(requestId, generation)
    local request = Gateway.cardPending[requestId]
    if not request
        or request.generation ~= generation
        or request.settled
    then
        return
    end
    request.settled = true
    Gateway.cardPending[requestId] = nil
    if request.handle then
        abortRemoteRequest(request.handle)
    end
    cardPickerFailure(request.player, "timeout")
end

function Gateway.requestCardPicker(
    player,
    query,
    deckFilter,
    page,
    pageSize
)
    if not canPresentTo(player) then
        return false, "forbidden"
    end
    if query == nil then
        query = ""
    elseif type(query) ~= "string" then
        return false, "invalid_query"
    end
    if deckFilter == nil or deckFilter == false then
        deckFilter = false
    elseif type(deckFilter) ~= "string" then
        return false, "invalid_deck_filter"
    end
    if page == nil then
        page = 0
    elseif type(page) ~= "number" or page ~= math.floor(page) or page < 0 then
        return false, "invalid_pagination"
    end
    if pageSize == nil then
        pageSize = 50
    elseif type(pageSize) ~= "number"
        or pageSize ~= math.floor(pageSize)
        or pageSize < 1
        or pageSize > 200
    then
        return false, "invalid_pagination"
    end
    local effective, category = ANKIGTA.ConnectionConfig.loadEffective()
    if not effective then
        cardPickerFailure(player, category)
        return false, category
    end
    Gateway.cardGeneration = Gateway.cardGeneration + 1
    local requestId = string.format(
        "cards-%d-%d",
        getTickCount(),
        Gateway.cardGeneration
    )
    local request = {
        requestId = requestId,
        generation = Gateway.cardGeneration,
        player = player,
        settled = false,
        handle = false,
    }
    Gateway.cardPending[requestId] = request
    setTimer(
        timeoutCardPicker,
        REQUEST_TIMEOUT_MS,
        1,
        requestId,
        request.generation
    )
    local envelope = encodeJson({
        protocol = PROTOCOL_NAME,
        protocolVersion = PROTOCOL_VERSION,
        requestId = requestId,
        query = query,
        deckFilter = deckFilter,
        page = page,
        pageSize = pageSize,
    })
    if not envelope then
        request.settled = true
        Gateway.cardPending[requestId] = nil
        cardPickerFailure(player, "protocol_error")
        return false, "json_encode_failed"
    end
    local headers = {
        ["Accept"] = "application/json",
        ["Content-Type"] = "application/json; charset=utf-8",
    }
    if type(effective.token) == "string" and effective.token ~= "" then
        headers["Authorization"] = "Bearer " .. effective.token
    end
    request.handle = fetchRemote(
        string.format(
            "http://127.0.0.1:%d%s",
            effective.port,
            CARD_SEARCH_PATH
        ),
        {
            method = "POST",
            postData = envelope,
            postIsBinary = false,
            headers = headers,
            queueName = "ankigta-card-picker",
            connectionAttempts = 1,
            connectTimeout = 4000,
            maxRedirects = 0,
        },
        cardPickerCallback,
        {
            requestId,
            generation = request.generation,
        }
    )
    if not request.handle then
        request.settled = true
        Gateway.cardPending[requestId] = nil
        cardPickerFailure(player, "transport_error")
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

function requestCompanionCardPicker(player, query, deckFilter, page, pageSize)
    return Gateway.requestCardPicker(
        player,
        query,
        deckFilter,
        page,
        pageSize
    )
end

function connectCompanion(player)
    return Gateway.connectConfigured(player, true)
end

function getCompanionConnectionStatus()
    return Gateway.getStatus()
end

ANKIGTA.CompanionGateway = Gateway

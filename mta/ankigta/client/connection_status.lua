local STATUS_EVENT = "ankigta:companionStatus"

local MESSAGES = {
    en = {
        connected = "ANKIGTA Companion: connected",
        connecting = "ANKIGTA Companion: connecting",
        protocol_error = "ANKIGTA Companion: protocol error",
        timeout = "ANKIGTA Companion: connection timed out",
        transport_error = "ANKIGTA Companion: transport error",
        collection_unavailable = "ANKIGTA Companion: collection unavailable",
        compatibility_failure = "ANKIGTA Companion: incompatible Anki configuration",
        disconnected = "ANKIGTA Companion: disconnected",
    },
    ru = {
        connected = "ANKIGTA Companion: подключено",
        connecting = "ANKIGTA Companion: подключение",
        protocol_error = "ANKIGTA Companion: ошибка протокола",
        timeout = "ANKIGTA Companion: превышено время ожидания",
        transport_error = "ANKIGTA Companion: ошибка транспорта",
        collection_unavailable = "ANKIGTA Companion: коллекция недоступна",
        compatibility_failure = "ANKIGTA Companion: конфигурация Anki несовместима",
        disconnected = "ANKIGTA Companion: отключено",
    },
}

local function messages()
    local localization = getLocalization()
    if type(localization) == "table"
        and type(localization.code) == "string"
        and string.sub(string.lower(localization.code), 1, 2) == "ru"
    then
        return MESSAGES.ru
    end
    return MESSAGES.en
end

local function statusMessage(status)
    local localized = messages()
    if status.state == "connected" then
        return localized.connected
    end
    if status.state == "connecting" then
        return localized.connecting
    end
    local category = tostring(status.category or "disconnected")
    return localized[category]
        or string.format("%s [%s]", localized.disconnected, category)
end

addEvent(STATUS_EVENT, true)
addEventHandler(STATUS_EVENT, resourceRoot, function(status)
    if source ~= resourceRoot or type(status) ~= "table" then
        return
    end
    outputChatBox(statusMessage(status), 196, 224, 255)
end)

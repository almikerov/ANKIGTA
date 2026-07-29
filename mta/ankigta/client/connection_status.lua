local STATUS_EVENT = "ankigta:companionStatus"

local function statusMessage(status)
    if status.state == "connected" then
        return "ANKIGTA Companion: connected"
    end
    if status.state == "connecting" then
        return "ANKIGTA Companion: connecting"
    end
    if status.category == "protocol_error" then
        return "ANKIGTA Companion: protocol error"
    end
    if status.category == "timeout" then
        return "ANKIGTA Companion: connection timed out"
    end
    return "ANKIGTA Companion: disconnected"
end

addEvent(STATUS_EVENT, true)
addEventHandler(STATUS_EVENT, resourceRoot, function(status)
    if source ~= resourceRoot or type(status) ~= "table" then
        return
    end
    outputChatBox(statusMessage(status), 196, 224, 255)
end)

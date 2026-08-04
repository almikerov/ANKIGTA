local STATUS_EVENT = "ankigta:companionStatus"

ANKIGTA = ANKIGTA or {}
ANKIGTA.ConnectionWarning = ANKIGTA.ConnectionWarning or {
    emptyTokenDismissed = false,
}

-- Every status line lives in the shared string table, read at the moment the
-- status arrives: this module used to carry a string table of its own, which
-- meant a wording fixed everywhere else was still wrong here.
local STATUS_KEY_PREFIX = "connection.status."

local function has(key)
    local strings = ANKIGTA.Locale and ANKIGTA.Locale.strings
    return strings ~= nil and strings[key] ~= nil
end

local function text(key, ...)
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.format(key, ...)
    end
    return key
end

local function statusMessage(status)
    if status.state == "connected" then
        return text(STATUS_KEY_PREFIX .. "connected")
    end
    if status.state == "connecting" then
        return text(STATUS_KEY_PREFIX .. "connecting")
    end
    local category = tostring(status.category or "disconnected")
    if has(STATUS_KEY_PREFIX .. category) then
        return text(STATUS_KEY_PREFIX .. category)
    end
    -- An unknown category is still worth showing, with the raw code attached:
    -- the code is a stable technical value and is not translated.
    return text(
        STATUS_KEY_PREFIX .. "unknown",
        text(STATUS_KEY_PREFIX .. "disconnected"),
        category
    )
end

-- What the chat was last told. A status is published whenever anyone asks for
-- one -- and the panel asks every time it opens -- so announcing each report
-- put "Companion: connected" in the chat after almost every action. The line
-- is worth reading when it changes and is noise when it does not, and the
-- panel already shows the standing state at the top.
local announced = nil

local function announcement(status)
    return tostring(status.state or "")
        .. "/" .. tostring(status.category or "")
        .. "/" .. tostring(status.warningCategory or "")
end

addEvent(STATUS_EVENT, true)
addEventHandler(STATUS_EVENT, resourceRoot, function(status)
    if source ~= resourceRoot or type(status) ~= "table" then
        return
    end
    local current = announcement(status)
    if current == announced then
        return
    end
    announced = current
    outputChatBox(statusMessage(status), 196, 224, 255)
    local warningCategory = tostring(status.warningCategory or "")
    if warningCategory ~= ""
        and not (
            warningCategory == "empty_token"
            and ANKIGTA.ConnectionWarning.emptyTokenDismissed
        )
    then
        if has(STATUS_KEY_PREFIX .. warningCategory) then
            outputChatBox(
                text(STATUS_KEY_PREFIX .. warningCategory),
                255,
                196,
                96
            )
        end
    end
end)

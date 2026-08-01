local STATUS_EVENT = "ankigta:companionStatus"

ANKIGTA = ANKIGTA or {}
ANKIGTA.ConnectionWarning = ANKIGTA.ConnectionWarning or {
    emptyTokenDismissed = false,
}

-- Every status line lives in the shared string table, read at the moment the
-- status arrives: this module used to carry its own two-language table and its
-- own locale detection, which meant switching the language setting moved the
-- rest of the interface and left the connection messages behind.
local STATUS_KEY_PREFIX = "connection.status."

local function has(key)
    local strings = ANKIGTA.Locale and ANKIGTA.Locale.strings
    local english = strings and strings.en
    return english ~= nil and english[key] ~= nil
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

addEvent(STATUS_EVENT, true)
addEventHandler(STATUS_EVENT, resourceRoot, function(status)
    if source ~= resourceRoot or type(status) ~= "table" then
        return
    end
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

local timerTicks = 0
local startedAt = 0
local finished = false
local requestId = false
local terminalSeen = false

local function readJson(path)
    if not fileExists(path) then
        return false
    end
    local handle = fileOpen(path, true)
    if not handle then
        return false
    end
    local text = fileRead(handle, fileGetSize(handle))
    fileClose(handle)
    local decoded = fromJSON(text)
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
    if string.sub(encoded, 1, 1) == "["
        and string.sub(encoded, -1) == "]"
    then
        return string.sub(encoded, 2, -2)
    end
    return encoded
end

local function writeResult(result)
    if finished then
        return
    end
    finished = true
    if fileExists("result.json") then
        fileDelete("result.json")
    end
    local handle = fileCreate("result.json")
    fileWrite(handle, encodeJson(result))
    fileFlush(handle)
    fileClose(handle)
    setTimer(function()
        shutdown("ANKIGTA ticket 02 acceptance complete")
    end, 100, 1)
end

local function pollStatus(case)
    local status = exports.ankigta:getCompanionConnectionStatus()
    if type(status) ~= "table"
        or status.requestId ~= requestId
        or status.state == "connecting"
    then
        return
    end
    if terminalSeen then
        return
    end
    terminalSeen = true
    local terminalElapsedMs = getTickCount() - startedAt
    local terminalTimerTicks = timerTicks
    if tonumber(case.waitAfterMs) and tonumber(case.waitAfterMs) > 0 then
        setTimer(function()
            writeResult({
                case = case.name,
                status = status,
                finalStatus = exports.ankigta:getCompanionConnectionStatus(),
                elapsedMs = terminalElapsedMs,
                timerTicks = terminalTimerTicks,
                mtaVersion = getVersion(),
            })
        end, tonumber(case.waitAfterMs), 1)
    else
        writeResult({
            case = case.name,
            status = status,
            elapsedMs = terminalElapsedMs,
            timerTicks = terminalTimerTicks,
            mtaVersion = getVersion(),
        })
    end
end

addEventHandler("onResourceStart", resourceRoot, function()
    local case = readJson("case.json")
    if type(case) ~= "table" then
        writeResult({error = "invalid_case"})
        return
    end
    startedAt = getTickCount()
    setTimer(function()
        timerTicks = timerTicks + 1
    end, 25, 0)
    setTimer(function()
        local accepted, acceptedRequestId =
            exports.ankigta:connectCompanion()
        if not accepted then
            writeResult({
                error = acceptedRequestId,
                elapsedMs = getTickCount() - startedAt,
                timerTicks = timerTicks,
            })
            return
        end
        requestId = acceptedRequestId
        setTimer(pollStatus, 25, 0, case)
    end, 50, 1)
end)

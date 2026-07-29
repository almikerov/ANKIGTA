local productionFetchRemote = fetchRemote
local capturedCallback = false
local capturedArguments = false

function fetchRemote(url, options, callback, callbackArguments)
    capturedCallback = callback
    capturedArguments = callbackArguments
    return productionFetchRemote(url, options, callback, callbackArguments)
end

addEventHandler("onResourceStart", resourceRoot, function()
    setTimer(function()
        if type(capturedCallback) ~= "function"
            or type(capturedArguments) ~= "table"
        then
            return
        end
        capturedCallback(
            "{}",
            {
                success = true,
                statusCode = 200,
                headers = {
                    ["Content-Type"] = "application/json",
                },
            },
            unpack(capturedArguments)
        )
    end, 5200, 1)
end)

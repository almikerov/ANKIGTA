addEventHandler("onResourceStart", resourceRoot, function()
    setTimer(function()
        local gateway = ANKIGTA and ANKIGTA.CompanionGateway
        if not gateway or type(gateway.receiveHealthResponse) ~= "function" then
            return
        end
        gateway.receiveHealthResponse(
            "{}",
            {
                success = true,
                statusCode = 200,
                headers = {
                    ["Content-Type"] = "application/json",
                },
            },
            "ticket02-late_callback",
            gateway.generation
        )
    end, 5200, 1)
end)

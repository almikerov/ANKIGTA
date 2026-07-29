local RESULT_PATH = "result.json"
local CASE_PATH = "case.json"
local RIGHT = "resource.ankigta.study"
local TARGET_RESOURCE_NAME = "ankigta"

local function readJson(path)
    if not fileExists(path) then
        return nil
    end

    local handle = fileOpen(path, true)
    if not handle then
        return nil
    end

    local body = fileRead(handle, fileGetSize(handle))
    fileClose(handle)

    local decoded = fromJSON(body)
    if type(decoded) == "table" and #decoded == 1 and type(decoded[1]) == "table" then
        return decoded[1]
    end
    return decoded
end

local function encodeJson(value)
    local encoded = toJSON(value, true)
    if string.sub(encoded, 1, 1) == "[" and string.sub(encoded, -1) == "]" then
        return string.sub(encoded, 2, -2)
    end
    return encoded
end

local function writeResult(value)
    if fileExists(RESULT_PATH) then
        fileDelete(RESULT_PATH)
    end

    local handle = fileCreate(RESULT_PATH)
    assert(handle, "could not create ticket 05 integration result")
    fileWrite(handle, encodeJson(value))
    fileFlush(handle)
    fileClose(handle)
end

local function ensureAccount(name)
    local account = getAccount(name)
    if account then
        return account
    end

    return assert(addAccount(name, "ticket-05-disposable-password"))
end

local function groupContainsObject(group, objectName)
    for _, existing in ipairs(aclGroupListObjects(group)) do
        if existing == objectName then
            return true
        end
    end
    return false
end

local function ensureAcl(caseName)
    local aclName = "ANKIGTA_Ticket05_" .. caseName
    local groupName = "ANKIGTA_Ticket05_" .. caseName
    local acl = aclGet(aclName) or assert(aclCreate(aclName))
    local group = aclGetGroup(groupName) or assert(aclCreateGroup(groupName))

    assert(aclSetRight(acl, RIGHT, true))
    assert(aclGroupAddACL(group, acl))

    local adminName = "ticket05_admin_" .. caseName
    local ordinaryName = "ticket05_ordinary_" .. caseName
    local admin = ensureAccount(adminName)
    local ordinary = ensureAccount(ordinaryName)
    if not groupContainsObject(group, "user." .. adminName) then
        assert(aclGroupAddObject(group, "user." .. adminName))
    end
    assert(aclSave())

    return admin, ordinary
end

local case = readJson(CASE_PATH)
local target = getResourceFromName(TARGET_RESOURCE_NAME)
local phase = "waiting"
local result = {
    case = case and case.name or "missing",
    mtaVersion = getVersion(),
}

local function request(account)
    local payload, denial = exports.ankigta:getF7SnapshotForAccount(account)
    return {
        payload = payload or false,
        denial = denial or false,
    }
end

local function clientLuaCompiles()
    local handle = fileOpen(":ankigta/client/f7.lua", true)
    if not handle then
        return false, "client_script_open_failed"
    end

    local body = fileRead(handle, fileGetSize(handle))
    fileClose(handle)
    local simpleCompiled, simpleError = loadstring("return true")
    local compiled, compileError = loadstring(body)
    return type(compiled) == "function", compileError, {
        bytes = string.len(body),
        compiledType = type(compiled),
        loadstringType = type(loadstring),
        loadstringAllowed = hasObjectPermissionTo(
            resource,
            "function.loadstring",
            false
        ),
        simpleCompiledType = type(simpleCompiled),
        simpleError = simpleError,
    }
end

local function finish()
    writeResult(result)
    setTimer(function()
        shutdown("ANKIGTA ticket 05 real-MTA acceptance case complete")
    end, 150, 1)
end

local function afterTargetRestart()
    local admin, ordinary = ensureAcl(case.name)

    if case.name == "migration_failure" then
        result.storeStatus = exports.ankigta:getStoreStatus()
        result.admin = request(admin)
        result.ordinary = request(ordinary)
        finish()
        return
    end

    if phase == "waiting" then
        result.storeStatus = exports.ankigta:getStoreStatus()
        result.clientLuaSyntax, result.clientLuaSyntaxError, result.clientLuaSyntaxDetail =
            clientLuaCompiles()
        result.admin = request(admin)
        result.ordinary = request(ordinary)
        result.guest = request(false)

        if case.name == "migration" then
            finish()
            return
        end

        local runtimeInstance = getElementByID("ankigta-ticket05-runtime")
        result.runtimeInitiallyPresent = isElement(runtimeInstance)
        if isElement(runtimeInstance) then
            destroyElement(runtimeInstance)
        end
        result.withoutRuntimeInstance = request(admin)

        phase = "restarting"
        assert(restartResource(target))
        return
    end

    if phase == "restarting" then
        result.afterResourceRestart = request(admin)
        finish()
    end
end

addEventHandler("onResourceStart", root, function(startedResource)
    if startedResource == target then
        setTimer(afterTargetRestart, 100, 1)
    end
end)

addEventHandler("onResourceStart", resourceRoot, function()
    if not case or type(case.name) ~= "string" then
        result.error = "missing integration case"
        finish()
        return
    end

    target = getResourceFromName(TARGET_RESOURCE_NAME)
    if not target or getResourceState(target) ~= "running" then
        result.error = "production ankigta resource is not running"
        finish()
        return
    end

    setTimer(afterTargetRestart, 100, 1)
end)

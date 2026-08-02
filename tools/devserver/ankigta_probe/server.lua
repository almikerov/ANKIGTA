-- A control channel for a development server, driven by files.
--
-- Every bug this project has cost a round trip through a person standing in
-- the world: press a key, click a thing, report back. Most of the questions
-- were about facts the server already knew. This lets whoever is working on
-- the resource ask the server directly and act on the answer.
--
-- Write a command into `command.txt`; it is executed within a second and the
-- answer is appended to `result.txt`, then the command file is emptied so the
-- same line is never run twice.
--
-- DEVELOPMENT ONLY. `exec` runs arbitrary server Lua, so anyone who can write
-- a file in this folder can run code as the server. That is the point on a
-- local box and unacceptable anywhere else.

local COMMAND_FILE = "@command.txt"
local RESULT_FILE = "@result.txt"
local REPORT_FILE = "@report.txt"
local POLL_INTERVAL = 1000

-- --- files -------------------------------------------------------------------

local function readWhole(path)
    if not fileExists(path) then
        return nil
    end
    local handle = fileOpen(path, true)
    if not handle then
        return nil
    end
    local size = fileGetSize(handle)
    local text = size > 0 and fileRead(handle, size) or ""
    fileClose(handle)
    return text
end

local function writeWhole(path, text)
    if fileExists(path) then
        fileDelete(path)
    end
    local handle = fileCreate(path)
    if not handle then
        return false
    end
    fileWrite(handle, text)
    fileClose(handle)
    return true
end

local function appendResult(text)
    local existing = readWhole(RESULT_FILE) or ""
    -- Kept bounded: a loop that writes every second would otherwise grow a
    -- file nobody trims until the disk notices.
    if #existing > 200000 then
        existing = ""
    end
    writeWhole(RESULT_FILE, existing .. text .. "\n")
end

-- --- the world report --------------------------------------------------------

local function ownerOf(element)
    for _, res in ipairs(getResources()) do
        local root = getResourceRootElement(res)
        local ancestor = element
        while isElement(ancestor) do
            if ancestor == root then
                return getResourceName(res)
            end
            ancestor = getElementParent(ancestor)
        end
    end
    return "<none>"
end

local function describe(element)
    local x, y, z = getElementPosition(element)
    return string.format(
        "  %-8s id=%-34s owner=%-16s me:ID=%-10s ankigtaEntityId=%-10s "
            .. "model=%-6s dim=%s int=%s pos=%.1f,%.1f,%.1f",
        getElementType(element),
        tostring(getElementID(element)),
        ownerOf(element),
        tostring(getElementData(element, "me:ID")),
        tostring(getElementData(element, "ankigtaEntityId")),
        tostring(getElementModel(element)),
        tostring(getElementDimension(element)),
        tostring(getElementInterior(element)),
        x or 0, y or 0, z or 0
    )
end

local function worldReport()
    local lines = {"ANKIGTA live probe", "=================="}
    local function say(text) table.insert(lines, text) end

    say("")
    say("-- resources running --")
    local running = {}
    for _, res in ipairs(getResources()) do
        if getResourceState(res) == "running" then
            table.insert(running, getResourceName(res))
        end
    end
    table.sort(running)
    say("  " .. table.concat(running, ", "))

    for _, kind in ipairs({"object", "vehicle", "ped"}) do
        local all = getElementsByType(kind)
        say("")
        say(string.format("-- %s: %d in the world --", kind, #all))
        local named, unnamed = 0, 0
        for _, element in ipairs(all) do
            local id = getElementID(element)
            if id ~= nil and id ~= "" then
                named = named + 1
                -- Only named elements can be adopted, so only they are listed.
                if named <= 40 then
                    say(describe(element))
                end
            else
                unnamed = unnamed + 1
            end
        end
        say(string.format(
            "  named (adoptable candidates): %d, unnamed (skipped): %d",
            named, unnamed
        ))
    end
    say("")
    say("-- end --")
    return table.concat(lines, "\n")
end

-- --- commands ----------------------------------------------------------------

local commands = {}

local function resourceByName(name)
    local res = getResourceFromName(name or "")
    if not res then
        return nil, "no such resource: " .. tostring(name)
    end
    return res
end

function commands.help()
    return table.concat({
        "probe                     -- what is loaded in the world right now",
        "report                    -- the same, also written to report.txt",
        "list [filter]             -- every resource and its state",
        "start <resource>",
        "stop <resource>",
        "restart <resource>",
        "refresh                   -- pick up new/changed resource folders",
        "refreshall                -- the same, forcing a full rescan",
        "players                   -- who is connected, and their account",
        "say <text>                -- into the chat of every player",
        "acl-grant <resource>      -- make it an admin, and save",
        "acl-revoke <resource>",
        "acl-check <resource>      -- what it may actually do, right now",
        "acl-add <group> <object>  -- e.g. acl-add Admin resource.foo",
        "acl-right <acl> <right> <true|false>",
        "call <resource> <export> [args...]",
        "exec <lua>                -- arbitrary server Lua; returns its value",
        "shutdown                  -- stop the server",
    }, "\n")
end

function commands.probe()
    return worldReport()
end

function commands.report()
    local text = worldReport()
    writeWhole(REPORT_FILE, text .. "\n")
    return text
end

function commands.list(filter)
    local rows = {}
    for _, res in ipairs(getResources()) do
        local name = getResourceName(res)
        if not filter or filter == "" or string.find(name, filter, 1, true) then
            table.insert(rows, string.format(
                "  %-28s %s", name, getResourceState(res)
            ))
        end
    end
    table.sort(rows)
    return table.concat(rows, "\n")
end

function commands.start(name)
    local res, missing = resourceByName(name)
    if not res then return missing end
    return startResource(res, true) and ("started " .. name)
        or ("could not start " .. name)
end

function commands.stop(name)
    local res, missing = resourceByName(name)
    if not res then return missing end
    return stopResource(res) and ("stopped " .. name)
        or ("could not stop " .. name)
end

function commands.restart(name)
    local res, missing = resourceByName(name)
    if not res then return missing end
    return restartResource(res) and ("restarted " .. name)
        or ("could not restart " .. name)
end

function commands.refresh()
    return refreshResources(false) and "refreshed" or "refresh failed"
end

function commands.refreshall()
    return refreshResources(true) and "refreshed all" or "refresh failed"
end

function commands.players()
    local rows = {}
    for _, player in ipairs(getElementsByType("player")) do
        local account = getPlayerAccount(player)
        local x, y, z = getElementPosition(player)
        table.insert(rows, string.format(
            "  %-20s account=%-16s guest=%-5s dim=%s int=%s pos=%.1f,%.1f,%.1f",
            getPlayerName(player),
            account and getAccountName(account) or "<none>",
            tostring(account and isGuestAccount(account)),
            tostring(getElementDimension(player)),
            tostring(getElementInterior(player)),
            x or 0, y or 0, z or 0
        ))
    end
    if #rows == 0 then
        return "  nobody is connected"
    end
    return table.concat(rows, "\n")
end

function commands.say(...)
    local text = table.concat({...}, " ")
    outputChatBox(text, root, 120, 200, 255)
    return "said: " .. text
end

function commands.acl_add(groupName, objectName)
    local group = aclGetGroup(groupName or "")
    if not group then
        return "no such ACL group: " .. tostring(groupName)
    end
    return aclGroupAddObject(group, objectName) and aclSave()
        and ("added " .. tostring(objectName) .. " to " .. groupName)
        or "could not add"
end

function commands.acl_right(aclName, rightName, access)
    local acl = aclGet(aclName or "")
    if not acl then
        return "no such ACL: " .. tostring(aclName)
    end
    local granted = aclSetRight(acl, rightName, access == "true")
    return granted and aclSave()
        and string.format("%s.%s = %s", aclName, rightName, tostring(access))
        or "could not set right"
end

--- Make a resource an admin, the way that survives a shutdown.
--
-- Editing `acl.xml` under a running server is the thing that does *not* work:
-- MTA reads it at start and writes it back from memory on the way out, so the
-- edit is overwritten and silently lost. Going through the ACL API changes the
-- memory the server will write, which is why this sticks and a text editor
-- does not.
--
-- `general.ModifyOtherObjects` is the one that matters most in practice: every
-- look inside another resource is gated on it, so a file watcher without it
-- reads nothing and cannot tell that from nothing having changed.
function commands.acl_grant(resourceName)
    if type(resourceName) ~= "string" or resourceName == "" then
        return "usage: acl-grant <resource>"
    end
    local group = aclGetGroup("Admin")
    if not group then
        return "no Admin ACL group on this server"
    end
    local object = "resource." .. resourceName
    if not getResourceFromName(resourceName) then
        return "no such resource: " .. resourceName
    end
    if not aclGroupAddObject(group, object) then
        return object .. " is already in Admin, or could not be added"
    end
    if not aclSave() then
        return "added, but the ACL could not be saved"
    end
    return object .. " is in Admin now, and saved"
end

function commands.acl_revoke(resourceName)
    local group = aclGetGroup("Admin")
    if not group then
        return "no Admin ACL group on this server"
    end
    local object = "resource." .. tostring(resourceName)
    if not aclGroupRemoveObject(group, object) then
        return object .. " was not in Admin"
    end
    aclSave()
    return object .. " is out of Admin now, and saved"
end

--- What a resource may actually do, asked of the server rather than the file.
function commands.acl_check(resourceName)
    local target = getResourceFromName(resourceName or "")
    if not target then
        return "no such resource: " .. tostring(resourceName)
    end
    local rows = {}
    for _, right in ipairs({
        "general.ModifyOtherObjects",
        "general.http",
        "function.refreshResources",
        "function.restartResource",
        "function.startResource",
        "function.stopResource",
        "function.loadstring",
        "function.aclSave",
        "function.shutdown",
    }) do
        rows[#rows + 1] = string.format(
            "  %-34s %s",
            right,
            hasObjectPermissionTo(target, right, false) and "yes" or "NO"
        )
    end
    return table.concat(rows, "
")
end

function commands.call(resourceName, exportName, ...)
    local res, missing = resourceByName(resourceName)
    if not res then return missing end
    local ok, result = pcall(call, res, exportName, ...)
    if not ok then
        return "call failed: " .. tostring(result)
    end
    return "=> " .. inspect(result)
end

function commands.exec(...)
    local body = table.concat({...}, " ")
    -- `return` first so a bare expression answers with its value; if that does
    -- not compile it is a statement, and it runs as one.
    local chunk, compileError = loadstring("return " .. body)
    if not chunk then
        chunk, compileError = loadstring(body)
    end
    if not chunk then
        return "compile error: " .. tostring(compileError)
    end
    local ok, result = pcall(chunk)
    if not ok then
        return "error: " .. tostring(result)
    end
    return "=> " .. inspect(result)
end

function commands.shutdown()
    appendResult("shutting down")
    setTimer(function() shutdown("ankigta dev control") end, 500, 1)
    return "shutting down in 500ms"
end

-- --- value rendering ---------------------------------------------------------

function inspect(value, depth)
    depth = depth or 0
    local kind = type(value)
    if kind == "table" then
        if depth > 3 then
            return "{...}"
        end
        local parts = {}
        for key, item in pairs(value) do
            table.insert(parts, string.format(
                "%s = %s", tostring(key), inspect(item, depth + 1)
            ))
        end
        table.sort(parts)
        return "{" .. table.concat(parts, ", ") .. "}"
    end
    if kind == "userdata" and isElement(value) then
        return string.format(
            "<%s id=%s>", getElementType(value), tostring(getElementID(value))
        )
    end
    return tostring(value)
end

-- --- the loop ----------------------------------------------------------------

local function words(line)
    local out = {}
    for word in string.gmatch(line, "%S+") do
        table.insert(out, word)
    end
    return out
end

local function runLine(line)
    local parts = words(line)
    local name = table.remove(parts, 1)
    if not name then
        return nil
    end
    -- `exec` and `say` take the rest of the line whole, spaces and all.
    if name == "exec" or name == "say" then
        local rest = string.match(line, "^%s*%S+%s+(.*)$") or ""
        return commands[name](rest)
    end
    local handler = commands[string.gsub(name, "%-", "_")]
    if not handler then
        return "unknown command: " .. name .. " (try `help`)"
    end
    local ok, result = pcall(handler, unpack(parts))
    if not ok then
        return "command failed: " .. tostring(result)
    end
    return result
end

local function poll()
    local text = readWhole(COMMAND_FILE)
    if not text or text == "" then
        return
    end
    -- Emptied before running, so a command that restarts this resource is not
    -- found again and run a second time on the way back up.
    writeWhole(COMMAND_FILE, "")
    for line in string.gmatch(text, "[^\r\n]+") do
        if string.match(line, "%S") and string.sub(line, 1, 1) ~= "#" then
            appendResult("$ " .. line)
            local answer = runLine(line)
            if answer ~= nil then
                appendResult(tostring(answer))
            end
            appendResult("")
        end
    end
end

addEventHandler("onResourceStart", resourceRoot, function()
    writeWhole(COMMAND_FILE, "")
    appendResult("--- ankigta dev control up ---")
    setTimer(poll, POLL_INTERVAL, 0)
    -- The maps other resources load are not all in place the instant this one
    -- starts, so the opening report waits for them.
    setTimer(commands.report, 3000, 1)
end)

addCommandHandler("ankigta-probe", function()
    commands.report()
    outputChatBox("[ankigta] report written", root, 120, 200, 255)
end)

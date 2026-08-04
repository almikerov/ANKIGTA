-- The file channel: how the watcher asks for a reload.
--
-- Write a request line into `command.txt`; it runs within a fraction of a
-- second and one JSON object per request is appended to `result.txt`. The
-- command file is emptied before the requests in it run, so a request that
-- restarts something is not found again and run twice on the way back up.
--
--     status
--     reload {"resource": "my_resource", "requestId": "abc"}
--
-- Why a file rather than MTA's HTTP interface, which this resource used to
-- offer: the HTTP path needs an MTA account, and an account needs a password,
-- and that password sat in the watcher's `config.json` in plain text. A
-- `.gitignore` keeps a secret out of a publication, not off a disk. There is
-- no secret here to keep anywhere -- and no listener either, so nothing about
-- this resource can be reached from the network at all, which is more than
-- "listens on loopback" would have given.
--
-- It also makes the resource installable on its own: no account to create, no
-- ACL right to grant, no port to agree on. Drop the folder in and start it.
--
-- The shape of this channel -- a command file polled on a timer, answers
-- appended as one JSON object per line -- is deliberately duplicated from
-- `mta_agent_devtools/server/channel.lua`, which does the same thing for a
-- different tool. Sharing it would mean a library resource, and a resource
-- that needs a neighbour present in order to start is not one you can hand to
-- somebody as a single download.

local COMMAND_FILE = "@command.txt"
local RESULT_FILE = "@result.txt"
--- Four times a second. The watcher already waits out its own debounce before
--- asking, so this is the only delay it cannot control, and reading one small
--- file this often costs nothing worth measuring.
local POLL_INTERVAL = 250
--- Past this the answer file is started over. A reader that finds a shorter
--- file than it left must be able to tell "trimmed" from "nothing happened",
--- so the trim announces itself in the file.
local RESULT_CEILING = 200000

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

local function appendLine(text)
    local existing = readWhole(RESULT_FILE) or ""
    if #existing > RESULT_CEILING then
        existing = '{"ok":true,"notice":"result file trimmed"}\n'
    end
    writeWhole(RESULT_FILE, existing .. text .. "\n")
end

--- Encode an answer as JSON.
--
-- `toJSON` wraps whatever it is given in a one-element array, so the object
-- has to be unwrapped back out of it. Getting this wrong is not a formatting
-- detail: the reader receives a list where it expected a record.
local function encode(answer)
    local text = toJSON(answer, true)
    if type(text) ~= "string" then
        return '{"ok":false,"error":"ENCODE_FAILED"}'
    end
    local inner = text:match("^%s*%[(.*)%]%s*$")
    return inner or text
end

--- Split a request line into its command name and its JSON payload.
--
-- The payload is optional, so `status` alone is a valid line. A payload that
-- does not parse is refused by name rather than quietly treated as absent:
-- running a command with its arguments silently dropped is how a caller ends
-- up certain of an answer to a question it did not ask.
local function parse(line)
    local name, rest = line:match("^%s*([%w_%-]+)%s*(.*)$")
    if not name then
        return nil, nil, "NOT_A_COMMAND"
    end
    if rest == nil or rest:match("^%s*$") then
        return name:lower(), {}, nil
    end
    local payload = fromJSON(rest)
    if type(payload) ~= "table" then
        return name:lower(), nil, "BAD_PAYLOAD"
    end
    return name:lower(), payload, nil
end

local function runLine(line)
    local name, payload, parseError = parse(line)
    if parseError == "NOT_A_COMMAND" then
        return {
            ok = false,
            error = "NOT_A_COMMAND",
            message = "could not read a command name from: " .. line,
        }
    end
    if parseError == "BAD_PAYLOAD" then
        return {
            ok = false,
            error = "BAD_PAYLOAD",
            command = name,
            message = "the text after the command name is not a JSON object",
        }
    end

    local answer
    if name == "status" then
        local ok, detail = getHotReloadStatus()
        answer = {ok = ok == true, result = detail}
    elseif name == "reload" then
        if type(payload.resource) ~= "string" then
            answer = {
                ok = false,
                error = "MISSING_RESOURCE",
                message = 'reload needs {"resource": "<name>"}',
            }
        else
            local ok, detail = reloadResourceByName(payload.resource)
            answer = {ok = ok == true, result = detail}
        end
    else
        answer = {
            ok = false,
            error = "UNKNOWN_COMMAND",
            message = "no such command: " .. name,
            commands = {"status", "reload"},
        }
    end

    answer.command = name
    -- Echoed back so the watcher can match an answer to the request it made
    -- rather than to whatever landed in the file next.
    if payload.requestId ~= nil then
        answer.requestId = payload.requestId
    end
    return answer
end

local function poll()
    local text = readWhole(COMMAND_FILE)
    if not text or text == "" then
        return
    end
    writeWhole(COMMAND_FILE, "")
    for line in text:gmatch("[^\r\n]+") do
        if line:match("%S") and line:sub(1, 1) ~= "#" then
            appendLine(encode(runLine(line)))
        end
    end
end

addEventHandler("onResourceStart", resourceRoot, function()
    writeWhole(COMMAND_FILE, "")
    appendLine(encode({ok = true, notice = "dev_hotreload channel up"}))
    setTimer(poll, POLL_INTERVAL, 0)
end)

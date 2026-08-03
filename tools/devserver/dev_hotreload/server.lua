local BLOCKED_RESOURCES = {
    ["dev_hotreload"] = true,
    ["local_admin_autologin"] = true,
    ["admin"] = true,
    ["webadmin"] = true,
    ["resourcebrowser"] = true,
    ["resourcemanager"] = true,
}

local managedOverrides = {}
--- Resources this starts when the server starts, by name.
--
-- The server's own autostart list lives in `mtaserver.conf` and is read once,
-- at boot, so a change there needs a restart to mean anything. Starting them
-- from here has the same effect and can be switched from the panel, because
-- this resource is itself in that list.
local startupOverrides = {}
--- Off unless the state file says otherwise, and deliberately so: watching
--- costs a read of every managed resource on every tick.
local autoupdateEnabled = false
--- The last content fingerprint seen per resource, and the timer watching.
local fingerprints = {}
local autoupdateTimer = nil
local stateRevision = 0
--- The resource names MTA knew about at the last Discovery pass, and the timer
--- looking for more. `nil` until something baselines it, which is what stops
--- the first pass from adopting the entire server as newly arrived.
local knownResources = nil
local discoveryTimer = nil
--- How many passes in a row Discovery has failed to start each new name, and
--- how many it gets before being written off. A folder copied in file by file
--- is briefly real and broken, which is worth waiting out; a genuinely broken
--- one is not worth saying so about every ten seconds forever.
local discoveryFailures = {}
local DISCOVERY_ATTEMPTS = 3
--- Filled in further down, declared here: `applyAutoupdate` starts this timer
--- and is written above the point where the pass can be defined, because the
--- pass needs `setResourceManagement` and `reloadResourceByName` first.
local pollForNewResources = nil
--- Also filled in further down. `reloadResourceByName` reports what moved, and
--- it is written above the fingerprint machinery that can tell.
local noteResourceChanges = nil

local function log(message, level)
    outputDebugString(HOTRELOAD_CONFIG.logPrefix .. " " .. message, level or 3)
end

local function reply(commandSource, message)
    local fullMessage = HOTRELOAD_CONFIG.logPrefix .. " " .. message
    if commandSource then
        outputConsole(fullMessage, commandSource)
    else
        outputDebugString(fullMessage, 3)
    end
end

local function trim(value)
    return value:match("^%s*(.-)%s*$")
end

local function validateResourceName(resourceName)
    if type(resourceName) ~= "string" then
        return nil, "INVALID_ARGUMENT", "Resource name must be a string"
    end

    local normalized = trim(resourceName)
    if normalized == "" then
        return nil, "INVALID_RESOURCE_NAME", "Resource name cannot be blank"
    end
    if not normalized:match("^[A-Za-z0-9_-]+$") then
        return nil, "INVALID_RESOURCE_NAME", "Resource name contains unsupported characters"
    end
    if BLOCKED_RESOURCES[normalized:lower()] then
        return nil, "RESOURCE_BLOCKED", "This protected resource cannot be managed by Hot Reload"
    end
    return normalized
end

local function isResourceAllowed(resourceName)
    if BLOCKED_RESOURCES[resourceName:lower()] then
        return false
    end
    if managedOverrides[resourceName] ~= nil then
        return managedOverrides[resourceName]
    end
    return HOTRELOAD_CONFIG.defaultAllowedResources[resourceName] == true
end

local function isCustomResource(resourceValue)
    local path = getResourceOrganizationalPath(resourceValue)
    if type(path) ~= "string" or path == "" then
        return true
    end
    local normalized = path:gsub("\\", "/"):lower()
    for bundledPath in pairs(HOTRELOAD_CONFIG.bundledOrganizationalPaths or {}) do
        local bundled = tostring(bundledPath):gsub("\\", "/"):lower()
        if normalized == bundled or normalized:sub(1, #bundled + 1) == bundled .. "/" then
            return false
        end
    end
    return true
end

local function loadManagedState()
    managedOverrides = {}
    startupOverrides = {}
    local rootNode = xmlLoadFile(HOTRELOAD_CONFIG.stateFile)
    if not rootNode then
        log("No saved management state yet; starting with configured defaults")
        return
    end

    -- Autoupdate is off unless the file says otherwise: watching files costs
    -- a read of every managed resource on every tick, and a setting that
    -- switches itself on after a restart is a setting nobody chose.
    autoupdateEnabled = xmlNodeGetAttribute(rootNode, "autoupdate") == "true"

    for _, node in ipairs(xmlNodeGetChildren(rootNode)) do
        if xmlNodeGetName(node) == "resource" then
            local name = xmlNodeGetAttribute(node, "name")
            local allowed = xmlNodeGetAttribute(node, "allowed")
            local startup = xmlNodeGetAttribute(node, "startup")
            local normalized = validateResourceName(name)
            if normalized and (allowed == "true" or allowed == "false") then
                managedOverrides[normalized] = allowed == "true"
            end
            if normalized and startup == "true" then
                startupOverrides[normalized] = true
            end
        end
    end
    xmlUnloadFile(rootNode)
    log("Saved Hot Reload resource selections loaded")
end

local function saveManagedState()
    local rootNode = xmlCreateFile(HOTRELOAD_CONFIG.stateFile, "hotreload")
    if not rootNode then
        return false, "Could not create the private Hot Reload state file"
    end

    xmlNodeSetAttribute(rootNode, "autoupdate", autoupdateEnabled and "true" or "false")

    local names = {}
    local seen = {}
    for name in pairs(managedOverrides) do
        names[#names + 1] = name
        seen[name] = true
    end
    -- A resource can be marked for startup without being hot-reloadable, so
    -- the two lists are not the same list.
    for name in pairs(startupOverrides) do
        if not seen[name] then
            names[#names + 1] = name
        end
    end
    table.sort(names)

    for _, name in ipairs(names) do
        local node = xmlCreateChild(rootNode, "resource")
        xmlNodeSetAttribute(node, "name", name)
        xmlNodeSetAttribute(
            node, "allowed", managedOverrides[name] and "true" or "false"
        )
        if startupOverrides[name] then
            xmlNodeSetAttribute(node, "startup", "true")
        end
    end

    local saved = xmlSaveFile(rootNode)
    xmlUnloadFile(rootNode)
    if not saved then
        return false, "Could not save the private Hot Reload state file"
    end
    stateRevision = stateRevision + 1
    return true
end

local function failure(resourceName, code, message)
    log(("Rejected operation for '%s': %s (%s)"):format(tostring(resourceName), message, code), 2)
    return false, {
        resource = type(resourceName) == "string" and resourceName or "",
        accepted = false,
        error = code,
        message = message,
    }
end

local function buildResourceCatalog()
    local catalog = {}
    local allowedResources = {}
    for _, resourceValue in ipairs(getResources()) do
        local name = getResourceName(resourceValue)
        local blocked = BLOCKED_RESOURCES[name:lower()] == true
        local allowed = not blocked and isResourceAllowed(name)
        if allowed then
            table.insert(allowedResources, name)
        end
        table.insert(catalog, {
            name = name,
            state = getResourceState(resourceValue),
            hotReload = blocked and "blocked" or (allowed and "allowed" or "ignored"),
            organizationalPath = getResourceOrganizationalPath(resourceValue) or "",
            custom = isCustomResource(resourceValue),
            startup = startupOverrides[name] == true,
        })
    end
    table.sort(catalog, function(left, right) return left.name:lower() < right.name:lower() end)
    table.sort(allowedResources)
    return catalog, allowedResources
end

local function canManageFromClient(player)
    return isElement(player)
        and getElementType(player) == "player"
        and hasObjectPermissionTo(player, "command." .. HOTRELOAD_CONFIG.commandName, false)
end

local function sendCatalogToClient(player, message)
    local catalog, allowedResources = buildResourceCatalog()
    triggerClientEvent(player, "dev_hotreload:catalog", resourceRoot, {
        resources = catalog,
        allowedCount = #allowedResources,
        revision = stateRevision,
        autoupdate = autoupdateEnabled,
    })
    if message then
        triggerClientEvent(player, "dev_hotreload:message", resourceRoot, message, false)
    end
end

function getHotReloadStatus()
    local catalog, allowedResources = buildResourceCatalog()
    return true, {
        resource = getResourceName(getThisResource()),
        running = getResourceState(getThisResource()) == "running",
        revision = stateRevision,
        allowedResources = allowedResources,
        resources = catalog,
        message = "Hot Reload endpoint is available",
    }
end

function reloadResourceByName(resourceName)
    local normalized, errorCode, errorMessage = validateResourceName(resourceName)
    if not normalized then
        return failure(resourceName, errorCode, errorMessage)
    end
    if not isResourceAllowed(normalized) then
        return failure(normalized, "RESOURCE_NOT_ALLOWED", "This resource is ignored by Hot Reload")
    end

    log(("Reload requested for '%s'"):format(normalized))
    -- Before the restart, because after it there is no "before" left to
    -- compare against and the reason for the reload would go unreported.
    noteResourceChanges(normalized)
    local targetResource = getResourceFromName(normalized)
    if not targetResource then
        log(("Resource '%s' is not loaded; refreshing the resource list once"):format(normalized))
        if not refreshResources(false) then
            return failure(normalized, "RESOURCE_DISCOVERY_FAILED", "Resource discovery refresh failed")
        end
        targetResource = getResourceFromName(normalized)
        if not targetResource then
            return failure(normalized, "RESOURCE_NOT_FOUND", "Resource was not found after refreshing the resource list")
        end
    end

    if getResourceName(targetResource) ~= normalized then
        return failure(normalized, "RESOURCE_NAME_MISMATCH", "Located resource did not match the requested name")
    end
    if not refreshResources(false, targetResource) then
        return failure(normalized, "RESOURCE_REFRESH_FAILED", "Targeted resource refresh failed")
    end

    targetResource = getResourceFromName(normalized)
    if not targetResource then
        return failure(normalized, "RESOURCE_NOT_FOUND_AFTER_REFRESH", "Resource disappeared during targeted refresh")
    end

    local stateBefore = getResourceState(targetResource)
    local action
    local accepted
    if stateBefore == "running" then
        action = "restart"
        accepted = restartResource(targetResource)
        if not accepted then
            return failure(normalized, "RESOURCE_RESTART_FAILED", "Resource restart request failed")
        end
    else
        action = "start"
        accepted = startResource(targetResource)
        if not accepted then
            return failure(normalized, "RESOURCE_START_FAILED", "Resource start request failed from state " .. tostring(stateBefore))
        end
    end

    local message = action == "restart" and "Resource restart requested" or "Resource start requested"
    log(("%s accepted for '%s' (previous state: %s)"):format(action, normalized, tostring(stateBefore)))
    return true, {
        resource = normalized,
        action = action,
        stateBefore = stateBefore,
        accepted = true,
        message = message,
    }
end

-- --- watching for changes ----------------------------------------------------

--- Everything a resource declares, plus the declaration itself.
--
-- Read from `meta.xml` rather than by walking the folder, because MTA gives no
-- way to list a directory -- and because what is not declared is not loaded, so
-- a change to it would not be a change to the resource.
local function declaredFiles(resourceName)
    local meta = xmlLoadFile(":" .. resourceName .. "/meta.xml")
    if not meta then
        return nil
    end
    local files = {"meta.xml"}
    for _, node in ipairs(xmlNodeGetChildren(meta)) do
        local tag = xmlNodeGetName(node)
        if tag == "script" or tag == "file" or tag == "map"
            or tag == "config" or tag == "html"
        then
            local src = xmlNodeGetAttribute(node, "src")
            if type(src) == "string" and src ~= "" then
                files[#files + 1] = src
            end
        end
    end
    xmlUnloadFile(meta)
    table.sort(files)
    return files
end

--- What every declared file of a resource holds right now.
--
-- MTA offers no modification time, so this is the content itself. Two things
-- come back: a `digest` that changes when anything changes, which is all the
-- poll compares, and the per-file `files` detail the change report is built
-- from.
--
-- A file over the content cap contributes its size instead: a map big enough
-- to matter is not the file anybody is editing in a loop, and reading it every
-- tick would cost more than the answer is worth. Content is *kept* only under
-- the smaller diff cap, and keeping it is the whole trick behind reporting
-- `+/-` later without reading the old version again -- there is nowhere to
-- read it from, because the change has already happened.
local CONTENT_CAP = 1048576
local DIFF_CAP = 262144

local function resourceFingerprint(resourceName)
    local files = declaredFiles(resourceName)
    if not files then
        -- Cannot even read the manifest, which is the first thing that fails
        -- when this resource has no right to look inside another one.
        return nil, "unreadable"
    end
    local parts = {}
    local detail = {}
    local unreadable = 0
    for _, relative in ipairs(files) do
        local handle = fileOpen(":" .. resourceName .. "/" .. relative, true)
        if not handle then
            unreadable = unreadable + 1
            parts[#parts + 1] = relative .. ":missing"
        else
            local size = fileGetSize(handle)
            if size > CONTENT_CAP then
                local mark = "size:" .. tostring(size)
                parts[#parts + 1] = relative .. ":" .. mark
                detail[relative] = {hash = mark}
            else
                local content = size > 0 and fileRead(handle, size) or ""
                content = content or ""
                local hash = md5(content)
                parts[#parts + 1] = relative .. ":" .. hash
                detail[relative] = {
                    hash = hash,
                    content = size <= DIFF_CAP and content or nil,
                }
            end
            fileClose(handle)
        end
    end
    -- Every file unreadable is not "nothing changed", it is "cannot tell".
    -- Returning a stable fingerprint for that would make Autoupdate look like
    -- it was watching while it silently never saw anything -- which is exactly
    -- how it behaved before this said so.
    if unreadable >= #files then
        return nil, "unreadable"
    end
    return {digest = md5(table.concat(parts, "|")), files = detail}, nil
end

--- How many times each line appears in a piece of text.
--
-- Keyed by the line itself: Lua interns strings, so this needs no hashing of
-- our own and compares by value the way a diff does. Line endings are
-- normalised first, or a file saved once by a Windows editor reads as every
-- line having changed.
local function lineCounts(content)
    if type(content) ~= "string" or content == "" then
        return {}
    end
    local normalized = (content:gsub("\r\n", "\n"))
    if normalized:sub(-1) ~= "\n" then
        normalized = normalized .. "\n"
    end
    local counts = {}
    for line in normalized:gmatch("(.-)\n") do
        counts[line] = (counts[line] or 0) + 1
    end
    return counts
end

--- Lines added and removed between two versions of one file.
--
-- Counted as multisets rather than by position, which is what makes editing a
-- line read as `+1 -1` instead of `0`. A line merely moved counts as neither,
-- which is the honest answer at this resolution: this reports how much moved,
-- not a patch.
local function lineDelta(before, after)
    local old, new = lineCounts(before), lineCounts(after)
    local added, removed = 0, 0
    for line, count in pairs(new) do
        local was = old[line] or 0
        if count > was then
            added = added + (count - was)
        end
    end
    for line, count in pairs(old) do
        local now = new[line] or 0
        if count > now then
            removed = removed + (count - now)
        end
    end
    return added, removed
end

--- Which files differ between two fingerprints of the same resource, and by
--- how much.
--
-- A file too large to have kept its content reports `nil` counts rather than
-- zero: "changed by an unknown amount" and "changed by nothing" are different
-- answers and must not print the same.
local function describeChanges(previous, current)
    local changes = {}
    if type(previous) ~= "table" or type(current) ~= "table" then
        return changes
    end
    local before, after = previous.files or {}, current.files or {}
    for relative, now in pairs(after) do
        local was = before[relative]
        if not was then
            local added = lineDelta(nil, now.content)
            changes[#changes + 1] = {
                file = relative,
                status = "added",
                added = now.content and added or nil,
                removed = now.content and 0 or nil,
            }
        elseif was.hash ~= now.hash then
            local countable = was.content ~= nil and now.content ~= nil
            local added, removed = nil, nil
            if countable then
                added, removed = lineDelta(was.content, now.content)
            end
            changes[#changes + 1] = {
                file = relative,
                status = "modified",
                added = added,
                removed = removed,
            }
        end
    end
    for relative, was in pairs(before) do
        if not after[relative] then
            local _, removed = lineDelta(was.content, nil)
            changes[#changes + 1] = {
                file = relative,
                status = "removed",
                added = was.content and 0 or nil,
                removed = was.content and removed or nil,
            }
        end
    end
    table.sort(changes, function(left, right) return left.file < right.file end)
    return changes
end

--- One printable line per changed file.
local function formatChange(change)
    local counts = "changed"
    if change.added and change.removed then
        counts = ("+%d -%d"):format(change.added, change.removed)
    end
    local suffix = ""
    if change.status ~= "modified" then
        suffix = " (" .. change.status .. ")"
    end
    return change.file .. "  " .. counts .. suffix
end

--- Record what a resource looks like now, and say what moved since last time.
--
-- Assigned to the forward declaration above. Called from `reloadResourceByName`
-- rather than from the poll, so that a reload driven from anywhere else -- the
-- file watcher over HTTP, the panel, the console -- reports the same thing the
-- poll would have. Recording happens before the restart, so a reload that
-- outlives a tick is not mistaken for a second change.
--
-- The first sight of a resource reports nothing. There is no previous version
-- to compare against, and announcing every file as "added" the first time
-- anything is watched would be noise, not news.
function noteResourceChanges(resourceName)
    local current = resourceFingerprint(resourceName)
    if not current then
        return {}
    end
    local previous = fingerprints[resourceName]
    fingerprints[resourceName] = current
    if not previous then
        return {}
    end

    local changes = describeChanges(previous, current)
    if #changes == 0 then
        return changes
    end

    for _, change in ipairs(changes) do
        log(("  %s: %s"):format(resourceName, formatChange(change)))
    end
    -- Only to the people allowed to act on it, which is the same gate every
    -- other client-facing part of this uses.
    for _, player in ipairs(getElementsByType("player")) do
        if canManageFromClient(player) then
            triggerClientEvent(
                player, "dev_hotreload:changed", resourceRoot,
                {resource = resourceName, changes = changes}
            )
        end
    end
    return changes
end

local function watchedResources()
    local names = {}
    for _, resourceValue in ipairs(getResources()) do
        local name = getResourceName(resourceValue)
        if BLOCKED_RESOURCES[name:lower()] ~= true and isResourceAllowed(name) then
            names[#names + 1] = name
        end
    end
    return names
end

--- Every resource MTA currently knows, by name.
-- Keyed rather than listed, because Discovery only ever asks whether a name is
-- one it has seen before.
local function currentResourceNames()
    local names = {}
    for _, resourceValue in ipairs(getResources()) do
        names[getResourceName(resourceValue)] = resourceValue
    end
    return names
end

--- Take the fingerprint of everything watched without acting on it.
-- Called when watching starts, so the first tick compares against what was
-- there at the moment the switch was flipped rather than reloading the world.
local function baselineFingerprints()
    fingerprints = {}
    blindTo = {}
    local blind = {}
    for _, name in ipairs(watchedResources()) do
        local print, failure = resourceFingerprint(name)
        fingerprints[name] = print
        if failure then
            blind[#blind + 1] = name
            blindTo[name] = true
        end
    end
    if #blind > 0 then
        -- Said once, at the moment the switch is flipped, rather than every
        -- tick for as long as it stays wrong.
        log(
            "Autoupdate cannot read: " .. table.concat(blind, ", ")
                .. " -- this resource needs the ACL right to look inside"
                .. " another. Run `aclrequest allow "
                .. getResourceName(getThisResource()) .. " all` in the server"
                .. " console, then switch Autoupdate off and on again.",
            2
        )
    end
end

--- Names Autoupdate has been refused, so it stops knocking.
local blindTo = {}

local function pollForChanges()
    for _, name in ipairs(watchedResources()) do
      if not blindTo[name] then
        local current, failure = resourceFingerprint(name)
        if failure then
            -- Refused once is refused every time until the ACL changes, and
            -- MTA logs a warning on every attempt. Asking again twice a second
            -- turns one unfixed permission into an unreadable console.
            blindTo[name] = true
        end
        local previous = fingerprints[name]
        if current and previous and current.digest ~= previous.digest then
            log(("Autoupdate: '%s' changed on disk; reloading"):format(name))
            -- Deliberately not recorded here. The reload records it, and it
            -- has to be the one to do so: overwriting the previous version now
            -- would leave nothing to compare against and the report would come
            -- out empty. Recording still happens before the restart, so a
            -- reload outliving a tick is not seen as a second change.
            reloadResourceByName(name)
        elseif current and not previous then
            -- Newly allowed, or newly discovered. Noted, not reloaded: the
            -- player asked to watch it, not to restart it.
            fingerprints[name] = current
        end
      end
    end
    -- Nothing left to watch means the timer is only there to be refused.
    local watching = false
    for _, name in ipairs(watchedResources()) do
        if not blindTo[name] then
            watching = true
            break
        end
    end
    if not watching and isTimer(autoupdateTimer) then
        killTimer(autoupdateTimer)
        autoupdateTimer = nil
        log("Autoupdate stopped: nothing it may read. Fix the ACL, then"
            .. " switch it off and on again.", 2)
    end
end

local function applyAutoupdate()
    if isTimer(autoupdateTimer) then
        killTimer(autoupdateTimer)
        autoupdateTimer = nil
    end
    if isTimer(discoveryTimer) then
        killTimer(discoveryTimer)
        discoveryTimer = nil
    end
    if not autoupdateEnabled then
        return
    end
    baselineFingerprints()
    autoupdateTimer = setTimer(
        pollForChanges, HOTRELOAD_CONFIG.autoupdateInterval or 2000, 0
    )
    if HOTRELOAD_CONFIG.discoverNewResources ~= false then
        -- Baselined here rather than on the first tick, so that a resource
        -- dropped in before the switch was flipped is still picked up one
        -- interval later instead of being written off as "already there".
        knownResources = currentResourceNames()
        discoveryTimer = setTimer(
            pollForNewResources, HOTRELOAD_CONFIG.discoveryInterval or 10000, 0
        )
    end
end

local function setAutoupdate(enabled)
    autoupdateEnabled = enabled == true
    local saved, saveError = saveManagedState()
    if not saved then
        return false, saveError
    end
    applyAutoupdate()
    log("Autoupdate " .. (autoupdateEnabled and "enabled" or "disabled"))
    return true
end

--- Reload every resource Hot Reload is allowed to touch, now.
local function reloadAllAllowed()
    local reloaded, failed = {}, {}
    for _, name in ipairs(watchedResources()) do
        local ok = reloadResourceByName(name)
        if ok then
            reloaded[#reloaded + 1] = name
        else
            failed[#failed + 1] = name
        end
        -- Whatever its state is now is the state to compare against next.
        fingerprints[name] = resourceFingerprint(name)
    end
    return reloaded, failed
end

local function setResourceStartup(resourceName, startup)
    local normalized, errorCode, errorMessage = validateResourceName(resourceName)
    if not normalized then
        return false, errorCode .. ": " .. errorMessage
    end
    startupOverrides[normalized] = startup == true or nil
    local saved, saveError = saveManagedState()
    if not saved then
        return false, saveError
    end
    return true
end

--- Start what the panel says to start, once this resource is up.
local function startFlaggedResources()
    local started = {}
    for name in pairs(startupOverrides) do
        local target = getResourceFromName(name)
        if target and getResourceState(target) ~= "running" then
            if startResource(target) then
                started[#started + 1] = name
            else
                log(("Startup: could not start '%s'"):format(name), 2)
            end
        end
    end
    if #started > 0 then
        log("Startup: started " .. table.concat(started, ", "))
    end
end

local function setResourceManagement(resourceName, allowed)
    local normalized, errorCode, errorMessage = validateResourceName(resourceName)
    if not normalized then
        return false, errorCode .. ": " .. errorMessage
    end

    local targetResource = getResourceFromName(normalized)
    if not targetResource then
        refreshResources(false)
        targetResource = getResourceFromName(normalized)
    end
    if not targetResource then
        return false, "RESOURCE_NOT_FOUND: MTA did not detect this resource"
    end

    local previous = managedOverrides[normalized]
    managedOverrides[normalized] = allowed
    local saved, saveError = saveManagedState()
    if not saved then
        managedOverrides[normalized] = previous
        return false, "STATE_SAVE_FAILED: " .. saveError
    end
    log(("Resource '%s' is now %s"):format(normalized, allowed and "allowed" or "ignored"))
    return true, normalized .. " is now " .. (allowed and "allowed" or "ignored")
end

--- Start, stop or restart a resource, with none of the reload semantics.
--
-- Separate from Hot Reload on purpose. A reload means "the files changed, pick
-- them up" and only applies to a resource Hot Reload is allowed to touch. This
-- is the plain control a resource manager has, so it works on ignored
-- resources too. What it will not touch is a protected one:
-- `validateResourceName` refuses those, which is what stops this panel from
-- being used to stop this panel.
local function controlResource(resourceName, action)
    local normalized, errorCode, errorMessage = validateResourceName(resourceName)
    if not normalized then
        return false, errorCode .. ": " .. errorMessage
    end
    if action ~= "start" and action ~= "stop" and action ~= "restart" then
        return false, "INVALID_ACTION: unknown resource action"
    end

    local target = getResourceFromName(normalized)
    if not target then
        refreshResources(false)
        target = getResourceFromName(normalized)
    end
    if not target then
        return false, "RESOURCE_NOT_FOUND: MTA did not detect this resource"
    end

    local stateBefore = getResourceState(target)
    local accepted
    if action == "start" then
        if stateBefore == "running" then
            return false, "ALREADY_RUNNING: " .. normalized .. " is already running"
        end
        accepted = startResource(target)
    elseif action == "stop" then
        if stateBefore ~= "running" then
            return false, "NOT_RUNNING: " .. normalized .. " is not running"
        end
        accepted = stopResource(target)
    else
        -- Restarting something that is not running is a start, not an error.
        -- The button says what the player wants to end up with.
        accepted = stateBefore == "running"
            and restartResource(target)
            or startResource(target)
    end

    if not accepted then
        return false, ("ACTION_REFUSED: MTA refused to %s %s"):format(action, normalized)
    end
    log(("%s accepted for '%s' (previous state: %s)"):format(
        action, normalized, tostring(stateBefore)
    ))
    return true, normalized .. ": " .. action
end

--- Pick up resources that appeared after the server read its list.
--
-- Dropping a folder into `resources/` leaves it invisible. MTA reads the list
-- once, a new name is not in it, and so Autoupdate's file poll cannot notice
-- it either -- there is nothing yet to fingerprint. This refreshes the list,
-- then allows and starts whatever turned up, so a newly added resource joins
-- the reload loop without anyone typing `refresh` and `start` by hand.
--
-- Only custom resources are adopted. A refresh also surfaces bundled MTA
-- resources that simply were never loaded, and starting those is not what
-- anyone dropping a folder in was asking for.
--
-- Assigned to the forward declaration above, not a fresh local: `applyAutoupdate`
-- is written before this point and hands the timer this same variable.
function pollForNewResources()
    if not refreshResources(false) then
        log("Discovery: MTA refused to refresh the resource list", 2)
        return
    end

    local present = currentResourceNames()
    if not knownResources then
        knownResources = present
        return
    end

    local adopted, refused, retrying = {}, {}, {}
    for name, resourceValue in pairs(present) do
        if knownResources[name] == nil
            and BLOCKED_RESOURCES[name:lower()] ~= true
            and isCustomResource(resourceValue)
        then
            local allowed, allowMessage = setResourceManagement(name, true)
            if not allowed then
                refused[#refused + 1] = name .. " (" .. tostring(allowMessage) .. ")"
            else
                local started, detail = reloadResourceByName(name)
                if started then
                    discoveryFailures[name] = nil
                    adopted[#adopted + 1] = name
                else
                    local reason = type(detail) == "table"
                        and tostring(detail.message) or "start refused"
                    local attempts = (discoveryFailures[name] or 0) + 1
                    discoveryFailures[name] = attempts
                    if attempts < DISCOVERY_ATTEMPTS then
                        -- Copying a folder is not atomic. MTA can scan it
                        -- between the manifest landing and the scripts that
                        -- manifest names, and then the resource is real but
                        -- broken. Held out of `known` below so the next pass
                        -- sees it as new again and finds the rest of the copy.
                        retrying[name] = true
                    else
                        refused[#refused + 1] = ("%s (%s, gave up after %d)")
                            :format(name, reason, attempts)
                    end
                end
            end
        end
    end

    -- Everything is recorded as seen, except what is still being retried.
    -- Retrying forever would turn one permanently broken meta.xml into an
    -- unreadable console -- the lesson the file poll already learned about the
    -- ACL -- so a name gets a small, finite number of chances and no more.
    knownResources = present
    for name in pairs(retrying) do
        knownResources[name] = nil
    end

    if #adopted > 0 then
        log("Discovery: picked up and started " .. table.concat(adopted, ", "))
    end
    if #refused > 0 then
        log("Discovery: found but could not start " .. table.concat(refused, ", "), 2)
    end
end

addEvent("dev_hotreload:requestCatalog", true)
addEventHandler("dev_hotreload:requestCatalog", resourceRoot, function(refreshMTA)
    if not client or not canManageFromClient(client) then
        if client then
            triggerClientEvent(client, "dev_hotreload:message", resourceRoot, "Missing ACL permission: command.hotreload (you are not logged in as an administrator)", true)
        end
        return
    end
    if refreshMTA == true and not refreshResources(false) then
        triggerClientEvent(client, "dev_hotreload:message", resourceRoot, "MTA could not refresh the resource catalog", true)
        return
    end
    sendCatalogToClient(client)
end)

addEvent("dev_hotreload:setManaged", true)
addEventHandler("dev_hotreload:setManaged", resourceRoot, function(resourceName, allowed)
    if not client or not canManageFromClient(client) then
        if client then
            triggerClientEvent(client, "dev_hotreload:message", resourceRoot, "Missing ACL permission: command.hotreload (you are not logged in as an administrator)", true)
        end
        return
    end
    if type(allowed) ~= "boolean" then
        triggerClientEvent(client, "dev_hotreload:message", resourceRoot, "Invalid resource mode", true)
        return
    end
    local ok, message = setResourceManagement(resourceName, allowed)
    if not ok then
        triggerClientEvent(client, "dev_hotreload:message", resourceRoot, message, true)
        return
    end
    sendCatalogToClient(client, message)
end)

--- The same permission gate the other client-driven changes use.
local function refuseUnlessAdmin(player)
    if player and canManageFromClient(player) then
        return false
    end
    if player then
        triggerClientEvent(
            player, "dev_hotreload:message", resourceRoot,
            "Missing ACL permission: command.hotreload"
                .. " (you are not logged in as an administrator)",
            true
        )
    end
    return true
end

addEvent("dev_hotreload:setAutoupdate", true)
addEventHandler("dev_hotreload:setAutoupdate", resourceRoot, function(enabled)
    if refuseUnlessAdmin(client) then
        return
    end
    if type(enabled) ~= "boolean" then
        triggerClientEvent(
            client, "dev_hotreload:message", resourceRoot,
            "Invalid autoupdate value", true
        )
        return
    end
    local ok, message = setAutoupdate(enabled)
    if not ok then
        triggerClientEvent(
            client, "dev_hotreload:message", resourceRoot, message, true
        )
        return
    end
    sendCatalogToClient(
        client,
        enabled and "Autoupdate on: watching allowed resources"
            or "Autoupdate off"
    )
end)

addEvent("dev_hotreload:setStartup", true)
addEventHandler("dev_hotreload:setStartup", resourceRoot, function(
    resourceName, startup
)
    if refuseUnlessAdmin(client) then
        return
    end
    if type(startup) ~= "boolean" then
        triggerClientEvent(
            client, "dev_hotreload:message", resourceRoot,
            "Invalid startup value", true
        )
        return
    end
    local ok, message = setResourceStartup(resourceName, startup)
    if not ok then
        triggerClientEvent(
            client, "dev_hotreload:message", resourceRoot, message, true
        )
        return
    end
    sendCatalogToClient(
        client,
        startup and ("Startup on for " .. tostring(resourceName))
            or ("Startup off for " .. tostring(resourceName))
    )
end)

addEvent("dev_hotreload:reloadAll", true)
addEventHandler("dev_hotreload:reloadAll", resourceRoot, function()
    if refuseUnlessAdmin(client) then
        return
    end
    local reloaded, failed = reloadAllAllowed()
    local message = ("Reloaded %d resource(s)"):format(#reloaded)
    if #failed > 0 then
        message = message .. (", %d refused: %s"):format(
            #failed, table.concat(failed, ", ")
        )
    end
    sendCatalogToClient(client, message)
end)

addEvent("dev_hotreload:discover", true)
addEventHandler("dev_hotreload:discover", resourceRoot, function()
    if refuseUnlessAdmin(client) then
        return
    end
    local player = client
    local hadBaseline = knownResources ~= nil
    pollForNewResources()
    -- The pass may have started something, and a resource asked to start is
    -- not running yet, so the catalog is read a moment later.
    setTimer(function()
        if isElement(player) then
            sendCatalogToClient(player, hadBaseline
                and "Looked for new resources"
                or "Baselined the resource list; press again after adding one")
        end
    end, 500, 1)
end)

addEvent("dev_hotreload:controlResource", true)
addEventHandler("dev_hotreload:controlResource", resourceRoot, function(
    resourceName, action
)
    if refuseUnlessAdmin(client) then
        return
    end
    -- Captured, because `client` is only itself for the length of this handler
    -- and the catalog is sent from a timer.
    local player = client
    local ok, message = controlResource(resourceName, action)
    if not ok then
        triggerClientEvent(player, "dev_hotreload:message", resourceRoot, message, true)
        return
    end
    -- A resource asked to start is not running yet, so reading the catalog now
    -- would report the state the player just changed. Read it a moment later.
    setTimer(function()
        if isElement(player) then
            sendCatalogToClient(player, message)
        end
    end, 500, 1)
end)

local function handleHotReloadCommand(commandSource, _, action, resourceName)
    action = action and action:lower() or "help"
    if action == "allow" or action == "add" then
        local ok, message = setResourceManagement(resourceName, true)
        reply(commandSource, (ok and "OK: " or "ERROR: ") .. message)
        return
    end
    if action == "ignore" or action == "remove" then
        local ok, message = setResourceManagement(resourceName, false)
        reply(commandSource, (ok and "OK: " or "ERROR: ") .. message)
        return
    end
    if action == "reload" then
        local reloaded, failed = reloadAllAllowed()
        reply(commandSource, ("Reloaded %d resource(s)"):format(#reloaded))
        if #failed > 0 then
            reply(commandSource, "Refused: " .. table.concat(failed, ", "))
        end
        return
    end
    if action == "autoupdate" then
        if resourceName ~= "on" and resourceName ~= "off" then
            reply(commandSource, "Autoupdate is " .. (autoupdateEnabled and "on" or "off")
                .. "; use `autoupdate on` or `autoupdate off`")
            return
        end
        local ok, message = setAutoupdate(resourceName == "on")
        reply(commandSource, ok and ("Autoupdate " .. resourceName)
            or ("ERROR: " .. tostring(message)))
        return
    end
    if action == "refresh" then
        local refreshed = refreshResources(false)
        reply(commandSource, refreshed and "Resource catalog refreshed" or "ERROR: resource catalog refresh failed")
        return
    end
    if action == "discover" then
        -- On demand, whether or not Autoupdate is on. Without a baseline
        -- there is nothing to call new, so take one first and say so rather
        -- than adopting every resource on the server.
        local hadBaseline = knownResources ~= nil
        pollForNewResources()
        reply(commandSource, hadBaseline
            and "Discovery pass done; see the log for what was picked up"
            or "Discovery baselined the current resource list; run it again"
                .. " after adding a resource")
        return
    end
    if action == "status" and resourceName then
        local target = getResourceFromName(resourceName)
        if not target then
            reply(commandSource, "ERROR: resource not found: " .. tostring(resourceName))
            return
        end
        local blocked = BLOCKED_RESOURCES[resourceName:lower()] == true
        local mode = blocked and "blocked" or (isResourceAllowed(resourceName) and "allowed" or "ignored")
        reply(commandSource, ("%s | state=%s | hotreload=%s"):format(resourceName, getResourceState(target), mode))
        return
    end
    if action == "list" then
        local catalog = buildResourceCatalog()
        reply(commandSource, ("MTA detected %d resources:"):format(#catalog))
        for _, item in ipairs(catalog) do
            reply(commandSource, ("%-32s state=%-10s hotreload=%s"):format(item.name, item.state, item.hotReload))
        end
        return
    end

    reply(commandSource, "Commands:")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " list")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " status <resource>")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " allow <resource>")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " ignore <resource>")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " refresh")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " discover")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " reload")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " autoupdate <on|off>")
    reply(commandSource, HOTRELOAD_CONFIG.commandName .. " startup <resource> <on|off>")
end

addCommandHandler(HOTRELOAD_CONFIG.commandName, handleHotReloadCommand, true, false)

addEventHandler("onResourceStart", resourceRoot, function()
    loadManagedState()
    -- The catalog is not complete the instant this starts, and a resource
    -- cannot be started before MTA has seen it, so both wait a moment.
    setTimer(function()
        refreshResources(false)
        startFlaggedResources()
        applyAutoupdate()
    end, 1500, 1)
    log("Development Hot Reload endpoint started; use '" .. HOTRELOAD_CONFIG.commandName .. " list' to manage resources")
end)

addEventHandler("onResourceStop", resourceRoot, function()
    if isTimer(autoupdateTimer) then
        killTimer(autoupdateTimer)
        autoupdateTimer = nil
    end
    if isTimer(discoveryTimer) then
        killTimer(discoveryTimer)
        discoveryTimer = nil
    end
end)

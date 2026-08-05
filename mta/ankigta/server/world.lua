ANKIGTA = ANKIGTA or {}

-- What is standing in the world right now, answered once.
--
-- Three questions have to agree with each other and were being answered in
-- three places: which map the player is looking at, which maps are in play at
-- all, and which live element carries a given Map Entity's identity. The panel
-- knew that the stock Map Editor keeps a second copy of everything and stepped
-- around it; the link path did not, and refused every object as not unique.
--
-- Nothing here reads the store. Rows are passed in, so this module can be
-- loaded and asked on its own, and so a caller that already has the rows does
-- not pay for a second read.

local World = {}

local SUPPORTED_ENTITY_ORDER = ANKIGTA.EntityTypes.order

--- The copy the editor play-tests from.
--
-- `editor_test` is rebuilt from whatever map is open every time Test is
-- pressed and torn down when the test ends, and every map reuses the name --
-- so an entity adopted out of it is a Spatial Link pointing at a copy that
-- stops existing when the test does.
--
-- `editor_dump` is NOT one of these, though ticket 02 said it was and broke
-- linking for it. It is the editor's autosave of the map being edited, and it
-- is that map's name for as long as the map is unsaved: `startUp` opens it on
-- every server start and `newResource` sets `loadedMap` back to it
-- (editor_main/server/saveloadtest_server.lua). Refusing it refused the normal
-- case -- a map the player has not pressed Save As on yet.
--
-- Knowing which of the editor's resources is the play-test is reading it, not
-- changing it (ADR 0025).
local PLAY_TEST_RESOURCE = "editor_test"

--- Is this the resource the editor play-tests from?
function World.isPlayTestResource(name)
    return name == PLAY_TEST_RESOURCE
end

--- Which running resource loaded this element, and under what name.
--
-- The exact inverse of the walk `Store.findMapEntityByRuntimeElement` does to
-- check ownership, so the pair that goes in is the pair that comes back out.
-- An element no resource owns has nothing to be looked up by after a restart.
function World.owningResource(element)
    for _, resource in ipairs(getResources() or {}) do
        local root = getResourceRootElement(resource)
        local ancestor = element
        while isElement(ancestor) do
            if ancestor == root then
                return getResourceName(resource)
            end
            ancestor = getElementParent(ancestor)
        end
    end
    return nil
end

--- Is this element the editor's own drawing of another element, rather than
--- the element itself?
--
-- EDF represents a custom element type with ordinary MTA elements parented to
-- it and stamped `edf:rep`. Counting one of those as a second copy is what
-- made every link fail: inside the editor the count was never one.
--
-- Read off the element rather than asked of `edf`, because that is the whole
-- of `edfIsRepresentation` (`edf/edf.lua`: `return getElementData(elem,
-- "edf:rep")`). Asking the resource needs a `pcall` -- calling an export on a
-- resource that is not running is a script error, and ANKIGTA runs with and
-- without the editor -- and this is asked once per element on paths with a
-- two-second budget. It is also the same answer the client can reach, where
-- the export does not exist at all.
function World.isEditorRepresentation(element)
    return getElementData(element, "edf:rep") == true
end

--- What the stock Map Editor currently holds, or `false` if it is not running.
function World.editor()
    local editor = getResourceFromName("editor_main")
    if not editor or getResourceState(editor) ~= "running" then
        return false
    end
    local dimensionOk, workingDimension = pcall(function()
        return exports.editor_main:getWorkingDimension()
    end)
    local nameOk, mapName = pcall(function()
        return exports.editor_main:getCurrentMapName()
    end)
    return {
        workingDimension = dimensionOk and tonumber(workingDimension) or false,
        mapName = (nameOk and type(mapName) == "string" and mapName ~= "")
            and mapName or false,
    }
end

--- Every ANKIGTA map identity the world carries, by the resource that owns it.
--
-- One walk for every resource rather than one walk each. `owningResource` is
-- itself a walk up the element tree against every running resource, so asking
-- per map turned a reference-sized world into that walk once per map -- and
-- the study refresh asks this every two seconds, not once per F7 open.
function World.mapIdsByOwner()
    local byOwner = {}
    local function collect(kind)
        for _, element in ipairs(getElementsByType(kind)) do
            local mapId = getElementData(element, "ankigtaMapId")
            if type(mapId) == "string" and mapId ~= "" then
                local owner = World.owningResource(element)
                if owner then
                    byOwner[owner] = byOwner[owner] or {}
                    byOwner[owner][mapId] = true
                end
            end
        end
    end
    collect("ankigta_map_identity")
    for _, kind in ipairs(SUPPORTED_ENTITY_ORDER) do
        collect(kind)
    end
    return byOwner
end

--- Every ANKIGTA map identity one resource's own elements carry.
function World.mapIdsForOwner(owner, byOwner)
    local mapIds = (byOwner or World.mapIdsByOwner())[owner]
    return (mapIds and next(mapIds)) and mapIds or false
end

local function playerWorldScore(owner, player)
    if not isElement(player) then
        return 0
    end
    local score = 0
    for _, kind in ipairs(SUPPORTED_ENTITY_ORDER) do
        for _, element in ipairs(getElementsByType(kind)) do
            if World.owningResource(element) == owner
                and getElementDimension(element) == getElementDimension(player)
                and getElementInterior(element) == getElementInterior(player)
            then
                score = score + 1
            end
        end
    end
    return score
end

--- The map the player is actually working in or playing on.
--
-- The stock editor keeps an editable copy under `editor_main` in its working
-- dimension while a play-test may keep the map resource itself running in the
-- ordinary world.  Looking at every element therefore lists the same authored
-- entity twice.  The player's dimension decides which of those two worlds is
-- current; outside the editor, the one running resource of type `map` wins.
function World.currentMapContext(player, storedRows)
    local editor = World.editor()
    if editor and editor.workingDimension and editor.mapName then
        if isElement(player)
            and getElementDimension(player) == editor.workingDimension
        then
            return {
                resourceName = editor.mapName,
                candidateOwner = "editor_main",
                workingDimension = editor.workingDimension,
                mapIds = World.mapIdsForOwner("editor_main"),
            }
        end
    end

    local runningMaps = {}
    for _, candidate in ipairs(getResources() or {}) do
        if getResourceState(candidate) == "running"
            and getResourceInfo(candidate, "type") == "map"
        then
            runningMaps[#runningMaps + 1] = getResourceName(candidate)
        end
    end
    table.sort(runningMaps)
    local runningMap = nil
    if #runningMaps == 1 then
        runningMap = runningMaps[1]
    elseif #runningMaps > 1 then
        local bestScore, tied = 0, false
        for _, resourceName in ipairs(runningMaps) do
            local score = playerWorldScore(resourceName, player)
            if score > bestScore then
                runningMap, bestScore, tied = resourceName, score, false
            elseif score > 0 and score == bestScore then
                tied = true
            end
        end
        if tied then
            runningMap = nil
        end
    end
    if runningMap then
        return {
            resourceName = runningMap,
            candidateOwner = runningMap,
            workingDimension = false,
            mapIds = World.mapIdsForOwner(runningMap),
        }
    end

    -- Disposable/server-only runs have no map manager, but a database that
    -- contains exactly one map still has an unambiguous current scope.  This
    -- is also the useful headless-server answer: one known map is that map;
    -- two known maps without runtime context are deliberately not guessed.
    local onlyResourceName, onlyMapId = nil, nil
    for _, row in ipairs(storedRows or {}) do
        if onlyResourceName == nil then
            onlyResourceName = row.resource_name
            onlyMapId = row.map_id
        elseif row.resource_name ~= onlyResourceName then
            onlyResourceName = false
            break
        elseif row.map_id ~= onlyMapId then
            onlyMapId = false
        end
    end
    if type(onlyResourceName) == "string" and onlyResourceName ~= ""
        and type(onlyMapId) == "string" and onlyMapId ~= ""
    then
        return {
            resourceName = onlyResourceName,
            candidateOwner = onlyResourceName,
            workingDimension = false,
            mapIds = {[onlyMapId] = true},
        }
    end

    return false
end

--- Is the map this resource holds loaded in the world?
--
-- Either its own resource is running, or the stock editor has it open. The
-- editor loads a map's elements into its working dimension without starting
-- the map resource, so asking only about the resource would call the map the
-- player is standing in unloaded.
function World.isMapResourceLoaded(resourceName, editor)
    if type(resourceName) ~= "string" or resourceName == "" then
        return false
    end
    local resource = getResourceFromName(resourceName)
    if resource and getResourceState(resource) == "running" then
        return true
    end
    if editor == nil then
        editor = World.editor()
    end
    return editor ~= false and editor.mapName == resourceName
end

--- The Active Map Set: which stored maps are in play right now.
--
-- A Map Entity takes part when its map is loaded, and nothing else decides it.
-- This replaced a per-map `Include in study` switch, which was the only thing
-- narrowing study at all and which offered a row per map ANKIGTA had ever
-- seen -- including the editor's own scratch resources.
--
-- Unloading a map removes nothing: the Spatial Link stays exactly as it was,
-- and loading the map again brings it back.
function World.loadedMapIds(storedRows)
    local loaded = {}
    local loadedResources = {}
    local editor = World.editor()
    local anyLoaded = false
    for _, row in ipairs(storedRows or {}) do
        local resourceName = row.resource_name
        if type(resourceName) == "string" and resourceName ~= ""
            and loadedResources[resourceName] == nil
        then
            loadedResources[resourceName] =
                World.isMapResourceLoaded(resourceName, editor)
            anyLoaded = anyLoaded or loadedResources[resourceName]
        end
    end
    if not anyLoaded then
        -- Nothing to narrow, and no reason to read the world to find that out.
        return loaded
    end

    local byOwner = World.mapIdsByOwner()
    for _, row in ipairs(storedRows or {}) do
        if loadedResources[row.resource_name] then
            -- A resource whose own elements name ANKIGTA map identities only
            -- brings those maps in: the same `.map` saved again under a new
            -- identity leaves the old one stored but nowhere in the world.
            local restriction = World.mapIdsForOwner(row.resource_name, byOwner)
            if not restriction or restriction[row.map_id] then
                loaded[row.map_id] = true
            end
        end
    end
    return loaded
end

--- Every live element carrying one Map Entity's identity.
--
-- Matched on the ANKIGTA stamp, on the editor's `me:ID`, or on the `id` the
-- `.map` file gave the element, because a Map Entity adopted out of the editor
-- is stored under whichever of those named it -- and a server restart takes
-- the stamp with it while the `.map` file keeps the id.
--
-- The editor's own EDF representations are not elements the player can be
-- taken to and are not second copies of anything.
--
-- `limit` stops the walk early, for the caller that only wants to know whether
-- there is an instance at all. The F7 snapshot asks that once per stored row.
function World.runtimeInstances(mapId, entityId, limit)
    local found = {}
    if type(entityId) ~= "string" or entityId == "" then
        return found
    end
    for _, kind in ipairs(SUPPORTED_ENTITY_ORDER) do
        for _, element in ipairs(getElementsByType(kind)) do
            if limit and #found >= limit then
                return found
            end
            if isElement(element) and not World.isEditorRepresentation(element)
            then
                local stamp = getElementData(element, "ankigtaEntityId")
                local editorId = getElementData(element, "me:ID")
                if stamp == entityId
                    or editorId == entityId
                    or getElementID(element) == entityId
                then
                    local elementMapId =
                        getElementData(element, "ankigtaMapId")
                    if mapId == nil
                        or not elementMapId
                        or elementMapId == mapId
                    then
                        found[#found + 1] = element
                    end
                end
            end
        end
    end
    return found
end

--- Which of several live copies is the one in front of the player.
--
-- The editor works in a dimension of its own while a play-test runs the same
-- map in the ordinary world, so the same authored entity stands in two places
-- at once. The player's own dimension and interior say which of them they are
-- looking at; that is the copy to link, and the copy to be taken to.
--
-- Returns the element and how many copies there were, or `false` and the count
-- when the copies cannot be told apart. Two copies in the player's own world
-- are a genuine duplicate, and guessing between them would write to whichever
-- the walk happened to reach first.
--
-- One copy is not a choice, so the player's world does not veto it: a Map
-- Entity whose only instance is the one the editor is holding is still that
-- entity, and taking the player somewhere it is not is the thing this exists
-- to stop. What the two callers do with a refusal differs on purpose --
-- linking writes, so it refuses and says which; teleport only moves the
-- player, so it goes where the record says instead.
function World.instanceInFrontOf(elements, player)
    local total = #elements
    if total <= 1 then
        return elements[1] or false, total
    end
    if isElement(player) then
        local dimension = getElementDimension(player)
        local interior = getElementInterior(player)
        local here = {}
        for _, element in ipairs(elements) do
            if getElementDimension(element) == dimension
                and getElementInterior(element) == interior
            then
                here[#here + 1] = element
            end
        end
        if #here == 1 then
            return here[1], total
        end
    end
    return false, total
end

--- The one live instance of a Map Entity, from the player's point of view.
function World.runtimeInstance(mapId, entityId, player)
    return World.instanceInFrontOf(
        World.runtimeInstances(mapId, entityId),
        player
    )
end

ANKIGTA.World = World

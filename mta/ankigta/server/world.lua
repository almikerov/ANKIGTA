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
-- so an entity recorded *as* one is a Spatial Link pointing at a copy that
-- stops existing when the test does. That is a statement about where the
-- entity is written down, not about whether the player may link it: the copy
-- they are pointing at is the same entity seen from inside the test, and
-- `playTestOrigin` below is what takes it back out.
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

--- The stock editor itself, which owns the copy of a map it has open.
local EDITOR_RESOURCE = "editor_main"

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

--- Is this element one the editor's play-test is holding?
--
-- Asked of the element rather than of the player's surroundings, because the
-- copy in front of them is what decides -- and it is the same ownership walk
-- the store checks a Map Entity against, so the two cannot disagree.
function World.isPlayTestElement(element)
    if not isElement(element) then
        return false
    end
    return World.isPlayTestResource(World.owningResource(element))
end

--- Every name this element could be recognised by.
--
-- Three, because a Map Entity is stored under whichever of them named it: the
-- ANKIGTA stamp, the editor's `me:ID` where it had to invent one, and the `id`
-- the `.map` file gave the element. A server restart takes the stamp with it
-- while the `.map` keeps the id, and a play-test copy carries the id alone.
--
-- `elementCarriesIdentity` asks the same three questions and deliberately does
-- not come through here: it is asked once per element per stored row inside
-- F7's two-second budget, and it answers by comparing rather than by building
-- a table it then throws away.
local function durableNames(element)
    local candidates = {
        getElementData(element, "ankigtaEntityId"),
        getElementData(element, "me:ID"),
        getElementID(element),
    }
    local names = {}
    -- Counted rather than walked with `ipairs`, which stops at the first hole:
    -- an element carrying only the third of these is the ordinary case inside
    -- a play-test, where the copy has the `.map` id and nothing else.
    for index = 1, 3 do
        local name = candidates[index]
        if type(name) == "string" and name ~= "" then
            names[name] = true
        end
    end
    return names
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

--- Has the editor deleted this element?
--
-- The stock editor's Delete does not destroy anything: it parks the element in
-- `workingDimension + 1` so Undo can bring it back. Nothing that reads the
-- world may treat a parked element as present -- a row for one stays in the
-- list and keeps its Activation Zone drawn at coordinates nothing stands at.
--
-- One answer, here, because three places were deriving it separately and only
-- two of them ever asked.
function World.isDeletedInEditor(element, editor)
    if editor == nil then
        editor = World.editor()
    end
    if not editor or not editor.workingDimension then
        return false
    end
    return getElementDimension(element) == editor.workingDimension + 1
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

--- Every resource holding a copy of one map, added to the ones already known.
--
-- One authored object stands in the world once per copy, and the copies are
-- one entity because one document produced them. Anything deciding whether an
-- element belongs to the map in front of the player has to ask about the map,
-- not about the copy: naming a single copy answers a different question
-- depending on where the player is standing, which is how a row the panel
-- offered from one world could not be edited from another.
--
-- Matched on identity, because that is what the rest of the resource matches
-- on and it is the only answer that survives the map being saved under a new
-- name. A map nobody has linked on carries no ANKIGTA identity at all -- the
-- ordinary state of a map whose objects are only now being taken in -- so the
-- copies the editor makes by construction are named by the caller instead.
--
-- Two documents genuinely answering to one identity is the thing ADR 0011's
-- copy decision exists for, and nothing here pre-empts it: that decision is
-- made about documents, by `MapIdentity`, while this is about which live
-- elements are the map in front of the player. Where both copies are really
-- running, both elements come back and `instanceInFrontOf` refuses to guess
-- between them -- which is the conservative half of the same answer.
function World.ownersOfMapIds(mapIds, owners, byOwner)
    owners = owners or {}
    if not mapIds then
        return owners
    end
    for owner, ownerIds in pairs(byOwner or World.mapIdsByOwner()) do
        for mapId in pairs(ownerIds) do
            if mapIds[mapId] then
                owners[owner] = true
                break
            end
        end
    end
    return owners
end

--- Does this element belong to the map the context is about?
--
-- The one question both walks over the world ask -- the list that offers a row
-- to adopt, and the lookup that resolves the row it offered. They asked it
-- apart, each naming a single copy of the map while doing so, which is how a
-- row offered in one world could not be edited in another.
--
-- Three things it is not, and all three were bought with real breakage. Not
-- EDF's own drawing of an element: it parents one to everything it draws and
-- stamps it `edf:rep`, and counting those made the editor's world refuse every
-- link. Not an element the editor has deleted, which it parks in
-- `workingDimension + 1` rather than destroying, so the row and its ring
-- outlived the object. And not an element of some other map that happens to be
-- running beside this one.
function World.belongsToContext(element, context)
    if not context or not context.owners then
        return false
    end
    if not context.owners[World.owningResource(element)] then
        return false
    end
    if World.isEditorRepresentation(element) then
        return false
    end
    return not (context.workingDimension
        and getElementDimension(element) == context.workingDimension + 1)
end

--- How much of one map stands in the player's own world.
--
-- Over every copy of the map rather than one resource: the map saved under its
-- own name and the copy of it a Test press left running are the same map, and
-- scored apart they were a tie -- which is answered by not guessing, so the
-- player standing in that world had no current map at all.
local function playerWorldScore(owners, player)
    if not isElement(player) then
        return 0
    end
    local score = 0
    for _, kind in ipairs(SUPPORTED_ENTITY_ORDER) do
        for _, element in ipairs(getElementsByType(kind)) do
            if owners[World.owningResource(element)]
                and getElementDimension(element) == getElementDimension(player)
                and getElementInterior(element) == getElementInterior(player)
            then
                score = score + 1
            end
        end
    end
    return score
end

--- One map, as everything that reads the world is handed it.
--
-- Built in one place because the four travel together and the last is derived
-- from the one before it: which resources hold a copy of this map is an answer
-- about its identities, and each caller assembling the table for itself is how
-- one of them could be given the identities and not the copies.
local function mapContext(
    resourceName, workingDimension, mapIds, owners, byOwner
)
    return {
        resourceName = resourceName,
        workingDimension = workingDimension,
        mapIds = mapIds,
        owners = World.ownersOfMapIds(mapIds, owners, byOwner),
    }
end

--- The map the editor has open, seen from wherever the player is standing.
--
-- The map is the same one either way; which copy of it they are looking at is
-- not, and nothing here depends on that any more. `owners` is every resource
-- holding a copy: the editor's own, the one a Test press writes out, the
-- resource the map is saved as, and anything else carrying its identity.
--
-- `workingDimension` is the editor's deleted dimension minus one. It used to
-- be `false` wherever the player was outside the editor's own world, because
-- the walk could only meet `editor_test`'s elements there and none of those
-- can be parked. The walk meets the editor's own copies from every world now,
-- so the question is live wherever the editor has a map open: a parked element
-- is in the bin, whichever world it is being looked at from.
local function editorContext(editor, byOwner)
    byOwner = byOwner or World.mapIdsByOwner()
    -- The identities the editor's own copy carries: the play-test's are a
    -- duplicate of them, and a stored row belongs to the map rather than to
    -- whichever copy of it is being looked at.
    local mapIds = World.mapIdsForOwner(EDITOR_RESOURCE, byOwner)
    local owners = {[EDITOR_RESOURCE] = true, [PLAY_TEST_RESOURCE] = true}
    if type(editor.mapName) == "string" and editor.mapName ~= "" then
        owners[editor.mapName] = true
    end
    return mapContext(
        editor.mapName, editor.workingDimension, mapIds, owners, byOwner
    )
end

--- The map the player is actually working in or playing on.
--
-- The stock editor keeps an editable copy under `editor_main` in its working
-- dimension while the map saved out of it, and a play-test of it, run in the
-- ordinary world.  Looking at every element therefore lists the same authored
-- entity once per copy.  The player's dimension decides which of those worlds
-- they are in; outside the editor, the one map in play wins.
function World.currentMapContext(player, storedRows)
    local editor = World.editor()
    -- Every identity in the world, read once for the whole answer: which maps
    -- are in play is the same question as which resources hold a copy of one.
    local byOwner = World.mapIdsByOwner()
    -- The map the editor has open, and every copy of it standing in the world.
    -- Built once, because the copies answer both questions: which map the
    -- player is standing in, and which elements belong to it.
    local held = (editor and editor.workingDimension and editor.mapName)
        and editorContext(editor, byOwner)
        or false
    if held and isElement(player)
        and getElementDimension(player) == editor.workingDimension
    then
        return held
    end

    -- Every map in play, as a map rather than as a resource. Two of the
    -- resources running as maps can be copies of the one the editor has open
    -- and not maps of their own: `editor_test` is that map written out on the
    -- Test press, and the resource it was saved as is the same document under
    -- its own name. Counted separately they were two maps the player could
    -- equally be standing in -- a tie, which is answered by not guessing, so
    -- an object in a saved map could not be reached from its own world at all.
    local inPlay, editorMap = {}, nil
    for _, candidate in ipairs(getResources() or {}) do
        if getResourceState(candidate) == "running"
            and getResourceInfo(candidate, "type") == "map"
        then
            local name = getResourceName(candidate)
            if held and held.owners[name] then
                if not editorMap then
                    editorMap = {
                        resourceName = held.resourceName,
                        owners = held.owners,
                    }
                    inPlay[#inPlay + 1] = editorMap
                end
            else
                inPlay[#inPlay + 1] = {
                    resourceName = name,
                    owners = {[name] = true},
                }
            end
        end
    end
    table.sort(inPlay, function(left, right)
        return left.resourceName < right.resourceName
    end)
    local current = nil
    if #inPlay == 1 then
        current = inPlay[1]
    elseif #inPlay > 1 then
        local bestScore, tied = 0, false
        for _, entry in ipairs(inPlay) do
            local score = playerWorldScore(entry.owners, player)
            if score > bestScore then
                current, bestScore, tied = entry, score, false
            elseif score > 0 and score == bestScore then
                tied = true
            end
        end
        if tied then
            current = nil
        end
    end
    if current then
        -- The map the editor has open is that map wherever it is being looked
        -- at from. Calling the copy in front of the player a map of its own is
        -- what made every row of the map being tested fall outside the current
        -- map, and what made a link recorded during a test point at a resource
        -- the next Test press rewrites.
        if current == editorMap then
            return held
        end
        return mapContext(
            current.resourceName,
            false,
            World.mapIdsForOwner(current.resourceName, byOwner),
            current.owners,
            byOwner
        )
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
        return mapContext(
            onlyResourceName,
            false,
            {[onlyMapId] = true},
            {[onlyResourceName] = true},
            byOwner
        )
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

--- Does this element answer to a Map Entity's identity?
--
-- Matched on the ANKIGTA stamp, on the editor's `me:ID`, or on the `id` the
-- `.map` file gave the element, because a Map Entity adopted out of the editor
-- is stored under whichever of those named it -- and a server restart takes
-- the stamp with it while the `.map` file keeps the id.
function World.elementCarriesIdentity(element, mapId, entityId)
    local stamp = getElementData(element, "ankigtaEntityId")
    local editorId = getElementData(element, "me:ID")
    if stamp ~= entityId
        and editorId ~= entityId
        and getElementID(element) ~= entityId
    then
        return false
    end
    local elementMapId = getElementData(element, "ankigtaMapId")
    return mapId == nil or not elementMapId or elementMapId == mapId
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
    local editor = World.editor()
    for _, kind in ipairs(SUPPORTED_ENTITY_ORDER) do
        for _, element in ipairs(getElementsByType(kind)) do
            if limit and #found >= limit then
                return found
            end
            if isElement(element)
                and not World.isEditorRepresentation(element)
                and not World.isDeletedInEditor(element, editor)
            then
                if World.elementCarriesIdentity(element, mapId, entityId) then
                    found[#found + 1] = element
                end
            end
        end
    end
    return found
end

--- Every identity the editor is holding in its deleted dimension.
--
-- Delete in the stock editor is `setElementDimension(element, working + 1)`,
-- not a destroy, so the element is still in the world and still answers to the
-- identity. That is the difference between "the player deleted this" and "this
-- map is not loaded", and it is the only signal that tells them apart while
-- the map is open.
--
-- One walk for the whole snapshot rather than one per row. Asked per row it is
-- the entire world re-read once per Map Entity, which on a reference-sized
-- world spent longer than F7's whole two-second budget.
function World.deletedIdentities()
    local deleted = {}
    local editor = World.editor()
    if not editor or not editor.workingDimension then
        return deleted
    end
    for _, kind in ipairs(SUPPORTED_ENTITY_ORDER) do
        for _, element in ipairs(getElementsByType(kind)) do
            if isElement(element)
                and not World.isEditorRepresentation(element)
                and World.isDeletedInEditor(element, editor)
            then
                -- Under every name the identity match would accept, so a row
                -- stored under any of them finds it.
                for name in pairs(durableNames(element)) do
                    deleted[name] = element
                end
            end
        end
    end
    return deleted
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
-- Except where one of them is the play-test's copy of the other, which is not
-- a second entity but the same one seen from inside the test. The editor runs
-- a test in the ordinary world, which is also where a map saved under its own
-- name runs, so the player's own dimension cannot tell those two apart -- and
-- the copy that stops existing when the test does is never the one meant.
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
        if #here > 1 then
            local enduring = {}
            for _, element in ipairs(here) do
                if not World.isPlayTestElement(element) then
                    enduring[#enduring + 1] = element
                end
            end
            -- Only where something outlives the test. Two copies both inside
            -- one are still two copies, and this is not the place that decides
            -- what a play-test copy on its own is worth.
            if #enduring > 0 then
                here = enduring
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

--- The copy of what the player pointed at that outlives a play-test, and the
--- map that owns it.
--
-- A play-test copy is not a different entity. The editor wrote whatever map
-- it had open out to `editor_test` on the Test press, so both copies came out
-- of one document and answer to the same `id` -- and the copy that outlives
-- the test is the editor's. That is the one a Spatial Link has to be made
-- against, and the one whose identity has to be written where the editor will
-- save it.
--
-- Returns `{element = ..., context = ...}` -- the element itself and no map of
-- its own where it is not a play-test copy at all, so a caller that does not
-- care whether a test is running can simply ask. Or `false` and which of the
-- ways there is nothing to resolve it to: refusing is still right where there
-- is nothing else, because a link made against the copy alone points at
-- something that stops existing when the test does.
function World.enduring(element, editor)
    if not World.isPlayTestElement(element) then
        return {element = element, context = false}
    end
    if editor == nil then
        editor = World.editor()
    end
    if not editor or not editor.mapName or not editor.workingDimension then
        return false, "play_test_without_open_map"
    end

    -- What the test is a test *of*. One walk, because both answers come out
    -- of it: the identities the play-test copy carries, and the ones the
    -- editor's copy carries. A test still running against a map the editor
    -- has since closed carries an identity no working copy answers to, and
    -- there is no other copy to adopt against.
    --
    -- Where neither document carries an identity there is nothing to compare,
    -- and the walk below falls back to the `.map` id alone -- which two maps
    -- can share, because the editor generates `object (crate) (1)` from the
    -- type and an ordinal. That gap is not closed here, for two reasons. The
    -- editor suspends itself for the length of a test -- `startWhenLoaded`
    -- returns early and `onClientRender` does nothing while `g_in_test` is set
    -- (editor_main/client/main.lua) -- so a map cannot be opened without
    -- stopping the test, which stops `editor_test` with it. And the obvious
    -- second discriminator is wrong: on the owner's server the play-test's
    -- Sentinel stands 80 metres from the editor's, because somebody drove it,
    -- so matching on the transform would refuse every vehicle a test was used
    -- on.
    local byOwner = World.mapIdsByOwner()
    local playTestIds = World.mapIdsForOwner(PLAY_TEST_RESOURCE, byOwner)
    if playTestIds then
        local editorIds = World.mapIdsForOwner(EDITOR_RESOURCE, byOwner)
        local answered = false
        for mapId in pairs(playTestIds) do
            if editorIds and editorIds[mapId] then
                answered = true
                break
            end
        end
        if not answered then
            return false, "play_test_of_another_map"
        end
    end

    local names = durableNames(element)
    local found = false
    if next(names) then
        for _, candidate in ipairs(getElementsByType(getElementType(element))) do
            if isElement(candidate)
                and not World.isEditorRepresentation(candidate)
                and not World.isDeletedInEditor(candidate, editor)
                and World.owningResource(candidate) == EDITOR_RESOURCE
            then
                for name in pairs(durableNames(candidate)) do
                    if names[name] then
                        if found and found ~= candidate then
                            return false, "play_test_original_not_unique"
                        end
                        found = candidate
                        break
                    end
                end
            end
        end
    end
    if not found then
        -- Deleted in the editor while the test ran, or never in the map the
        -- editor is holding at all.
        return false, "play_test_copy_has_no_original"
    end
    return {
        element = found,
        context = editorContext(editor),
    }
end

ANKIGTA.World = World

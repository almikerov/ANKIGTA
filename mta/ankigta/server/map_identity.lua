ANKIGTA = ANKIGTA or {}

local MapIdentity = {}
local pendingByEntity = {}
local collisionsByEntity = {}
local PENDING_NOTICE_EVENT = "ankigta:pendingMapSaveNotice"
local IDENTITY_CHANGED_EVENT = "ankigta:mapIdentityChanged"
local SUPPORTED_ENTITY_TYPES = ANKIGTA.EntityTypes.supported

local function assignIdentity(mapIdentity, objectElement, mapId, entityId)
    exports.edf:edfSetElementProperty(mapIdentity, "ankigtaMapId", mapId)
    exports.edf:edfSetElementProperty(objectElement, "ankigtaEntityId", entityId)
end

local function entityKey(mapId, entityId)
    return tostring(mapId) .. "\0" .. tostring(entityId)
end

local function readMapFileHash(virtualPath)
    local handle = fileOpen(virtualPath, true)
    if not handle then
        return false
    end
    local contents = fileRead(handle, fileGetSize(handle))
    fileClose(handle)
    return hash("sha256", contents)
end

local function readSavedMapHash(pending)
    return readMapFileHash(pending.mapLocator.virtualPath)
end

--- Which ANKIGTA identities one saved map file carries.
--
-- Read whole rather than searched per entity. A map file is one document: the
-- answer for one Map Entity and the answer for ten thousand of them cost the
-- same parse, and asking per entity made the presence refresh reparse the map
-- once per row -- the whole of F7's two-second budget, several times over, on
-- a reference-sized world.
--
-- `nil` means the file could not be read, which is not the same answer as a
-- file that was read and does not contain something.
local function readMapFileIdentities(virtualPath)
    local root = xmlLoadFile(virtualPath, true)
    if not root then
        return nil
    end
    local mapIds = {}
    local entityIds = {}
    for _, child in ipairs(xmlNodeGetChildren(root)) do
        local childName = xmlNodeGetName(child)
        if childName == "ankigta_map_identity" then
            local mapId = xmlNodeGetAttribute(child, "ankigtaMapId")
            if type(mapId) == "string" and mapId ~= "" then
                mapIds[mapId] = true
            end
        elseif childName == "object"
            or childName == "vehicle"
            or childName == "ped"
        then
            local entityId = xmlNodeGetAttribute(child, "ankigtaEntityId")
            if type(entityId) == "string" and entityId ~= "" then
                entityIds[entityId] = true
            end
        end
    end
    xmlUnloadFile(root)
    return {mapIds = mapIds, entityIds = entityIds}
end

--- The single `<map src>` a resource declares, or `false`.
--
-- One resource, one map document. Read from `meta.xml` rather than assumed,
-- because a `src` may carry a directory (`maps/ticket05.map`) and because the
-- name a map is stored under is not always the name of its file.
local function declaredMapFile(resourceName, cache)
    if type(resourceName) ~= "string" or resourceName == "" then
        return false
    end
    -- Memoised for the caller that asks about every row. `meta.xml` is one
    -- document per resource and the presence refresh walks ten thousand Map
    -- Entities: parsing it per row spent longer than F7's whole budget.
    if cache and cache[resourceName] ~= nil then
        return cache[resourceName]
    end
    local meta = xmlLoadFile(":" .. resourceName .. "/meta.xml", true)
    if not meta then
        if cache then
            cache[resourceName] = false
        end
        return false
    end
    local sources = {}
    for _, child in ipairs(xmlNodeGetChildren(meta)) do
        if xmlNodeGetName(child) == "map" then
            local source = xmlNodeGetAttribute(child, "src")
            if type(source) == "string" and source ~= "" then
                sources[#sources + 1] = source
            end
        end
    end
    xmlUnloadFile(meta)
    local declared = #sources == 1 and sources[1] or false
    if cache then
        cache[resourceName] = declared
    end
    return declared
end

--- Where a stored row's map document actually is.
--
-- `maps.map_name` is supposed to hold the `.map` filename -- that is what
-- `Store.updateMapLocator` writes into it -- but adoption writes the resource
-- name there, because adoption never learns the resource's `<map src>`. So a
-- row adopted through the F7 list produced `:editor_dump/editor_dump`, which
-- is nothing, and every reader of that path silently got "unreadable": the
-- presence refresh could never clear Entity missing, and the collision check
-- compared a resource name against a real filename and called it a copy.
--
-- Asking the resource what its map file is called costs one `meta.xml` read
-- and answers for both shapes, so a row healed by `updateMapLocator` and a row
-- that was never linked resolve the same way.
local function mapFileVirtualPath(row, declaredFiles)
    if type(row) ~= "table" or type(row.resource_name) ~= "string" then
        return nil
    end
    if type(row.map_name) == "string" and row.map_name:sub(-4) == ".map" then
        return ":" .. row.resource_name .. "/" .. row.map_name
    end
    local declared = declaredMapFile(row.resource_name, declaredFiles)
    if not declared then
        return nil
    end
    return ":" .. row.resource_name .. "/" .. declared
end

local function readIdentitiesCached(virtualPath, readFiles)
    if type(virtualPath) ~= "string" then
        return nil
    end
    if readFiles == nil then
        return readMapFileIdentities(virtualPath)
    end
    local contents = readFiles[virtualPath]
    if contents == nil then
        contents = readMapFileIdentities(virtualPath) or false
        readFiles[virtualPath] = contents
    end
    return contents ~= false and contents or nil
end

local function documentCarriesMapId(virtualPath, mapId, readFiles)
    local contents = readIdentitiesCached(virtualPath, readFiles)
    return contents ~= nil and contents.mapIds[mapId] == true
end

local function resolveCurrentMapLocator()
    local mapName = exports.editor_main:getCurrentMapName()
    if type(mapName) ~= "string" or mapName == "" then
        return false, "no_loaded_map"
    end
    local declared = declaredMapFile(mapName)
    if not declared then
        return false, "ambiguous_map_file"
    end
    return {
        resourceName = mapName,
        mapFile = declared,
        virtualPath = ":" .. mapName .. "/" .. declared,
    }
end

--- Is this row's Map Entity in its saved map file?
--
-- `nil` where the file could not be read, so a map that is not there is never
-- mistaken for a map whose entities have gone.
local function mapFileContainsEntity(row, readFiles, currentLocator, declaredFiles)
    if type(row) ~= "table" then
        return nil
    end
    -- Where this map's document is *now*. A map keeps its ANKIGTA identity and
    -- changes resource: the same document is `editor_dump` while it is
    -- unsaved, `editor_test` while it is play-testing, and its own name after
    -- Save As. So the row is looked for in the document that currently carries
    -- its identity, not in the resource it happened to be adopted under.
    local virtualPath = nil
    if currentLocator
        and documentCarriesMapId(
            currentLocator.virtualPath, row.map_id, readFiles
        )
    then
        virtualPath = currentLocator.virtualPath
    elseif ANKIGTA.World.isPlayTestResource(row.resource_name) then
        -- Nothing carries this identity and the only place it was ever written
        -- down is the copy the editor play-tests from, which is rewritten from
        -- whatever map is open the next time Test is pressed. `false` rather
        -- than `nil`: this is a Map Entity that is not coming back, not a map
        -- that could not be opened.
        return false
    else
        virtualPath = mapFileVirtualPath(row, declaredFiles)
    end
    if virtualPath == nil then
        return nil
    end
    local contents = readIdentitiesCached(virtualPath, readFiles)
    if contents == nil then
        return nil
    end
    return contents.mapIds[row.map_id] == true
        and contents.entityIds[row.entity_id] == true
end

function MapIdentity.refreshEntityPresence()
    -- Runtime Instance destruction/unstreaming never changes persistent
    -- presence; only the saved map data can establish Entity missing.
    local rows, readError = ANKIGTA.Store.listMapEntities()
    if not rows then
        return false, readError
    end
    -- Each map file, read once for the whole refresh.
    local readFiles = {}
    -- And each resource's `meta.xml`, read once for the whole refresh.
    local declaredFiles = {}
    local currentLocator = resolveCurrentMapLocator()
    for _, row in ipairs(rows) do
        local present = mapFileContainsEntity(
            row, readFiles, currentLocator, declaredFiles
        )
        -- Only where the stored state disagrees. The refresh runs on every F7
        -- open, and a write per entity is twenty thousand statements to record
        -- that nothing changed.
        local missing = row.entity_state == "entity_missing"
        if present == true and missing then
            ANKIGTA.Store.clearEntityMissing(row.map_id, row.entity_id)
        elseif present == false and not missing then
            ANKIGTA.Store.markEntityMissing(row.map_id, row.entity_id)
        end
    end
    return true
end

--- Where the map the editor currently has open keeps its document.
--
-- Adoption needs it: a row whose `map_name` is a resource name is a row every
-- later reader misreads.
function MapIdentity.currentMapLocator()
    return resolveCurrentMapLocator()
end

--- The map identity elements the editor is holding, minus EDF's own drawings.
--
-- `me:ID` used to be demanded here as well, and it is not a marker of an
-- element the editor manages: `assignID` writes it only when it has to invent
-- an id, so an element the map file already named uniquely never carries one
-- (editor_main/server/IDhandler.lua). Demanding it made a saved and reloaded
-- map look like a map with no identity at all, and the next link would import
-- a second one beside the first.
local function currentMapIdentityElements()
    local result = {}
    for _, element in ipairs(getElementsByType("ankigta_map_identity")) do
        if not ANKIGTA.World.isEditorRepresentation(element) then
            table.insert(result, element)
        end
    end
    return result
end

local function createMapIdentity(player)
    local before = currentMapIdentityElements()
    if #before == 1 then
        return before[1]
    end
    if #before > 1 then
        return false, "ambiguous_map_identity"
    end

    local container = createElement("ankigta_editor_import")
    setElementParent(container, resourceRoot)
    local template = exports.edf:edfCreateElement(
        "ankigta_map_identity",
        player,
        getThisResource(),
        {ankigtaMapId = ""},
        true
    )
    if not isElement(template) then
        destroyElement(container)
        return false, "ankigta_edf_not_loaded"
    end
    setElementParent(template, container)
    local imported = exports.editor_main:import(container)
    destroyElement(container)
    if not imported then
        return false, "editor_import_failed"
    end

    local after = currentMapIdentityElements()
    if #after ~= 1 then
        return false, "imported_map_identity_not_found"
    end
    return after[1]
end

local function readBackSavedMap(pending)
    local root = xmlLoadFile(pending.mapLocator.virtualPath, true)
    if not root then
        return false, "partial_read_back"
    end

    local mapIdentityCount = 0
    local expectedMapIdentityCount = 0
    local expectedEntityIdentityCount = 0
    local selectedEntityIdentityCount = 0
    local duplicateEntityIdentity = false
    local entityIdentityCounts = {}
    for _, child in ipairs(xmlNodeGetChildren(root)) do
        if xmlNodeGetName(child) == "ankigta_map_identity" then
            mapIdentityCount = mapIdentityCount + 1
            if xmlNodeGetAttribute(child, "ankigtaMapId") == pending.mapId then
                expectedMapIdentityCount = expectedMapIdentityCount + 1
            end
        elseif xmlNodeGetName(child) == "object"
            or xmlNodeGetName(child) == "vehicle"
            or xmlNodeGetName(child) == "ped"
        then
            local childEntityId = xmlNodeGetAttribute(child, "ankigtaEntityId")
            if childEntityId and childEntityId ~= "" then
                entityIdentityCounts[childEntityId] =
                    (entityIdentityCounts[childEntityId] or 0) + 1
                if entityIdentityCounts[childEntityId] > 1 then
                    duplicateEntityIdentity = true
                end
            end
            if childEntityId == pending.entityId then
                expectedEntityIdentityCount = expectedEntityIdentityCount + 1
                if xmlNodeGetName(child) == pending.entityType
                    and xmlNodeGetAttribute(child, "id") == pending.editorElementId
                then
                    selectedEntityIdentityCount =
                        selectedEntityIdentityCount + 1
                end
            end
        end
    end
    xmlUnloadFile(root)

    if duplicateEntityIdentity
        or mapIdentityCount > 1
        or expectedMapIdentityCount > 1
        or expectedEntityIdentityCount > 1
    then
        return false, "identity_collision"
    end
    if mapIdentityCount > 1
        or expectedMapIdentityCount > 1
        or expectedEntityIdentityCount > 1
        or selectedEntityIdentityCount > 1
        or duplicateEntityIdentity
    then
        return false, "ambiguous_read_back"
    end
    if mapIdentityCount ~= 1
        or expectedMapIdentityCount ~= 1
        or expectedEntityIdentityCount ~= 1
        or selectedEntityIdentityCount ~= 1
    then
        return false, "partial_read_back"
    end
    return true, "verified"
end

local function attemptReadBack(pending, trigger)
    local verified, outcome = readBackSavedMap(pending)
    pending.lastReadBackTrigger = trigger
    pending.lastReadBackOutcome = outcome
    if not verified then
        if outcome == "identity_collision" then
            collisionsByEntity[entityKey(pending.mapId, pending.entityId)] = pending
            ANKIGTA.Store.markEntityIdentityCollision(
                pending.mapId,
                pending.entityId,
                outcome
            )
        end
        return false, outcome
    end

    pending.verifiedMapSha256 = readSavedMapHash(pending)
    if not pending.verifiedMapSha256 then
        pending.lastReadBackOutcome = "partial_read_back"
        return false, "partial_read_back"
    end
    if pending.newCopy then
        local currentLocator = resolveCurrentMapLocator()
        if currentLocator then
            pending.mapLocator = currentLocator
            ANKIGTA.Store.updateMapLocator(pending.mapId, currentLocator)
        end
        local key = entityKey(pending.mapId, pending.entityId)
        pendingByEntity[key] = nil
        collisionsByEntity[key] = nil
        if isElement(pending.player) then
            triggerEvent(
                IDENTITY_CHANGED_EVENT,
                resourceRoot,
                pending.player,
                pending.mapId,
                pending.entityId
            )
        end
        return true, "unlinked_copy"
    end
    local collision, collisionError = MapIdentity.detectIdentityCollisions(
        pending.mapId,
        pending.entityId,
        pending.mapLocator
    )
    if collisionError then
        pending.lastReadBackOutcome = collisionError
        collisionsByEntity[entityKey(pending.mapId, pending.entityId)] = pending
        return false, collisionError
    end
    if collision then
        pending.lastReadBackOutcome = "identity_collision"
        collisionsByEntity[entityKey(pending.mapId, pending.entityId)] = pending
        return false, "identity_collision"
    end

    local activated, activationError = ANKIGTA.Store.activateSpatialLink(pending)
    if not activated then
        pending.lastReadBackOutcome = activationError
        return false, activationError
    end

    local key = entityKey(pending.mapId, pending.entityId)
    pendingByEntity[key] = nil
    if isElement(pending.player) then
        triggerEvent(
            IDENTITY_CHANGED_EVENT,
            resourceRoot,
            pending.player,
            pending.mapId,
            pending.entityId
        )
    end
    return true, "active"
end

--- Has this map been copied or renamed behind ANKIGTA's back?
--
-- The question is whether the map that carries this identity is still the map
-- ANKIGTA wrote down, and it is answered by comparing where the document lives
-- now against where the store says it lives.
--
-- Both halves used to be compared raw, and both were wrong. `owner.mapFile`
-- comes out of `maps.map_name`, which adoption fills with a RESOURCE NAME
-- while `mapLocator.mapFile` is a real `<map src>` -- so `editor_test` was
-- forever "not" `editor_dump.map` and every adopted row was announced as a
-- copy, with two buttons that could not do anything about it. They are
-- normalised through the same resolver now, so a row that has never been
-- linked and a row healed by `updateMapLocator` compare equal.
local function mapWasCopiedOrRenamed(mapId, owner, mapLocator)
    if not owner then
        return false
    end
    -- The document in front of us says which map it is. If it carries this
    -- identity then it IS this map, whatever resource it happens to be loaded
    -- from -- and being loaded from a different resource is the ordinary case
    -- in the editor, where one document answers to `editor_dump` while it is
    -- unsaved, to `editor_test` while it is play-testing, and to its own name
    -- afterwards. Comparing those names called every one of those a copy.
    if not documentCarriesMapId(mapLocator.virtualPath, mapId) then
        -- No identity in the document to go on, so fall back to where the
        -- store says the map lives, normalised so a stored resource name and a
        -- real `<map src>` are not mistaken for a rename.
        if owner.resourceName ~= mapLocator.resourceName then
            return true
        end
        if owner.mapFile == mapLocator.mapFile then
            return false
        end
        local declared = declaredMapFile(owner.resourceName)
        return declared ~= false and declared ~= mapLocator.mapFile
    end
    -- It does carry the identity. That is a copy only if the map the store
    -- recorded still carries it too -- two documents answering to one identity
    -- is the thing the decision exists for. One document that has moved is a
    -- rename, and needs no decision.
    if owner.resourceName == mapLocator.resourceName then
        return false
    end
    -- Except when the other document is the editor's play-test copy, which is
    -- a duplicate of whatever is open by construction: the editor writes it on
    -- every Test press. On the owner's server both `editor_dump.map` and
    -- `editor_test.map` carried the same `ankigtaMapId`, and counting that as
    -- a copy is the same mistake as counting a resource name as a filename.
    if ANKIGTA.World.isPlayTestResource(owner.resourceName)
        or ANKIGTA.World.isPlayTestResource(mapLocator.resourceName)
    then
        return false
    end
    local recorded = declaredMapFile(owner.resourceName)
    if not recorded then
        return false
    end
    return documentCarriesMapId(
        ":" .. owner.resourceName .. "/" .. recorded,
        mapId
    )
end

function MapIdentity.detectIdentityCollisions(mapId, entityId, mapLocator)
    local pending = pendingByEntity[entityKey(mapId, entityId)]
    local owner, ownerError = ANKIGTA.Store.mapIdentityOwner(mapId, mapLocator)
    if ownerError then
        return false, ownerError
    end
    if not (pending and pending.allowRename)
        and mapWasCopiedOrRenamed(mapId, owner, mapLocator)
    then
        ANKIGTA.Store.markEntityIdentityCollision(
            mapId,
            entityId,
            "copied_resource_or_rename_requires_decision"
        )
        return true
    end
    if pending and pending.entityType ~= nil and pending.entityType ~= "object"
        and not SUPPORTED_ENTITY_TYPES[pending.entityType]
    then
        return true
    end
    return false
end

local function freshIdentity(prefix)
    return prefix .. "-" .. hash(
        "sha256",
        tostring(getTickCount()) .. ":" .. tostring(math.random())
    ):sub(1, 24)
end

function MapIdentity.resolveCopyDecision(mapId, entityId, decision)
    local key = entityKey(mapId, entityId)
    local collision = collisionsByEntity[key]
    if not collision then
        return false, "identity_collision_not_found"
    end
    if decision == "original_or_renamed" then
        local locator, locatorError = resolveCurrentMapLocator()
        if not locator then
            return false, locatorError
        end
        collision.mapLocator = locator
        collision.allowRename = true
        pendingByEntity[key] = collision
        collisionsByEntity[key] = nil
        local activated, activationError = attemptReadBack(
            collision,
            "copy_decision_original_or_renamed"
        )
        if not activated then
            collisionsByEntity[key] = collision
            return false, activationError
        end
        ANKIGTA.Store.clearEntityIdentityCollision(mapId, entityId)
        return {
            state = "active",
            automaticLinkTransfer = true,
            linkTransferred = true,
        }
    end
    if decision ~= "new_copy" then
        return false, "invalid_copy_decision"
    end

    local copyEntries = {collision}
    for otherKey, other in pairs(collisionsByEntity) do
        if otherKey ~= key and other.mapId == mapId then
            table.insert(copyEntries, other)
        end
    end
    for _, entry in ipairs(copyEntries) do
        if not isElement(entry.mapIdentity)
            or not isElement(entry.objectElement)
        then
            return false, "copied_editor_elements_unavailable"
        end
    end

    local newMapId = freshIdentity("map")
    local newCopies = {}
    for _, entry in ipairs(copyEntries) do
        local newEntityId = freshIdentity("entity")
        local copied, copyError = ANKIGTA.Store.createMapEntityCopy(
            mapId,
            entry.entityId,
            newMapId,
            newEntityId
        )
        if not copied then
            return false, copyError
        end
        assignIdentity(
            entry.mapIdentity,
            entry.objectElement,
            newMapId,
            newEntityId
        )
        ANKIGTA.Store.clearEntityIdentityCollision(
            mapId,
            entry.entityId
        )
        collisionsByEntity[entityKey(mapId, entry.entityId)] = nil
        pendingByEntity[entityKey(mapId, entry.entityId)] = nil
        local newKey = entityKey(newMapId, newEntityId)
        local newLocator = entry.mapLocator
        local newBaselineHash = newLocator
            and readMapFileHash(newLocator.virtualPath)
        pendingByEntity[newKey] = {
            state = "Pending Map Save",
            mapId = newMapId,
            entityId = newEntityId,
            entityType = entry.entityType,
            mapLocator = newLocator,
            baselineHash = newBaselineHash,
            lastObservedHash = newBaselineHash,
            player = entry.player,
            objectElement = entry.objectElement,
            mapIdentity = entry.mapIdentity,
            editorElementId = entry.editorElementId,
            newCopy = true,
            study = false,
            activation = false,
            statistics = false,
            markers = false,
        }
        table.insert(newCopies, {
            mapId = newMapId,
            entityId = newEntityId,
        })
    end
    return {
        state = "Pending Map Save",
        mapId = newMapId,
        entityId = newCopies[1].entityId,
        copies = newCopies,
        automaticLinkTransfer = false,
        linkTransferred = false,
    }
end

local function discardPending(pending, reason)
    local key = entityKey(pending.mapId, pending.entityId)
    pendingByEntity[key] = nil
    if isElement(pending.player) then
        triggerClientEvent(
            pending.player,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.pendingDiscarded",
            reason
        )
    end
end

local function observeSavedMap()
    for _, pending in pairs(pendingByEntity) do
        local currentHash = readSavedMapHash(pending)
        if currentHash and currentHash ~= pending.lastObservedHash then
            pending.lastObservedHash = currentHash
            attemptReadBack(pending, "automatic")
        end
    end
end

function MapIdentity.preparePendingMapSave(
    player,
    row,
    mapIdentity,
    objectElement,
    cardIdentity,
    mapLocator,
    baselineHash
)
    local entityType = type(row) == "table" and row.entity_type or false
    if type(row) ~= "table"
        or not isElement(mapIdentity)
        or not isElement(objectElement)
        or not SUPPORTED_ENTITY_TYPES[entityType]
        or getElementType(objectElement) ~= entityType
    then
        return false, "invalid_pending_request"
    end

    local mapId = row.map_id
    local entityId = row.entity_id
    local existingPending = pendingByEntity[entityKey(mapId, entityId)]
    if existingPending then
        return false, "pending_map_save_exists"
    end
    if row.link_state == "active" then
        return false, "entity_already_linked"
    end
    local existingMapId = getElementData(mapIdentity, "ankigtaMapId")
    if existingMapId and existingMapId ~= "" and existingMapId ~= mapId then
        return false, "persistent_map_identity_conflict"
    end

    local existingEntityId = getElementData(objectElement, "ankigtaEntityId")
    if existingEntityId and existingEntityId ~= "" and existingEntityId ~= entityId then
        return false, "persistent_entity_identity_conflict"
    end

    assignIdentity(mapIdentity, objectElement, mapId, entityId)

    local pending = {
        state = "Pending Map Save",
        mapId = mapId,
        entityId = entityId,
        cardIdentity = cardIdentity,
        mapLocator = mapLocator,
        baselineHash = baselineHash,
        lastObservedHash = baselineHash,
        player = player,
        objectElement = objectElement,
        entityType = entityType,
        mapIdentity = mapIdentity,
        -- What the saved `.map` will call this element. `me:ID` is the
        -- editor's copy of it and exists only where the editor had to invent
        -- one, so the element's own id is the answer wherever there is one.
        editorElementId = getElementID(objectElement) ~= ""
            and getElementID(objectElement)
            or getElementData(objectElement, "me:ID"),
        study = false,
        activation = false,
        statistics = false,
        markers = false,
    }
    pendingByEntity[entityKey(mapId, entityId)] = pending
    return pending
end

function MapIdentity.prepareObjectPendingMapSave(player, row, objectElement, cardIdentity)
    if not isElement(objectElement)
        or getElementType(objectElement) ~= "object"
        or ANKIGTA.World.isEditorRepresentation(objectElement)
    then
        return false, "object_not_managed_by_stock_editor"
    end
    if type(cardIdentity) ~= "table"
        or type(cardIdentity.collectionUuid) ~= "string"
        or cardIdentity.collectionUuid == ""
        or tonumber(cardIdentity.cardId) == nil
    then
        return false, "invalid_anki_card_identity"
    end

    local mapLocator, locatorError = resolveCurrentMapLocator()
    if not mapLocator then
        return false, locatorError
    end
    local baselineHash = readMapFileHash(mapLocator.virtualPath)
    if not baselineHash then
        return false, "saved_map_not_readable"
    end
    local mapIdentity, identityError = createMapIdentity(player)
    if not mapIdentity then
        return false, identityError
    end

    return MapIdentity.preparePendingMapSave(
        player,
        row,
        mapIdentity,
        objectElement,
        cardIdentity,
        mapLocator,
        baselineHash
    )
end

--- Hang a card on a Map Entity the store already knows about.
--
-- This is the path the panel's Link button takes, and it refused everything.
-- It counted `object` elements only -- a vehicle, a ped and a marker are Map
-- Entity types and could not be linked at all -- and it demanded exactly one,
-- while the editor keeps its own copy of the map beside the play-test's and
-- EDF keeps a representation beside each element it draws. Inside the editor
-- the count was never one.
--
-- `World` answers which live element that is, the same way the panel's list
-- does, so the two cannot disagree about what the player is looking at.
function MapIdentity.prepareCardLinkForEntity(player, row, cardIdentity)
    if type(row) ~= "table" then
        return false, "invalid_map_entity"
    end
    local entityElement, copies = ANKIGTA.World.runtimeInstance(
        row.map_id,
        row.entity_id,
        player
    )
    if not entityElement then
        if copies == 0 then
            return false, "entity_runtime_not_found: " .. tostring(row.entity_id)
        end
        -- Which entity, because two copies standing in the player's own world
        -- is a question about which one is meant, and answering it by taking
        -- the first would write to whichever the walk happened to reach.
        return false, "entity_runtime_not_unique: " .. tostring(row.entity_id)
            .. " (" .. tostring(copies) .. " copies)"
    end
    local identities = currentMapIdentityElements()
    if #identities > 1 then
        return false, "map_identity_not_unique"
    end
    local mapIdentity = identities[1]
    if not mapIdentity then
        -- Created the same way every other prepare path creates it. Demanding
        -- one already exist is what left the F7 list unable to link anything:
        -- adoption never makes one, so the first link on a fresh map found
        -- none and stopped.
        local created, identityError = createMapIdentity(player)
        if not created then
            return false, identityError
        end
        mapIdentity = created
    end
    local mapLocator, locatorError = resolveCurrentMapLocator()
    if not mapLocator then
        return false, locatorError
    end
    local baselineHash = readMapFileHash(mapLocator.virtualPath)
    if not baselineHash then
        return false, "saved_map_not_readable"
    end
    return MapIdentity.preparePendingMapSave(
        player,
        row,
        mapIdentity,
        entityElement,
        cardIdentity,
        mapLocator,
        baselineHash
    )
end

local function prepareManagedPendingMapSave(
    player,
    row,
    entityElement,
    cardIdentity,
    expectedType
)
    if not isElement(entityElement)
        or getElementType(entityElement) ~= expectedType
        or ANKIGTA.World.isEditorRepresentation(entityElement)
    then
        return false, expectedType .. "_not_managed_by_stock_editor"
    end
    if type(cardIdentity) ~= "table"
        or type(cardIdentity.collectionUuid) ~= "string"
        or cardIdentity.collectionUuid == ""
        or tonumber(cardIdentity.cardId) == nil
    then
        return false, "invalid_anki_card_identity"
    end

    local mapLocator, locatorError = resolveCurrentMapLocator()
    if not mapLocator then
        return false, locatorError
    end
    local baselineHash = readMapFileHash(mapLocator.virtualPath)
    if not baselineHash then
        return false, "saved_map_not_readable"
    end
    local mapIdentity, identityError = createMapIdentity(player)
    if not mapIdentity then
        return false, identityError
    end
    return MapIdentity.preparePendingMapSave(
        player,
        row,
        mapIdentity,
        entityElement,
        cardIdentity,
        mapLocator,
        baselineHash
    )
end

function MapIdentity.prepareVehiclePendingMapSave(
    player,
    row,
    vehicleElement,
    cardIdentity
)
    return prepareManagedPendingMapSave(
        player,
        row,
        vehicleElement,
        cardIdentity,
        "vehicle"
    )
end

function MapIdentity.preparePedPendingMapSave(player, row, pedElement, cardIdentity)
    return prepareManagedPendingMapSave(
        player,
        row,
        pedElement,
        cardIdentity,
        "ped"
    )
end

function MapIdentity.handleEditorElementDestroyed(element)
    for _, pending in pairs(pendingByEntity) do
        if pending.objectElement == element or pending.mapIdentity == element then
            local currentHash = readSavedMapHash(pending)
            if currentHash == pending.baselineHash then
                discardPending(pending, "unsaved_close_or_reload")
                return true, "discarded"
            end

            local verified, outcome = attemptReadBack(pending, "close_or_reload")
            if not verified then
                pending.objectElement = false
                pending.mapIdentity = false
            end
            return verified, outcome
        end
    end
    return false, "not_pending"
end

function MapIdentity.recheckPendingMapSave(mapId, entityId)
    local pending = pendingByEntity[entityKey(mapId, entityId)]
    if not pending then
        return false, "pending_map_save_not_found"
    end
    return attemptReadBack(pending, "manual")
end

--- Rebuild what the store remembers about blocked copy decisions.
--
-- Each one is re-checked rather than believed. A collision is a statement
-- about where the map document is now, and the predicate that wrote these
-- rows compared a resource name against a `.map` filename -- so a build that
-- has fixed the predicate must not carry its old answers forward, or the
-- Original / New copy buttons outlive the bug that raised them.
function MapIdentity.recoverPersistedCollisions()
    local rows, readError = ANKIGTA.Store.listIdentityCollisions()
    if not rows then
        return false, readError
    end
    local currentLocator = resolveCurrentMapLocator()
    for _, row in ipairs(rows) do
        local owner = {
            resourceName = row.resource_name,
            mapFile = row.map_name,
        }
        if currentLocator
            and not mapWasCopiedOrRenamed(row.map_id, owner, currentLocator)
        then
            -- The map is where the store says it is. Whatever raised this was
            -- not a copy.
            ANKIGTA.Store.clearEntityIdentityCollision(
                row.map_id,
                row.entity_id
            )
        else
        local mapIdentity = false
        for _, candidate in ipairs(getElementsByType("ankigta_map_identity")) do
            if getElementData(candidate, "ankigtaMapId") == row.map_id then
                mapIdentity = candidate
                break
            end
        end
        local entityElement = false
        for _, entityType in ipairs({"object", "vehicle", "ped"}) do
            for _, candidate in ipairs(getElementsByType(entityType)) do
                if getElementData(candidate, "ankigtaEntityId") == row.entity_id then
                    entityElement = candidate
                    break
                end
            end
            if entityElement then
                break
            end
        end
        -- Resolved rather than concatenated: a row adopted through the F7
        -- list carries a resource name in `map_name`, and the path built from
        -- it is nothing, so the baseline hash was always false.
        local virtualPath = mapFileVirtualPath(row)
        local mapFile = declaredMapFile(row.resource_name) or row.map_name
        local baselineHash = virtualPath and readMapFileHash(virtualPath)
        collisionsByEntity[entityKey(row.map_id, row.entity_id)] = {
            state = "Identity Collision",
            mapId = row.map_id,
            entityId = row.entity_id,
            entityType = row.entity_type,
            cardIdentity = {
                collectionUuid = row.collection_uuid,
                cardId = row.card_id,
            },
            mapLocator = {
                resourceName = row.resource_name,
                mapFile = mapFile,
                virtualPath = virtualPath,
            },
            baselineHash = baselineHash,
            lastObservedHash = baselineHash,
            verifiedMapSha256 = row.verified_map_sha256,
            editorElementId = entityElement
                and getElementData(entityElement, "me:ID")
                or false,
            lastReadBackOutcome = row.reason,
            objectElement = entityElement,
            mapIdentity = mapIdentity,
        }
        end
    end
    return true
end

function MapIdentity.linkSnapshot(row)
    local metadata = {
        name = row.entity_name or "",
        entityTag = row.entity_tag or "",
        -- `false` is "this entity follows the global", the same answer the row
        -- gives everywhere else. Coercing it to 3 here would make one row say
        -- two different things about its own Activation Zone.
        radius = tonumber(row.radius) or false,
        showRadius = tonumber(row.show_radius) == 1,
    }
    local pending = pendingByEntity[entityKey(row.map_id, row.entity_id)]
    if ANKIGTA.Store.rowIsIdentityCollision(row) then
        return {
            state = "Identity Collision",
            guidanceKey = "guidance.copyBlocked",
            study = false,
            activation = false,
            statistics = false,
            markers = false,
            recheckAvailable = false,
            copyCollision = true,
        }
    end
    if row.entity_state == "entity_missing" then
        -- A row stored against `editor_dump` or `editor_test` is missing for a
        -- reason worth naming: the player made that link deliberately, and may
        -- have made it against an object they still have. Reported as what it
        -- is and left for them to relink or remove -- never deleted here.
        local scratchMap =
            ANKIGTA.World.isPlayTestResource(row.resource_name)
        return {
            state = "Entity missing",
            metadata = metadata,
            editorScratchMap = scratchMap,
            guidanceKey = scratchMap and "guidance.editorScratchMap" or nil,
            relinkAvailable = row.link_state == "active",
            cardIdentity = row.link_state == "active" and {
                collectionUuid = row.collection_uuid,
                cardId = tonumber(row.card_id),
            } or nil,
            study = false,
            activation = false,
            statistics = false,
            markers = false,
            recheckAvailable = false,
        }
    end
    if pending then
        -- Guidance travels as a key, not a sentence: this side has no string
        -- table, and the F7 window that shows the guidance does.
        local guidanceKey = "guidance.saveWithEditor"
        if pending.lastReadBackOutcome == "identity_collision" then
            return {
                state = "Identity Collision",
                guidanceKey = "guidance.copyBlocked",
                study = false,
                activation = false,
                statistics = false,
                markers = false,
                recheckAvailable = false,
                copyCollision = true,
            }
        end
        if pending.lastReadBackOutcome == "partial_read_back"
            or pending.lastReadBackOutcome == "ambiguous_read_back"
        then
            guidanceKey = "guidance.retrySave"
        end
        return {
            state = pending.state,
            guidanceKey = guidanceKey,
            study = pending.study,
            activation = pending.activation,
            statistics = pending.statistics,
            markers = pending.markers,
            recheckAvailable = true,
        }
    end

    if row.link_state == "active" then
        return {
            state = "Active Spatial Link",
            metadata = metadata,
            cardIdentity = {
                collectionUuid = row.collection_uuid,
                cardId = tonumber(row.card_id),
            },
            study = true,
            activation = true,
            statistics = true,
            markers = true,
            recheckAvailable = false,
        }
    end

    if row.link_state == "card_missing" then
        return {
            state = "Card missing",
            metadata = metadata,
            guidanceKey = "guidance.cardMissing",
            cardIdentity = {
                collectionUuid = row.collection_uuid,
                cardId = tonumber(row.card_id),
            },
            study = false,
            activation = false,
            statistics = false,
            markers = false,
            recheckAvailable = false,
            cardMissing = true,
        }
    end

    if row.link_state == "identity_collision" then
        return {
            state = "Identity Collision",
            study = false,
            activation = false,
            statistics = false,
            markers = false,
            recheckAvailable = false,
        }
    end

    return {
        state = "Unlinked",
        metadata = metadata,
        study = false,
        activation = false,
        statistics = false,
        markers = false,
        recheckAvailable = false,
    }
end

ANKIGTA.MapIdentity = MapIdentity

setTimer(observeSavedMap, 500, 0)

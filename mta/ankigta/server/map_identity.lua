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

local function mapFileVirtualPath(row)
    if type(row) ~= "table"
        or type(row.resource_name) ~= "string"
        or type(row.map_name) ~= "string"
    then
        return nil
    end
    return ":" .. row.resource_name .. "/" .. row.map_name
end

--- Is this row's Map Entity in its saved map file?
--
-- `nil` where the file could not be read, so a map that is not there is never
-- mistaken for a map whose entities have gone.
local function mapFileContainsEntity(row, readFiles)
    local virtualPath = mapFileVirtualPath(row)
    if virtualPath == nil then
        return nil
    end
    local contents
    if readFiles ~= nil then
        contents = readFiles[virtualPath]
        if contents == nil then
            contents = readMapFileIdentities(virtualPath) or false
            readFiles[virtualPath] = contents
        end
        if contents == false then
            return nil
        end
    else
        contents = readMapFileIdentities(virtualPath)
        if contents == nil then
            return nil
        end
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
    for _, row in ipairs(rows) do
        local present = mapFileContainsEntity(row, readFiles)
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

local function resolveCurrentMapLocator()
    local mapName = exports.editor_main:getCurrentMapName()
    if type(mapName) ~= "string" or mapName == "" then
        return false, "no_loaded_map"
    end

    local meta = xmlLoadFile(":" .. mapName .. "/meta.xml", true)
    if not meta then
        return false, "map_meta_not_readable"
    end
    local mapSources = {}
    for _, child in ipairs(xmlNodeGetChildren(meta)) do
        if xmlNodeGetName(child) == "map" then
            local source = xmlNodeGetAttribute(child, "src")
            if type(source) == "string" and source ~= "" then
                table.insert(mapSources, source)
            end
        end
    end
    xmlUnloadFile(meta)
    if #mapSources ~= 1 then
        return false, "ambiguous_map_file"
    end
    return {
        resourceName = mapName,
        mapFile = mapSources[1],
        virtualPath = ":" .. mapName .. "/" .. mapSources[1],
    }
end

local function currentMapIdentityElements()
    local result = {}
    for _, element in ipairs(getElementsByType("ankigta_map_identity")) do
        if not exports.edf:edfIsRepresentation(element)
            and getElementData(element, "me:ID")
        then
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

function MapIdentity.detectIdentityCollisions(mapId, entityId, mapLocator)
    local pending = pendingByEntity[entityKey(mapId, entityId)]
    local owner, ownerError = ANKIGTA.Store.mapIdentityOwner(mapId, mapLocator)
    if ownerError then
        return false, ownerError
    end
    if owner and not (pending and pending.allowRename) and (
        owner.resourceName ~= mapLocator.resourceName
        or owner.mapFile ~= mapLocator.mapFile
    ) then
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
        editorElementId = getElementData(objectElement, "me:ID"),
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
        or exports.edf:edfIsRepresentation(objectElement)
        or not getElementData(objectElement, "me:ID")
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

function MapIdentity.prepareCardLinkForEntity(player, row, cardIdentity)
    if type(row) ~= "table" then
        return false, "invalid_map_entity"
    end
    local objectMatches = {}
    for _, objectElement in ipairs(getElementsByType("object")) do
        if getElementData(objectElement, "ankigtaEntityId") == row.entity_id
            and getElementData(objectElement, "me:ID")
        then
            table.insert(objectMatches, objectElement)
        end
    end
    if #objectMatches ~= 1 then
        return false, "entity_runtime_not_unique"
    end
    local identities = currentMapIdentityElements()
    if #identities ~= 1 then
        return false, "map_identity_not_unique"
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
        identities[1],
        objectMatches[1],
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
        or exports.edf:edfIsRepresentation(entityElement)
        or not getElementData(entityElement, "me:ID")
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

function MapIdentity.recoverPersistedCollisions()
    local rows, readError = ANKIGTA.Store.listIdentityCollisions()
    if not rows then
        return false, readError
    end
    for _, row in ipairs(rows) do
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
        local mapFile = row.map_name
        local virtualPath = ":" .. row.resource_name .. "/" .. mapFile
        local baselineHash = readMapFileHash(virtualPath)
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
        ANKIGTA.Store.markIdentityCollision(row.map_id)
    end
    return true
end

function MapIdentity.linkSnapshot(row)
    local coronaColour, coronaOpacity = ANKIGTA.Store.coronaOf(row)
    local metadata = {
        name = row.entity_name or "",
        entityTag = row.entity_tag or "",
        radius = tonumber(row.radius) or 3,
        showCorona = tonumber(row.show_radius) == 1,
        coronaColour = coronaColour,
        coronaOpacity = coronaOpacity,
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
        return {
            state = "Entity missing",
            metadata = metadata,
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
        -- Guidance travels as a key, not a sentence: this side has no
        -- language, and the F7 window that shows it does.
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

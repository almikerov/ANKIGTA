ANKIGTA = ANKIGTA or {}

local STUDY_RIGHT = "resource.ankigta.study"
local F7_REQUEST_EVENT = "ankigta:requestF7"
local F7_SNAPSHOT_EVENT = "ankigta:f7Snapshot"
local F7_DENIED_EVENT = "ankigta:f7Denied"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"
local SETTINGS_EVENT = "ankigta:settings"
local AUTHORIZATION_REQUEST_EVENT = "ankigta:requestAuthorization"
local RECHECK_REQUEST_EVENT = "ankigta:recheckPendingMapSave"
local SETTINGS_REQUEST_EVENT = "ankigta:requestSettings"
local SETTINGS_SNAPSHOT_EVENT = "ankigta:settingsSnapshot"
local SETTINGS_UPDATE_EVENT = "ankigta:updateSetting"
local SETTINGS_REJECTED_EVENT = "ankigta:settingRejected"
local COPY_DECISION_REQUEST_EVENT = "ankigta:resolveMapCopyDecision"
local PENDING_NOTICE_EVENT = "ankigta:pendingMapSaveNotice"
local IDENTITY_CHANGED_EVENT = "ankigta:mapIdentityChanged"
local CARD_PICKER_REQUEST_EVENT = "ankigta:requestCardPicker"
local CARD_PICKER_SNAPSHOT_EVENT = "ankigta:cardPickerSnapshot"
local CARD_STATE_REFRESH_REQUEST_EVENT = "ankigta:refreshCardState"
local LINK_CARD_REQUEST_EVENT = "ankigta:linkCardToEntity"
local START_STUDY_REQUEST_EVENT = "ankigta:startStudy"
local REBUILD_STUDY_REQUEST_EVENT = "ankigta:rebuildStudy"
local PAUSE_STUDY_REQUEST_EVENT = "ankigta:pauseStudy"
local STOP_STUDY_REQUEST_EVENT = "ankigta:stopStudy"
local CANCEL_STUDY_REQUEST_EVENT = "ankigta:cancelStudyRebuild"
local RELINK_ENTITY_REQUEST_EVENT = "ankigta:relinkEntity"
local UNLINK_CARD_REQUEST_EVENT = "ankigta:unlinkCardFromEntity"
local REPLACE_CARD_REQUEST_EVENT = "ankigta:replaceCardForEntity"
local SESSION_INVALIDATED_EVENT = "ankigta:sessionInvalidated"
local CARD_STATE_REFRESHED_EVENT = "ankigta:cardStateRefreshed"
local UNDO_REQUEST_EVENT = "ankigta:undo"
local REDO_REQUEST_EVENT = "ankigta:redo"
local REVIEW_OPEN_EVENT = "ankigta:openReviewMode"
local REVIEW_SIDE_EVENT = "ankigta:reviewSide"
local REVIEW_REVEAL_REQUEST_EVENT = "ankigta:revealAnswer"
local REVIEW_RATE_REQUEST_EVENT = "ankigta:submitRating"
local REVIEW_RESULT_EVENT = "ankigta:reviewResult"
local REVIEW_CLOSED_EVENT = "ankigta:reviewClosed"
local RENDER_ISSUED_EVENT = "ankigta:renderIssued"
local REVIEW_RETURN_REQUEST_EVENT = "ankigta:returnToCard"
local PICK_ENTITY_REQUEST_EVENT = "ankigta:pickEntity"
local PICK_ENTITY_RESULT_EVENT = "ankigta:pickEntityResult"
-- Ticket 05 uses this only to observe a disposable map-created element.
-- Persistent Map Entity identity remains the responsibility of ticket 06.
local RUNTIME_REFERENCE_ID = "ankigta-ticket05-runtime"

local runtimeInstance = nil

local SUPPORTED_ENTITY_TYPES = {
    object = true,
    vehicle = true,
    ped = true,
}

local function denial(category)
    return {
        category = category,
    }
end

local function playerAuthorization(player)
    if not isElement(player) or getElementType(player) ~= "player" then
        return false, denial("authentication_required")
    end

    local account = getPlayerAccount(player)
    if not account or isGuestAccount(account) then
        return false, denial("authentication_required")
    end

    if not hasObjectPermissionTo(player, STUDY_RIGHT, false) then
        return false, denial("forbidden")
    end

    return true
end

local function runtimeSnapshot()
    if not isElement(runtimeInstance) then
        return {
            available = false,
            streamed = false,
        }
    end

    return {
        available = true,
        streamed = false,
        referenceId = RUNTIME_REFERENCE_ID,
    }
end

local function entityContract(row)
    local link = ANKIGTA.MapIdentity.linkSnapshot(row)
    return {
        mapEntity = {
            mapId = row.map_id,
            entityId = row.entity_id,
            type = row.entity_type,
            model = tonumber(row.model),
            map = {
                resourceName = row.resource_name,
                mapName = row.map_name,
            },
            display = {
                name = row.entity_name or "",
                entityTag = row.entity_tag or "",
                radius = tonumber(row.radius) or 3,
                showRadius = tonumber(row.show_radius) == 1,
            },
            authored = {
                position = {
                    x = tonumber(row.authored_x),
                    y = tonumber(row.authored_y),
                    z = tonumber(row.authored_z),
                },
                rotation = {
                    x = tonumber(row.rotation_x),
                    y = tonumber(row.rotation_y),
                    z = tonumber(row.rotation_z),
                },
                world = {
                    interior = tonumber(row.interior),
                    dimension = tonumber(row.dimension),
                },
            },
        },
        runtimeInstance = runtimeSnapshot(),
        metadata = {
            name = row.entity_name or "",
            entityTag = row.entity_tag or "",
            radius = tonumber(row.radius) or 3,
            showRadius = tonumber(row.show_radius) == 1,
        },
        link = link,
        copyCollision = link.copyCollision == true,
    }
end

local function buildF7Snapshot()
    local refreshed, refreshError = ANKIGTA.MapIdentity.refreshEntityPresence()
    if not refreshed and refreshError ~= "entity_read_failed" then
        return false, denial(refreshError or "entity_presence_refresh_failed")
    end
    local rows, readError = ANKIGTA.Store.listMapEntities()
    if not rows then
        return false, denial(readError or "storage_unavailable")
    end

    local entities = {}
    for _, row in ipairs(rows) do
        table.insert(entities, entityContract(row))
    end

    local history = ANKIGTA.Store.historyStatus()
    if not history then
        history = {
            entryCount = 0,
            canUndo = false,
            canRedo = false,
            limit = 100,
        }
    end

    return {
        contractVersion = 1,
        visible = true,
        cardPicker = {
            enabled = true,
            deckFilterScope = "initial_card_picker_filter",
        },
        entities = entities,
        history = history,
    }
end

function relinkEntity(
    player,
    sourceMapId,
    sourceEntityId,
    targetMapId,
    targetEntityId
)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local source, sourceError = ANKIGTA.Store.getMapEntity(
        sourceMapId,
        sourceEntityId
    )
    if not source then
        return false, sourceError
    end
    local target, targetError = ANKIGTA.Store.getMapEntity(
        targetMapId,
        targetEntityId
    )
    if not target then
        return false, targetError
    end
    local sourceLink = ANKIGTA.MapIdentity.linkSnapshot(source)
    local targetLink = ANKIGTA.MapIdentity.linkSnapshot(target)
    if sourceLink.state ~= "Entity missing" then
        return false, "source_entity_not_missing"
    end
    if targetLink.state ~= "Unlinked" then
        return false, "target_entity_not_unlinked"
    end
    return ANKIGTA.Store.relinkEntity({
        sourceMapId = sourceMapId,
        sourceEntityId = sourceEntityId,
        targetMapId = targetMapId,
        targetEntityId = targetEntityId,
    })
end

function getStoreStatus()
    return ANKIGTA.Store.status()
end

function prepareObjectPendingMapSave(player, objectElement, collectionUuid, cardId)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local row, readError = ANKIGTA.Store.singleMapEntity()
    if not row then
        return false, readError
    end
    return ANKIGTA.MapIdentity.prepareObjectPendingMapSave(
        player,
        row,
        objectElement,
        {
            collectionUuid = collectionUuid,
            cardId = cardId,
        }
    )
end

function prepareVehiclePendingMapSave(player, vehicleElement, collectionUuid, cardId)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local row, readError =
        ANKIGTA.Store.singleMapEntity("vehicle", vehicleElement)
    if not row then
        return false, readError
    end
    return ANKIGTA.MapIdentity.prepareVehiclePendingMapSave(
        player,
        row,
        vehicleElement,
        {
            collectionUuid = collectionUuid,
            cardId = cardId,
        }
    )
end

function preparePedPendingMapSave(player, pedElement, collectionUuid, cardId)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local row, readError = ANKIGTA.Store.singleMapEntity("ped", pedElement)
    if not row then
        return false, readError
    end
    return ANKIGTA.MapIdentity.preparePedPendingMapSave(
        player,
        row,
        pedElement,
        {
            collectionUuid = collectionUuid,
            cardId = cardId,
        }
    )
end

function linkCardToEntity(
    player,
    mapId,
    entityId,
    cardIdentity
)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    if type(cardIdentity) ~= "table"
        or type(cardIdentity.collectionUuid) ~= "string"
        or tonumber(cardIdentity.cardId) == nil
    then
        return false, "invalid_anki_card_identity"
    end
    local row, readError = ANKIGTA.Store.getMapEntity(mapId, entityId)
    if not row then
        return false, readError
    end
    local link = ANKIGTA.MapIdentity.linkSnapshot(row)
    if link.state == "Pending Map Save" then
        return false, "pending_map_save"
    end
    if link.state == "Identity Collision" then
        return false, "identity_collision"
    end
    if link.state == "Active Spatial Link" then
        return false, "entity_already_linked"
    end
    if link.state == "Card missing" then
        return false, "card_missing_requires_replace"
    end
    local linked, linkError =
        ANKIGTA.MapIdentity.prepareCardLinkForEntity(
            player,
            row,
            cardIdentity
        )
    if not linked then
        return false, linkError
    end
    return linked
end

local function cardIdentityFromRow(row)
    if type(row) ~= "table"
        or type(row.collection_uuid) ~= "string"
        or tonumber(row.card_id) == nil
    then
        return false
    end
    return {
        collectionUuid = row.collection_uuid,
        cardId = tonumber(row.card_id),
    }
end

function unlinkCardFromEntity(player, mapId, entityId, cardIdentity)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local row, readError = ANKIGTA.Store.getMapEntity(mapId, entityId)
    if not row then
        return false, readError
    end
    local oldIdentity = cardIdentityFromRow(row)
    local unlinked, unlinkError = ANKIGTA.Store.unlinkSpatialLink({
        mapId = mapId,
        entityId = entityId,
        expectedCardIdentity = cardIdentity,
    })
    if not unlinked then
        return false, unlinkError
    end
    return {
        state = "Unlinked",
        oldCardIdentity = oldIdentity,
    }
end

function replaceCardForEntity(
    player,
    mapId,
    entityId,
    oldCardIdentity,
    newCardIdentity
)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local replaced, replaceError = ANKIGTA.Store.replaceSpatialLink({
        mapId = mapId,
        entityId = entityId,
        oldCardIdentity = oldCardIdentity,
        newCardIdentity = newCardIdentity,
    })
    if not replaced then
        return false, replaceError
    end
    return replaced
end

function validatePickEntity(player, entityElement, mode)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    if not isElement(entityElement) then
        return false, "entity_not_an_element"
    end
    local entityType = getElementType(entityElement)
    if not SUPPORTED_ENTITY_TYPES[entityType] then
        return false, "target_type_not_supported"
    end
    if exports.edf:edfIsRepresentation(entityElement) then
        return false, "entity_not_managed"
    end
    local persistentId = getElementData(entityElement, "ankigtaEntityId")
    local editorId = getElementData(entityElement, "me:ID")
    if type(persistentId) ~= "string" or persistentId == ""
        or type(editorId) ~= "string" or editorId == ""
    then
        return false, "entity_not_managed"
    end
    if isElementStreamedIn and not isElementStreamedIn(entityElement) then
        return false, "entity_not_streamed"
    end

    local row, readError =
        ANKIGTA.Store.findMapEntityByRuntimeElement(entityElement)
    if not row then
        return false, readError or "map_entity_not_loaded"
    end
    local canonical, canonicalError =
        ANKIGTA.Store.getMapEntity(row.map_id, row.entity_id)
    if not canonical then
        return false, canonicalError or "map_entity_not_loaded"
    end
    row = canonical
    if mode == "relink"
        and (
            row.link_state == "active"
            or row.link_state == "Pending Map Save"
            or ANKIGTA.Store.isIdentityCollision(row.map_id, row.entity_id)
        )
    then
        return false, "relink_target_already_linked"
    end
    return {
        mapId = row.map_id,
        entityId = row.entity_id,
        entityType = row.entity_type,
        purpose = mode == "relink" and "relink" or "pick",
    }
end

local function sendAuthorization(player)
    local authorized = playerAuthorization(player)
    triggerClientEvent(
        player,
        AUTHORIZATION_EVENT,
        resourceRoot,
        authorized == true
    )
    if authorized == true then
        -- The world and study settings the server owns. The client's own
        -- settings are not in here: it owns those and reads them locally.
        triggerClientEvent(
            player,
            SETTINGS_EVENT,
            resourceRoot,
            ANKIGTA.SettingsStore.owned()
        )
    end
end

local function activeCardIdentities()
    local rows = ANKIGTA.Store.listMapEntities()
    if type(rows) ~= "table" then
        return false, "storage_unavailable"
    end
    local identities = {}
    local seen = {}
    for _, row in ipairs(rows) do
        if row.link_state == "active"
            and type(row.collection_uuid) == "string"
            and tonumber(row.card_id) ~= nil
        then
            local cardId = tonumber(row.card_id)
            local key = row.collection_uuid .. ":" .. tostring(cardId)
            if not seen[key] then
                seen[key] = true
                table.insert(identities, {
                    collectionUuid = row.collection_uuid,
                    cardId = cardId,
                })
            end
        end
    end
    return identities
end

local function requestStudyStart(player, rebuild, allowEarlyReview)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    -- The early-review policy is the server's (ADR 0014). The request carries
    -- what the player asked for; the setting is what actually governs, so the
    -- request changes the setting and then the setting is read back. A study
    -- session started after a restart uses the same policy as the one before.
    if type(allowEarlyReview) == "boolean" then
        ANKIGTA.SettingsStore.set("allowEarlyReview", allowEarlyReview)
    end
    allowEarlyReview = ANKIGTA.SettingsStore.get("allowEarlyReview") == true
    local identities, identityError = activeCardIdentities()
    if not identities then
        return false, identityError
    end
    if rebuild then
        return ANKIGTA.CompanionGateway.requestSessionRebuild(
            player,
            identities,
            allowEarlyReview == true
        )
    end
    return ANKIGTA.CompanionGateway.requestSessionStart(
        player,
        identities,
        allowEarlyReview == true
    )
end

local function requestStudyCleanup(player, stop)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    if stop then
        return ANKIGTA.CompanionGateway.requestSessionStop(player)
    end
    return ANKIGTA.CompanionGateway.requestSessionPause(player)
end

local function requestStudyCancel(player)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    return ANKIGTA.CompanionGateway.requestSessionCancel(player)
end

local function sendF7Snapshot(player)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        triggerClientEvent(
            player,
            F7_DENIED_EVENT,
            resourceRoot,
            authorizationError
        )
        return false
    end

    local snapshot, snapshotError = buildF7Snapshot()
    if not snapshot then
        triggerClientEvent(
            player,
            F7_DENIED_EVENT,
            resourceRoot,
            snapshotError
        )
        return false
    end

    triggerClientEvent(
        player,
        F7_SNAPSHOT_EVENT,
        resourceRoot,
        snapshot
    )
    return true
end

local function changeHistory(player, direction)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local changed, outcome
    if direction == "undo" then
        changed, outcome = ANKIGTA.Store.undo()
    else
        changed, outcome = ANKIGTA.Store.redo()
    end
    if not changed then
        triggerClientEvent(
            player,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            direction == "undo"
                and "notice.undoUnavailable"
                or "notice.redoUnavailable",
            outcome
        )
        return false, outcome
    end
    local refresh = sendF7Snapshot
    refresh(player)
    return true, outcome
end

function undoChange(player)
    return changeHistory(player, "undo")
end

function redoChange(player)
    return changeHistory(player, "redo")
end

local function invalidateStudyDependents(
    player,
    oldIdentity,
    newIdentity,
    reason
)
    -- A future session/review coordinator consumes this server-only seam.
    triggerEvent(SESSION_INVALIDATED_EVENT,
        resourceRoot,
        player,
        oldIdentity or false,
        newIdentity or false,
        reason
    )
end

local function recheckPendingMapSave(player, mapId, entityId)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local verified, outcome =
        ANKIGTA.MapIdentity.recheckPendingMapSave(mapId, entityId)
    -- The notice travels as a key: the player's language is a client-owned
    -- setting, so the side that renders it is the side that translates it.
    triggerClientEvent(
        player,
        PENDING_NOTICE_EVENT,
        resourceRoot,
        verified and "notice.pendingActivated" or "notice.pendingNotConfirmed",
        outcome
    )
    if not verified then
        sendF7Snapshot(player)
    end
    return verified, outcome
end

function resolveMapCopyDecision(player, mapId, entityId, decision)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    -- "new_copy" deliberately creates fresh IDs with no automatic link transfer:
    -- automaticLinkTransfer = false.
    local resolved, outcome = ANKIGTA.MapIdentity.resolveCopyDecision(
        mapId,
        entityId,
        decision
    )
    triggerClientEvent(
        player,
        PENDING_NOTICE_EVENT,
        resourceRoot,
        resolved
            and "notice.copyDecisionApplied"
            or "notice.copyDecisionFailed",
        outcome
    )
    local refresh = sendF7Snapshot
    refresh(player)
    return resolved, outcome
end

addEvent(IDENTITY_CHANGED_EVENT, false)
addEventHandler(IDENTITY_CHANGED_EVENT, resourceRoot, function(player)
    if source == resourceRoot and playerAuthorization(player) then
        sendF7Snapshot(player)
    end
end)

addEvent(SESSION_INVALIDATED_EVENT, false)
addEvent(CARD_STATE_REFRESHED_EVENT, false)
addEventHandler(CARD_STATE_REFRESHED_EVENT, resourceRoot, function(
    player,
    cardIdentity,
    present,
    changed
)
    if source ~= resourceRoot or not playerAuthorization(player) then
        return
    end
    if changed == true then
        invalidateStudyDependents(
            player,
            cardIdentity,
            present == true and cardIdentity or false,
            present == true and "card_state_present" or "card_missing"
        )
        sendF7Snapshot(player)
    end
end)

addEvent(F7_REQUEST_EVENT, true)
addEventHandler(F7_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    sendF7Snapshot(client)
end)

--- Everything the server owns, for the client's settings panel.
--
-- Only what the server owns: the client's own settings never leave its machine,
-- so the server has no value to answer with and does not invent one (ADR 0014).
local function sendSettingsSnapshot(player)
    triggerClientEvent(
        player,
        SETTINGS_SNAPSHOT_EVENT,
        resourceRoot,
        {
            values = ANKIGTA.SettingsStore.owned(),
            maps = ANKIGTA.SettingsStore.mapPreferences(),
        }
    )
end

addEvent(SETTINGS_REQUEST_EVENT, true)
addEventHandler(SETTINGS_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    local authorized, authorizationError = playerAuthorization(client)
    if not authorized then
        triggerClientEvent(
            client,
            F7_DENIED_EVENT,
            resourceRoot,
            authorizationError
        )
        return
    end
    sendSettingsSnapshot(client)
end)

addEvent(SETTINGS_UPDATE_EVENT, true)
addEventHandler(SETTINGS_UPDATE_EVENT, resourceRoot, function(key, value, mapId)
    if not client or source ~= resourceRoot then
        return
    end
    local authorized, authorizationError = playerAuthorization(client)
    if not authorized then
        triggerClientEvent(
            client,
            F7_DENIED_EVENT,
            resourceRoot,
            authorizationError
        )
        return
    end

    -- Checked again here. The client validated for the user's sake, so a bad
    -- value is caught before it leaves the machine; a value arriving over the
    -- wire has been checked by nothing this side owns.
    local stored, reason
    if key == "includeInStudy" and mapId ~= nil then
        -- The only per-map setting: it names the map it is about.
        stored, reason = ANKIGTA.SettingsStore.setMapIncludeInStudy(
            mapId,
            value
        )
    else
        stored, reason = ANKIGTA.SettingsStore.set(key, value)
    end
    if not stored then
        triggerClientEvent(
            client,
            SETTINGS_REJECTED_EVENT,
            resourceRoot,
            key,
            reason
        )
        return
    end
    sendSettingsSnapshot(client)
end)

addEvent(RECHECK_REQUEST_EVENT, true)
addEventHandler(RECHECK_REQUEST_EVENT, resourceRoot, function(mapId, entityId)
    if not client or source ~= resourceRoot then
        return
    end
    recheckPendingMapSave(client, mapId, entityId)
end)

addEvent(COPY_DECISION_REQUEST_EVENT, true)
addEventHandler(COPY_DECISION_REQUEST_EVENT, resourceRoot, function(
    mapId,
    entityId,
    decision
)
    if not client or source ~= resourceRoot then
        return
    end
    resolveMapCopyDecision(client, mapId, entityId, decision)
end)

addEvent(CARD_PICKER_REQUEST_EVENT, true)
addEventHandler(CARD_PICKER_REQUEST_EVENT, resourceRoot, function(
    query,
    deckFilter,
    page,
    pageSize
)
    if not client or source ~= resourceRoot then
        return
    end
    local authorized, authorizationError = playerAuthorization(client)
    if not authorized then
        triggerClientEvent(
            client,
            F7_DENIED_EVENT,
            resourceRoot,
            authorizationError
        )
        return
    end
    local requested, requestError = ANKIGTA.CompanionGateway.requestCardPicker(
        client,
        query,
        deckFilter,
        page,
        pageSize
    )
    if not requested then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.cardPickerUnavailable",
            requestError
        )
    end
end)

addEvent(CARD_STATE_REFRESH_REQUEST_EVENT, true)
addEventHandler(CARD_STATE_REFRESH_REQUEST_EVENT, resourceRoot, function(
    cardIdentity
)
    if not client or source ~= resourceRoot then
        return
    end
    local authorized, authorizationError = playerAuthorization(client)
    if not authorized then
        triggerClientEvent(
            client,
            F7_DENIED_EVENT,
            resourceRoot,
            authorizationError
        )
        return
    end
    ANKIGTA.CompanionGateway.requestCardState(client, cardIdentity)
end)

addEvent(LINK_CARD_REQUEST_EVENT, true)
addEventHandler(LINK_CARD_REQUEST_EVENT, resourceRoot, function(
    mapId,
    entityId,
    cardIdentity
)
    if not client or source ~= resourceRoot then
        return
    end
    local linked, linkError = linkCardToEntity(
        client,
        mapId,
        entityId,
        cardIdentity
    )
    if not linked then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.linkFailed",
            linkError
        )
    else
        local linkedRow = ANKIGTA.Store.getMapEntity(mapId, entityId)
        invalidateStudyDependents(
            client,
            false,
            linkedRow and cardIdentityFromRow(linkedRow) or cardIdentity,
            "link"
        )
        local refresh = sendF7Snapshot
        refresh(client)
    end
end)

addEvent(START_STUDY_REQUEST_EVENT, true)
addEventHandler(START_STUDY_REQUEST_EVENT, resourceRoot, function(
    allowEarlyReview
)
    if not client or source ~= resourceRoot then
        return
    end
    local requested, requestError = requestStudyStart(
        client,
        false,
        allowEarlyReview
    )
    if not requested then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.studyStartFailed",
            requestError
        )
    end
end)

addEvent(REBUILD_STUDY_REQUEST_EVENT, true)
addEventHandler(REBUILD_STUDY_REQUEST_EVENT, resourceRoot, function(
    allowEarlyReview
)
    if not client or source ~= resourceRoot then
        return
    end
    local requested, requestError = requestStudyStart(
        client,
        true,
        allowEarlyReview
    )
    if not requested then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.studyRebuildFailed",
            requestError
        )
    end
end)

addEvent(PAUSE_STUDY_REQUEST_EVENT, true)
addEventHandler(PAUSE_STUDY_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    local requested, requestError = requestStudyCleanup(client, false)
    if not requested then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.studyPauseFailed",
            requestError
        )
    end
end)

addEvent(STOP_STUDY_REQUEST_EVENT, true)
addEventHandler(STOP_STUDY_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    local requested, requestError = requestStudyCleanup(client, true)
    if not requested then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.studyStopFailed",
            requestError
        )
    end
end)

addEvent(CANCEL_STUDY_REQUEST_EVENT, true)
addEventHandler(CANCEL_STUDY_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    local requested, requestError = requestStudyCancel(client)
    if not requested then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.studyCancelFailed",
            requestError
        )
    end
end)

addEvent(UNLINK_CARD_REQUEST_EVENT, true)
addEventHandler(UNLINK_CARD_REQUEST_EVENT, resourceRoot, function(
    mapId,
    entityId,
    cardIdentity
)
    if not client or source ~= resourceRoot then
        return
    end
    local unlinked, unlinkError = unlinkCardFromEntity(
        client,
        mapId,
        entityId,
        cardIdentity
    )
    if not unlinked then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.unlinkFailed",
            unlinkError
        )
        return
    end
    invalidateStudyDependents(
        client,
        unlinked.oldCardIdentity,
        false,
        "unlink"
    )
    triggerClientEvent(
        client,
        PENDING_NOTICE_EVENT,
        resourceRoot,
        "notice.unlinked",
        "unlink"
    )
    sendF7Snapshot(client)
end)

addEvent(REPLACE_CARD_REQUEST_EVENT, true)
addEventHandler(REPLACE_CARD_REQUEST_EVENT, resourceRoot, function(
    mapId,
    entityId,
    oldCardIdentity,
    newCardIdentity
)
    if not client or source ~= resourceRoot then
        return
    end
    local replaced, replaceError = replaceCardForEntity(
        client,
        mapId,
        entityId,
        oldCardIdentity,
        newCardIdentity
    )
    if not replaced then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.replaceFailed",
            replaceError
        )
        return
    end
    invalidateStudyDependents(
        client,
        replaced.oldCardIdentity,
        replaced.newCardIdentity,
        "replace_card"
    )
    triggerClientEvent(
        client,
        PENDING_NOTICE_EVENT,
        resourceRoot,
        "notice.replaced",
        "replace_card"
    )
    sendF7Snapshot(client)
end)

addEvent(RELINK_ENTITY_REQUEST_EVENT, true)
addEventHandler(RELINK_ENTITY_REQUEST_EVENT, resourceRoot, function(
    sourceMapId,
    sourceEntityId,
    targetMapId,
    targetEntityId
)
    if not client or source ~= resourceRoot then
        return
    end
    local relinked, relinkError = relinkEntity(
        client,
        sourceMapId,
        sourceEntityId,
        targetMapId,
        targetEntityId
    )
    triggerClientEvent(
        client,
        PENDING_NOTICE_EVENT,
        resourceRoot,
        relinked and "notice.relinkApplied" or "notice.relinkFailed",
        relinkError
    )
    if relinked then
        invalidateStudyDependents(
            client,
            relinked.link,
            relinked.link,
            "relink_entity"
        )
        local refresh = sendF7Snapshot
        refresh(client)
    end
end)

addEvent(UNDO_REQUEST_EVENT, true)
addEventHandler(UNDO_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    changeHistory(client, "undo")
end)

addEvent(REDO_REQUEST_EVENT, true)
addEventHandler(REDO_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    changeHistory(client, "redo")
end)

addEvent(PICK_ENTITY_REQUEST_EVENT, true)
addEvent(PICK_ENTITY_RESULT_EVENT, true)
addEventHandler(PICK_ENTITY_REQUEST_EVENT, resourceRoot, function(
    entityElement,
    mode
)
    if not client or source ~= resourceRoot then
        return
    end
    local target, reason = validatePickEntity(client, entityElement, mode)
    if not target then
        triggerClientEvent(
            client,
            PICK_ENTITY_RESULT_EVENT,
            resourceRoot,
            false,
            reason
        )
        return
    end
    triggerClientEvent(
        client,
        PICK_ENTITY_RESULT_EVENT,
        resourceRoot,
        true,
        "selected",
        target.mapId,
        target.entityId,
        target.purpose
    )
end)

addEvent(AUTHORIZATION_REQUEST_EVENT, true)
addEventHandler(AUTHORIZATION_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    sendAuthorization(client)
end)

addEventHandler("onPlayerLogin", root, function()
    sendAuthorization(source)
end)

addEventHandler("onPlayerLogout", root, function()
    sendAuthorization(source)
end)

addEventHandler("onElementDestroy", root, function()
    ANKIGTA.MapIdentity.handleEditorElementDestroyed(source)
    if source == runtimeInstance then
        runtimeInstance = nil
    end
end)

addEventHandler("onResourceStart", resourceRoot, function()
    runtimeInstance = getElementByID(RUNTIME_REFERENCE_ID)
    ANKIGTA.Store.open()
    -- Before anything reads a setting: a restart restores what the user chose,
    -- and falls back to the schema default only where nothing valid is stored.
    ANKIGTA.SettingsStore.load()
    ANKIGTA.MapIdentity.recoverPersistedCollisions()
    ANKIGTA.MapIdentity.refreshEntityPresence()

    for _, player in ipairs(getElementsByType("player")) do
        sendAuthorization(player)
    end
end)

-- Review Mode ---------------------------------------------------------------
--
-- The server owns the whole privileged half: it issues the short-lived content
-- capability, admits the card and carries the rating. The client only ever
-- receives a URL and sends back a rating name.

local openReview = false

local function sameCardIdentity(left, right)
    return type(left) == "table"
        and type(right) == "table"
        and left.collectionUuid == right.collectionUuid
        and tonumber(left.cardId) == tonumber(right.cardId)
end

local function normalizedCardIdentity(value)
    if type(value) ~= "table"
        or type(value.collectionUuid) ~= "string"
        or value.collectionUuid == ""
        or (tonumber(value.cardId) or 0) <= 0
    then
        return false
    end
    return {
        collectionUuid = value.collectionUuid,
        cardId = tonumber(value.cardId),
    }
end

function openReviewModeFor(player, cardIdentity)
    local authorized = playerAuthorization(player)
    if not authorized then
        return false, "forbidden"
    end
    local identity = normalizedCardIdentity(cardIdentity)
    if not identity then
        return false, "invalid_card_identity"
    end
    if openReview then
        return false, "review_open"
    end
    openReview = {
        player = player,
        cardIdentity = identity,
        side = "question",
        opened = false,
    }
    local accepted, reason =
        ANKIGTA.CompanionGateway.requestRender(player, identity, "question")
    if not accepted then
        openReview = false
        return false, reason
    end
    return true
end

addEventHandler(RENDER_ISSUED_EVENT, resourceRoot, function(
    player,
    render,
    category,
    side
)
    if not openReview or openReview.player ~= player then
        return
    end
    if not render then
        triggerClientEvent(
            player,
            REVIEW_RESULT_EVENT,
            resourceRoot,
            {state = "rejected", category = category or "render_failed"}
        )
        return
    end
    openReview.side = side or render.side or "question"
    if not openReview.opened then
        openReview.opened = true
        triggerClientEvent(
            player,
            REVIEW_OPEN_EVENT,
            resourceRoot,
            {
                url = render.url,
                side = openReview.side,
                cardIdentity = openReview.cardIdentity,
                -- No closeAfterRating here: the client owns it (ADR 0014) and
                -- reads it from its own settings store.
            }
        )
        return
    end
    triggerClientEvent(
        player,
        REVIEW_SIDE_EVENT,
        resourceRoot,
        {url = render.url, side = openReview.side}
    )
end)

addEvent(REVIEW_REVEAL_REQUEST_EVENT, true)
addEventHandler(REVIEW_REVEAL_REQUEST_EVENT, resourceRoot, function(
    cardIdentity,
    requestedSide
)
    if not client or source ~= resourceRoot then
        return
    end
    if not openReview or openReview.player ~= client then
        return
    end
    if not sameCardIdentity(openReview.cardIdentity, cardIdentity) then
        return
    end
    ANKIGTA.CompanionGateway.requestRender(
        client,
        openReview.cardIdentity,
        requestedSide == "question" and "question" or "answer"
    )
end)

addEvent(REVIEW_RATE_REQUEST_EVENT, true)
addEventHandler(REVIEW_RATE_REQUEST_EVENT, resourceRoot, function(
    cardIdentity,
    rating
)
    if not client or source ~= resourceRoot then
        return
    end
    if not openReview or openReview.player ~= client then
        return
    end
    -- The client proposes; the server decides which card is being rated.
    if not sameCardIdentity(openReview.cardIdentity, cardIdentity) then
        triggerClientEvent(
            client,
            REVIEW_RESULT_EVENT,
            resourceRoot,
            {state = "rejected", category = "card_not_open"}
        )
        return
    end
    local accepted, reason = ANKIGTA.CompanionGateway.requestRating(
        client,
        openReview.cardIdentity,
        rating
    )
    if not accepted then
        triggerClientEvent(
            client,
            REVIEW_RESULT_EVENT,
            resourceRoot,
            {state = "rejected", category = reason}
        )
    end
end)

addEventHandler(REVIEW_RESULT_EVENT, resourceRoot, function(outcome)
    if not openReview or type(outcome) ~= "table" then
        return
    end
    if not sameCardIdentity(openReview.cardIdentity, outcome.cardIdentity) then
        return
    end
    triggerClientEvent(
        openReview.player,
        REVIEW_RESULT_EVENT,
        resourceRoot,
        outcome
    )
end)

addEvent(REVIEW_RETURN_REQUEST_EVENT, true)
addEventHandler(REVIEW_RETURN_REQUEST_EVENT, resourceRoot, function(
    cardIdentity,
    side
)
    if not client or source ~= resourceRoot then
        return
    end
    if not openReview or openReview.player ~= client then
        return
    end
    if not sameCardIdentity(openReview.cardIdentity, cardIdentity) then
        return
    end
    -- A fresh capability, because the previous one has expired or been spent
    -- by whatever the card navigated to.
    ANKIGTA.CompanionGateway.requestRender(
        client,
        openReview.cardIdentity,
        side == "answer" and "answer" or "question"
    )
end)

addEvent(REVIEW_CLOSED_EVENT, true)
addEventHandler(REVIEW_CLOSED_EVENT, resourceRoot, function(_identity, reason)
    if not client or source ~= resourceRoot then
        return
    end
    if not openReview or openReview.player ~= client then
        return
    end
    openReview = false
    -- Revoke the capability immediately rather than waiting out its lifetime.
    ANKIGTA.CompanionGateway.requestRenderClose(client)
    outputDebugString(
        "[ANKIGTA] review_closed reason=" .. tostring(reason or "closed")
    )
end)

addEventHandler("onPlayerQuit", root, function()
    if openReview and openReview.player == source then
        openReview = false
    end
end)

function reviewModeOpenCard()
    return openReview and openReview.cardIdentity or false
end

-- Teleport -------------------------------------------------------------------

local TELEPORT_REQUEST_EVENT = "ankigta:teleportToEntity"

--- Move the requesting player to one of their Map Entities.
-- The client names a Map Entity; the server resolves which Runtime Instance
-- that is, so a client cannot ask to be moved to arbitrary coordinates.
function teleportPlayerToMapEntity(player, mapId, entityId)
    local authorized = playerAuthorization(player)
    if not authorized then
        return false, "forbidden"
    end
    if type(mapId) ~= "string" or type(entityId) ~= "string" then
        return false, "invalid_map_entity"
    end
    local record, readError = ANKIGTA.Store.getMapEntity(mapId, entityId)
    if not record then
        return false, readError or "entity_missing"
    end
    return ANKIGTA.Teleport.toMapEntity(player, {
        mapId = mapId,
        entityId = entityId,
        authoredX = record.authored_x,
        authoredY = record.authored_y,
        authoredZ = record.authored_z,
        interior = record.interior,
        dimension = record.dimension,
    })
end

addEvent(TELEPORT_REQUEST_EVENT, true)
addEventHandler(TELEPORT_REQUEST_EVENT, resourceRoot, function(mapId, entityId)
    if not client or source ~= resourceRoot then
        return
    end
    teleportPlayerToMapEntity(client, mapId, entityId)
end)

addEventHandler("onResourceStop", resourceRoot, function()
    ANKIGTA.Store.close()
end)

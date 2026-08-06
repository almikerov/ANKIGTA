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
local CLEAR_ENTITY_OVERRIDES_EVENT = "ankigta:clearEntityOverrides"
local ENTITY_OVERRIDE_COUNT_EVENT = "ankigta:entityOverrideCount"
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
local ADOPT_ENTITY_REQUEST_EVENT = "ankigta:adoptEntity"
local FORGET_ENTITY_REQUEST_EVENT = "ankigta:forgetMapEntity"
local NOTE_READ_REQUEST_EVENT = "ankigta:requestNote"
local NOTE_UPDATE_REQUEST_EVENT = "ankigta:updateNote"
local NOTE_SNAPSHOT_EVENT = "ankigta:noteSnapshot"
local ENTITY_METADATA_REQUEST_EVENT = "ankigta:updateEntityMetadata"
local PICK_ENTITY_REQUEST_EVENT = "ankigta:pickEntity"
local PICK_ENTITY_RESULT_EVENT = "ankigta:pickEntityResult"
local RECOVERY_STATE_EVENT = "ankigta:databaseRecovery"
local RECOVERY_REQUEST_EVENT = "ankigta:requestDatabaseRecovery"
local RESTORE_REQUEST_EVENT = "ankigta:restoreDatabaseBackup"
local TEXT_LABELS_EVENT = "ankigta:textLabels"

--- The Review mode in which nothing is presented and nothing is rated.
--
-- Named once, here, because four different questions read it: whether a
-- session may be built, whether Review Mode may open at all, whether the
-- companion is worth asking about card states, and whether the world carries
-- Text Labels (ADR 0029).
local SHOW_TEXT_MODE = "show_text"

-- Forward declarations. Both belong with the rest of the world state at the
-- bottom of this file, beside the spatial candidates they replace in
-- `Show text`; linking a card and saving a note happen well above it, and each
-- of them changes what the world should be showing.
local sendTextLabels
local refreshCardNoteCache

-- Ticket 05 uses this only to observe a disposable map-created element.
-- Persistent Map Entity identity remains the responsibility of ticket 06.
local RUNTIME_REFERENCE_ID = "ankigta-ticket05-runtime"

local runtimeInstance = nil

-- A marker is a thing a map author places on purpose to mean "here", which is
-- exactly what a card wants to hang on. The prior resource allowed pickups and
-- colshapes too; those are a spec question, this one is not.
local SUPPORTED_ENTITY_TYPES = ANKIGTA.EntityTypes.supported
local SUPPORTED_ENTITY_ORDER = ANKIGTA.EntityTypes.order

local function denial(category)
    return {
        category = category,
    }
end

-- What is standing in the world is `server/world.lua`'s to answer, so the
-- panel's scoping, the link path, teleport and the study refresh cannot end up
-- with four answers that disagree.
local owningResource = ANKIGTA.World.owningResource
local currentMapContext = ANKIGTA.World.currentMapContext
local isEditorRepresentation = ANKIGTA.World.isEditorRepresentation

--- A name for an element that has none of its own.
--
-- The prior resource keyed on what an element *is and where it stands* --
-- type, model, position, rotation, interior -- and disambiguated identical
-- twins by their ordinal among themselves. That is why it could take a
-- freeroam vehicle, which no `.map` file ever named, and it is the right
-- answer: an object that has not moved is the same object.
--
-- The trade is honest and worth stating: move the thing and the name changes,
-- so the card is left pointing at where it used to be. A `.map` id, where
-- there is one, does not have that weakness, so it wins.
local function positionalName(element)
    local x, y, z = getElementPosition(element)
    if type(x) ~= "number" then
        return nil
    end
    local rotationX, rotationY, rotationZ = getElementRotation(element)
    local descriptor = table.concat({
        getElementType(element),
        tostring(getElementModel(element) or 0),
        string.format("%.3f", x),
        string.format("%.3f", y),
        string.format("%.3f", z),
        string.format("%.2f", tonumber(rotationX) or 0),
        string.format("%.2f", tonumber(rotationY) or 0),
        string.format("%.2f", tonumber(rotationZ) or 0),
        tostring(getElementInterior(element)),
        -- The prior resource keyed on the dimension as well, and it was right
        -- to: two identical objects in two dimensions are two objects.
        tostring(getElementDimension(element)),
    }, "|")
    -- Twins stand in the same place with the same model, so the descriptor
    -- alone would name them both. The ordinal is which of them this is.
    local ordinal = 0
    for _, candidate in ipairs(getElementsByType(getElementType(element))) do
        local otherX, otherY, otherZ = getElementPosition(candidate)
        if type(otherX) == "number"
            and getElementModel(candidate) == getElementModel(element)
            and string.format("%.3f", otherX) == string.format("%.3f", x)
            and string.format("%.3f", otherY) == string.format("%.3f", y)
            and string.format("%.3f", otherZ) == string.format("%.3f", z)
        then
            ordinal = ordinal + 1
            if candidate == element then
                break
            end
        end
    end
    return "at_" .. md5(descriptor .. "|" .. tostring(math.max(ordinal, 1)))
end

--- Everything the store needs to write an object down, read off the object.
local function adoptionRecord(element, context)
    -- The name in a `.map` file if there is one, because it survives the
    -- object being moved; otherwise where the object stands, which is what
    -- lets a freeroam vehicle be taken at all.
    local entityId = getElementID(element)
    if type(entityId) ~= "string" or entityId == "" then
        entityId = positionalName(element)
    end
    if type(entityId) ~= "string" or entityId == "" then
        return false, "entity_has_no_durable_id"
    end
    local resourceName = context and context.resourceName
        or owningResource(element) or "world"
    -- What the map's document is actually called. `maps.map_name` is read as a
    -- `.map` filename everywhere -- it is what `Store.updateMapLocator` writes
    -- into it -- so filling it with the resource name made every later reader
    -- look for a file that is not there, and made the copy-decision check
    -- announce every adopted row as a copy of itself.
    local locator = ANKIGTA.MapIdentity.currentMapLocator()
    local mapFile = (locator and locator.resourceName == resourceName)
        and locator.mapFile
        or resourceName
    local x, y, z = getElementPosition(element)
    local rotationX, rotationY, rotationZ = getElementRotation(element)
    return {
        -- One map per resource: a `.map` names its elements uniquely, and the
        -- resource is what the ownership walk can check. The map's *identity*
        -- is the resource; the map's *document* is the file it declares, and
        -- the two are different strings.
        mapId = resourceName,
        mapName = mapFile,
        resourceName = resourceName,
        entityId = entityId,
        entityType = getElementType(element),
        model = getElementModel(element),
        x = x, y = y, z = z,
        rotationX = rotationX or 0,
        rotationY = rotationY or 0,
        rotationZ = rotationZ or 0,
        interior = getElementInterior(element) or 0,
        dimension = getElementDimension(element) or 0,
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

local function runtimeSnapshot(element)
    if not isElement(element) then
        return {
            available = false,
            streamed = false,
        }
    end

    return {
        available = true,
        streamed = false,
        referenceId = getElementID(element) or "",
    }
end

--- The row an element's own stamp names, wherever it is standing today.
--
-- ANKIGTA writes `ankigtaEntityId` on an element when it adopts it, so an
-- element carrying one is already a Map Entity and the stamp is its durable
-- half. The map is not: the same object can be saved into another `.map`, or
-- met while a different map resource owns it, and then the identity the panel
-- names -- which is built from the map it is standing in -- misses a row that
-- plainly exists.
--
-- That is what refused `Draw always` on an object stored under `editor_dump`
-- while the world had it under `editor_test`: `findMapEntityByRuntimeElement`
-- checks the owning resource as well as the id, and answered "not loaded"
-- about a thing standing in front of the player.
--
-- One row or none. Two maps holding the same entity id is a question about
-- which entity is meant, and answering it by picking the first would write to
-- whichever the walk happened to reach.
local function rowByOwnStamp(entityElement)
    local stamp = getElementData(entityElement, "ankigtaEntityId")
    if type(stamp) ~= "string" or stamp == "" then
        return nil
    end
    local rows = ANKIGTA.Store.listMapEntities()
    if type(rows) ~= "table" then
        return nil
    end
    local found = nil
    for _, row in ipairs(rows) do
        if row.entity_id == stamp then
            if found then
                return nil
            end
            found = row
        end
    end
    return found
end

--- The Map Entity an element in the world is, by either half of its identity.
--
-- Both, because neither answers on its own. The store's walk checks the owning
-- resource as well as the id, which is right for an element loaded from the
-- map it is recorded against and wrong for the copy in front of the player
-- during a play-test. The stamp answers wherever the element is standing, and
-- is only there once ANKIGTA has taken the element in.
local function rowForRuntimeElement(entityElement)
    local row, readError =
        ANKIGTA.Store.findMapEntityByRuntimeElement(entityElement)
    if row then
        return row
    end
    return rowByOwnStamp(entityElement), readError
end

--- What this row's Text Label would say, for the panel row that sets it.
--
-- Carried on every row rather than only in `Show text`, because the row is
-- where the three overrides are edited and a player setting them has to see
-- what they did without changing mode first. The lines travel with it, so the
-- row shows what the world shows rather than a second rendering of the same
-- note that could disagree with it.
--
-- `false` where the row is not a Spatial Link at all: there is nothing to
-- label, and the pane says so in its own words.
local function textLabelContract(row, notes, globals)
    local label = ANKIGTA.TextLabels.forRow(row, notes, globals, nil)
    if not label then
        return false
    end
    return {
        requestedField = label.requestedField,
        fieldName = label.fieldName,
        fallback = label.fallback,
        reason = label.reason,
        truncated = label.truncated,
        lines = label.lines,
    }
end

local function entityContract(row, notes, globals)
    local link = ANKIGTA.MapIdentity.linkSnapshot(row)
    -- Whether there is a Runtime Instance at all, which is a different
    -- question from which of several copies is in front of the player -- two
    -- copies still means the entity is there. Stopped at the first, because
    -- this runs once per row inside F7's two-second envelope.
    local element =
        ANKIGTA.World.runtimeInstances(row.map_id, row.entity_id, 1)[1]
    -- Every override the schema declares, absent where the entity says nothing
    -- of its own and follows Settings. What "follows Settings" then looks like
    -- is the client's to resolve: the value it falls back to is one the client
    -- already holds, and a copy resolved here would go stale the moment the
    -- setting changed.
    --
    -- One table under both names. `display` and `metadata` have carried the
    -- same answers since ticket 09 named them; building it twice is a second
    -- walk of the schema per row, and this runs ten thousand times inside F7's
    -- two-second envelope. Nothing mutates either of them.
    local metadata = ANKIGTA.Store.metadataOf(row)
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
            display = metadata,
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
        runtimeInstance = runtimeSnapshot(element),
        metadata = metadata,
        textLabel = textLabelContract(row, notes, globals),
        link = link,
        copyCollision = link.copyCollision == true,
    }
end

--- What the F7 snapshot cost to build, measured where it is built.
--
-- The threshold ticket 30 states is about the window being usable, which no
-- automated check can watch. This is the part of it the server owns and can
-- report: how long the read and the contract took, over how much data, and
-- whether that data is still inside the volume the promise covers. It travels
-- with the snapshot so a player's bug report carries it too.
local function snapshotDiagnostics(startedAt, entityCount, linkCount)
    local volume = ANKIGTA.Store.volumeReport()
    return {
        buildMs = getTickCount() - startedAt,
        entityCount = entityCount,
        linkCount = linkCount,
        mapEntities = type(volume) == "table" and volume.mapEntities or false,
        spatialLinks = type(volume) == "table" and volume.spatialLinks or false,
        referenceMapEntities = type(volume) == "table"
            and volume.referenceMapEntities or false,
        referenceSpatialLinks = type(volume) == "table"
            and volume.referenceSpatialLinks or false,
        overReferenceVolume = type(volume) == "table"
            and volume.overReference == true,
    }
end

--- One row for something in the world that ANKIGTA has not taken in yet.
--
-- Shaped like a stored entity so the panel needs no second kind of row, and
-- marked `Not adopted` so it reads as an offer rather than as a link that has
-- gone wrong. Without these the list showed only what was already inside it,
-- which on a fresh install is nothing -- so a player looking at a world full of
-- objects was looking at an empty list and correctly concluded it was broken.
local function candidateContract(element, name, resourceName)
    local x, y, z = getElementPosition(element)
    local rotationX, rotationY, rotationZ = getElementRotation(element)
    return {
        mapEntity = {
            mapId = resourceName,
            entityId = name,
            type = getElementType(element),
            model = getElementModel(element),
            map = {resourceName = resourceName, mapName = resourceName},
            -- Nothing of its own about anything: it is not in the store yet, so
            -- every global reaches it untouched. Said by leaving the overrides
            -- out rather than by naming them, which is also what makes this row
            -- keep its shape as the set of overridable settings grows.
            display = {name = "", entityTag = ""},
            authored = {
                position = {x = x or 0, y = y or 0, z = z or 0},
                rotation = {
                    x = rotationX or 0, y = rotationY or 0, z = rotationZ or 0
                },
                world = {
                    interior = getElementInterior(element) or 0,
                    dimension = getElementDimension(element) or 0,
                },
            },
        },
        runtimeInstance = {
            available = true,
            referenceId = getElementID(element) or "",
        },
        metadata = {name = "", entityTag = ""},
        link = {state = "Not adopted", guidanceKey = "f7.guidance.notAdopted"},
        copyCollision = false,
        adoptable = true,
    }
end

--- What is standing in the world that could be taken in, nearest first.
--
-- Bounded on purpose. A server with thousands of elements would otherwise
-- build a list nobody can read out of a scan nobody asked for, and the cap is
-- reported rather than applied quietly.
local CANDIDATE_LIMIT = 150

local function worldCandidates(player, storedRows, context, notes, globals)
    local taken = {}
    for _, row in ipairs(storedRows) do
        taken[row.entity_id] = true
    end
    local originX, originY, originZ = 0, 0, 0
    if isElement(player) then
        originX, originY, originZ = getElementPosition(player)
    end

    local found, seen = {}, {}
    for _, kind in ipairs(SUPPORTED_ENTITY_ORDER) do
        for _, element in ipairs(getElementsByType(kind)) do
            local owner = owningResource(element)
            local deletedDimension = context.workingDimension
                and context.workingDimension + 1 or false
            local isRepresentation = isEditorRepresentation(element)
            if owner == context.candidateOwner
                and not isRepresentation
                and (not deletedDimension
                    or getElementDimension(element) ~= deletedDimension)
            then
                local name = getElementID(element)
                if type(name) ~= "string" or name == "" then
                    name = positionalName(element)
                end
                local persistentId = getElementData(element, "ankigtaEntityId")
                local editorId = getElementData(element, "me:ID")
                local alreadyTaken = taken[name]
                    or (persistentId and taken[persistentId])
                    or (editorId and taken[editorId])
                if type(name) == "string" and name ~= ""
                    and not alreadyTaken and not seen[name]
                then
                    seen[name] = true
                    local x, y, z = getElementPosition(element)
                    found[#found + 1] = {
                        element = element,
                        name = name,
                        distance = isElement(player)
                            and getDistanceBetweenPoints3D(
                                originX, originY, originZ, x or 0, y or 0, z or 0
                            )
                            or 0,
                    }
                end
            end
        end
    end
    table.sort(found, function(left, right)
        if left.distance ~= right.distance then
            return left.distance < right.distance
        end
        return left.name < right.name
    end)

    local rows, total = {}, #found
    for index = 1, math.min(total, CANDIDATE_LIMIT) do
        local entry = found[index]
        -- An element ANKIGTA has already stamped is a Map Entity, not an
        -- offer to take one in. Its row can be stored under another map --
        -- the same object saved into a second `.map` -- and offering it again
        -- showed empty metadata over a row that had some, so a box ticked
        -- against it sprang back on the next snapshot.
        local adopted = rowByOwnStamp(entry.element)
        if adopted then
            rows[#rows + 1] = entityContract(adopted, notes, globals)
        else
            rows[#rows + 1] = candidateContract(
                entry.element, entry.name, context.resourceName
            )
        end
    end
    return rows, total
end

local function buildF7Snapshot(player)
    local startedAt = getTickCount()
    local refreshed, refreshError = ANKIGTA.MapIdentity.refreshEntityPresence()
    if not refreshed and refreshError ~= "entity_read_failed" then
        return false, denial(refreshError or "entity_presence_refresh_failed")
    end
    local rows, readError = ANKIGTA.Store.listMapEntities()
    if not rows then
        return false, denial(readError or "storage_unavailable")
    end

    local context = currentMapContext(player, rows)
    local currentRows, currentMapIds, seenMapIds = {}, {}, {}
    local scratchRows = {}
    local cardLinks = {}
    for _, row in ipairs(rows) do
        -- Which map a row belongs to is its ANKIGTA identity, not the name of
        -- the resource the map happens to be loaded from. Those differ every
        -- time the editor is involved: the same document is `editor_dump`
        -- while it is unsaved, `editor_test` while it is play-testing, and
        -- whatever the player saves it as afterwards -- and the identity
        -- written into the `.map` survives all three. Comparing resource names
        -- put every row of the open map outside it, which is what listed each
        -- of them twice: once as a stored row nobody claimed, and once as an
        -- offer to adopt the element standing right there.
        local onCurrentMap = false
        if context ~= false then
            if context.mapIds then
                onCurrentMap = context.mapIds[row.map_id] == true
            else
                onCurrentMap = row.resource_name == context.resourceName
            end
        end
        if onCurrentMap then
            currentRows[#currentRows + 1] = row
            if not seenMapIds[row.map_id] then
                seenMapIds[row.map_id] = true
                currentMapIds[#currentMapIds + 1] = row.map_id
            end
        elseif ANKIGTA.World.isPlayTestResource(row.resource_name) then
            -- Stored against the copy the editor play-tests from, which is not
            -- a map the player can walk back into. Shown anyway: the row is how
            -- they are told what happened, and the only place they can relink
            -- or remove the Spatial Link they made.
            scratchRows[#scratchRows + 1] = row
        end
        if row.link_state == "active" or row.link_state == "card_missing" then
            cardLinks[#cardLinks + 1] = {
                mapId = row.map_id,
                entityId = row.entity_id,
                mapName = row.map_name or row.resource_name,
                collectionUuid = row.collection_uuid,
                cardId = tonumber(row.card_id),
            }
        end
    end

    -- An object deleted in the editor is not a Map Entity any more, so it is
    -- not a row. The editor parks a deleted element in `workingDimension + 1`
    -- rather than destroying it, which is exactly what tells "the player
    -- deleted this" apart from "this map is not loaded" -- and without that
    -- test the row stayed in the list, kept its Activation Zone drawn, and
    -- offered a copy decision about an object that was in the bin.
    --
    -- Reported rather than acted on. The link was made deliberately and the
    -- player is the one who says whether it goes.
    local deletedRows = {}
    local kept = {}
    local deletedIdentities = ANKIGTA.World.deletedIdentities()
    for _, row in ipairs(currentRows) do
        if deletedIdentities[row.entity_id] then
            deletedRows[#deletedRows + 1] = {
                mapId = row.map_id,
                entityId = row.entity_id,
                name = row.entity_name ~= "" and row.entity_name
                    or row.entity_id,
                mapName = row.map_name or row.resource_name,
                linked = row.link_state == "active"
                    or row.link_state == "card_missing",
            }
        else
            kept[#kept + 1] = row
        end
    end
    currentRows = kept

    -- Every row the snapshot emits, in the order it emits them. The candidate
    -- walk is fed this rather than the current-map rows alone: an element whose
    -- row was already emitted must not also be offered as something to adopt,
    -- which is the second half of how one object came to have two entries.
    local emittedRows = {}
    for _, row in ipairs(currentRows) do
        emittedRows[#emittedRows + 1] = row
    end
    for _, row in ipairs(scratchRows) do
        emittedRows[#emittedRows + 1] = row
    end

    -- Read once for the whole snapshot rather than per row: one query
    -- against the cache and one read of three settings, not one of each per
    -- Map Entity in the world.
    local cachedNotes = ANKIGTA.Store.cachedCardNotes()
    if type(cachedNotes) ~= "table" then
        cachedNotes = {}
    end
    local labelGlobals = ANKIGTA.TextLabels.globals()

    local entities = {}
    for _, row in ipairs(emittedRows) do
        table.insert(entities, entityContract(row, cachedNotes, labelGlobals))
    end

    -- After the stored rows, so what ANKIGTA already knows about is what the
    -- player sees first and the offers follow.
    local candidates, candidateTotal = {}, 0
    if context then
        candidates, candidateTotal = worldCandidates(
            player, emittedRows, context, cachedNotes, labelGlobals
        )
    end
    for _, candidate in ipairs(candidates) do
        entities[#entities + 1] = candidate
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
        currentMap = context and {
            resourceName = context.resourceName,
            mapIds = currentMapIds,
        } or false,
        cardLinks = cardLinks,
        entities = entities,
        deletedFromMap = deletedRows,
        candidatesShown = #candidates,
        candidatesFound = candidateTotal,
        history = history,
        diagnostics = snapshotDiagnostics(startedAt, #entities, #cardLinks),
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
    if isEditorRepresentation(entityElement) then
        return false, "entity_not_managed"
    end
    local persistentId = getElementData(entityElement, "ankigtaEntityId")
    -- No name is demanded of the element. One can always be made: the `id` its
    -- `.map` file gave it where there is one, and otherwise where it stands.
    -- Demanding `me:ID`, which the stock editor writes only while it has the
    -- map open, is what made a whole world offer nothing.
    if isElementStreamedIn and not isElementStreamedIn(entityElement) then
        return false, "entity_not_streamed"
    end
    -- Placed by the editor but never adopted: offered as itself rather than
    -- refused. Adoption is what linking a card does next, and refusing here is
    -- what made a map full of editor objects show a single row.
    if type(persistentId) ~= "string" or persistentId == "" then
        if mode == "relink" then
            return false, "relink_target_not_adopted"
        end
        return {
            adoptable = true,
            element = entityElement,
            entityType = entityType,
            purpose = "pick",
        }
    end

    -- Both halves of the identity: without the stamp, pointing at an object
    -- ANKIGTA had already taken in reported it as not loaded, because the copy
    -- in front of the player during a play-test belongs to `editor_test` while
    -- its row is stored against the map being edited.
    local row, readError = rowForRuntimeElement(entityElement)
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

--- Tell one player what there is to recover from, or that there is nothing.
--
-- Sent as state rather than as an error, and re-read on every send: a copy can
-- be deleted or go bad between two glances at the screen, and a copy that is
-- offered has to be one that verified just now.
local function sendRecoveryState(player)
    if not playerAuthorization(player) then
        -- The state names files on the server's disk. It is the Study Player's
        -- to act on and nobody else's to see.
        return false
    end
    triggerClientEvent(
        player,
        RECOVERY_STATE_EVENT,
        resourceRoot,
        ANKIGTA.Store.recovery() or false
    )
    return true
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
        sendRecoveryState(player)
    end
end

--- Restore the copy the player chose on the recovery screen.
--
-- Guarded on the recovery state, not merely on the request being well formed. A
-- database that opened cleanly is never replaced from here: doing it on request
-- would be the silent replacement ADR 0016 forbids, with one extra click in
-- front of it.
local function restoreDatabaseBackup(player, backupId)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    if not ANKIGTA.Store.recovery() then
        return false, "not_in_recovery"
    end
    return ANKIGTA.Store.restoreFromBackup(backupId)
end

--- Every card the session should take, from the maps that are in play.
--
-- The Active Map Set is the only thing that narrows study, and it is asked for
-- here rather than assembled: the counters, the spatial candidates and this
-- set have to be statements about the same world.
local function activeCardIdentities()
    local rows = ANKIGTA.Store.listMapEntities()
    if type(rows) ~= "table" then
        return false, "storage_unavailable"
    end
    local loadedMaps = ANKIGTA.World.loadedMapIds(rows)
    local identities = {}
    local seen = {}
    for _, row in ipairs(rows) do
        if row.link_state == "active"
            and loadedMaps[row.map_id] == true
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

--- Does the Review mode now in force take cards the scheduler does not call
--- due?
--
-- The setting names the mode; the companion is asked a narrower question --
-- whether this session admits not-due cards -- and that stays true of a mode
-- which builds no session at all. Translating here, once, is what keeps the
-- two vocabularies from leaking into each other.
local function studyTakesNotDueCards()
    return ANKIGTA.SettingsStore.get("reviewMode") == "allow_all"
end

--- Which of the three things walking up to a linked Map Entity does.
--
-- Through the schema's default where the store holds nothing the schema
-- accepts, so an unreadable stored mode is the shipped one rather than `nil`
-- compared against three strings.
local function reviewModeInForce()
    local mode = ANKIGTA.SettingsStore.get("reviewMode")
    if type(mode) ~= "string" then
        return ANKIGTA.Settings.default("reviewMode")
    end
    return mode
end

local function requestStudyStart(player, rebuild, reviewMode)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    -- The Review mode is the server's (ADR 0014). The request carries what the
    -- player asked for; the setting is what actually governs, so the request
    -- changes the setting and then the setting is read back. A study session
    -- started after a restart uses the same mode as the one before.
    if type(reviewMode) == "string" then
        ANKIGTA.SettingsStore.set("reviewMode", reviewMode)
    end
    if reviewModeInForce() == SHOW_TEXT_MODE then
        -- `Show text` presents nothing and rates nothing, so there is no
        -- session to build: no filtered deck, no Exact Card Admission, no
        -- Review Transaction and no counters (ADR 0029). Building one anyway
        -- would leave a filtered deck in somebody's collection for a mode that
        -- never rates a card in it.
        return false, "show_text_mode"
    end
    local allowNotDue = studyTakesNotDueCards()
    local identities, identityError = activeCardIdentities()
    if not identities then
        return false, identityError
    end
    if rebuild then
        return ANKIGTA.CompanionGateway.requestSessionRebuild(
            player,
            identities,
            allowNotDue
        )
    end
    return ANKIGTA.CompanionGateway.requestSessionStart(
        player,
        identities,
        allowNotDue
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

    -- The player is passed so candidates can be ordered by how far away
    -- they are: the thing being looked at is nearly always the thing meant.
    local snapshot, snapshotError = buildF7Snapshot(player)
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
    sendF7Snapshot(player)
    -- Undo moves whatever the entry moved, and any of it can change what may
    -- activate: a link, an entity's own Activation type, a radius. The watched
    -- set is rebuilt rather than reasoned about -- one round trip beats a list
    -- of which operations matter, which is a list that goes stale.
    invalidateStudyDependents(player, false, false, direction)
    return true, outcome
end

function undoChange(player)
    return changeHistory(player, "undo")
end

function redoChange(player)
    return changeHistory(player, "redo")
end

local function recheckPendingMapSave(player, mapId, entityId)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    local verified, outcome =
        ANKIGTA.MapIdentity.recheckPendingMapSave(mapId, entityId)
    -- The notice travels as a key: the string table is the client's, so the
    -- side that shows the notice is the side that words it.
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
addEventHandler(SETTINGS_UPDATE_EVENT, resourceRoot, function(key, value)
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
    local stored, reason = ANKIGTA.SettingsStore.set(key, value)
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
    if key == "reviewMode" and value == SHOW_TEXT_MODE then
        -- Arriving in the mode is the other moment the cache has to be
        -- current: a note edited in Anki itself while the player was in
        -- another mode was never seen here, and the labels would open saying
        -- what the card stopped saying.
        refreshCardNoteCache(client)
    end
    -- Sent for every setting rather than for the five that matter. The mode
    -- decides whether there are labels at all and the other four decide what
    -- each says and how far it carries -- and it is the *empty* set that takes
    -- the labels away on the way out of the mode, which a list of five keys
    -- would have to remember to include.
    sendTextLabels(client)
end)

--- Put every link back on the global for one setting.
--
-- Two messages rather than one, because clearing overrides across a world is
-- not undone by pressing the control again: unconfirmed, this answers with how
-- many links it would change and nothing happens; confirmed, it does it. The
-- count comes from the side that is about to act, so it is the number of links
-- the sweep will really touch rather than one the panel worked out earlier.
addEvent(CLEAR_ENTITY_OVERRIDES_EVENT, true)
addEventHandler(CLEAR_ENTITY_OVERRIDES_EVENT, resourceRoot, function(
    settingKey, confirmed
)
    if not client or source ~= resourceRoot then
        return
    end
    local authorized, authorizationError = playerAuthorization(client)
    if not authorized then
        triggerClientEvent(
            client, F7_DENIED_EVENT, resourceRoot, authorizationError
        )
        return
    end
    if confirmed ~= true then
        local count, countError = ANKIGTA.Store.countEntityOverrides(settingKey)
        if not count then
            triggerClientEvent(
                client, SETTINGS_REJECTED_EVENT, resourceRoot,
                settingKey, countError
            )
            return
        end
        triggerClientEvent(
            client, ENTITY_OVERRIDE_COUNT_EVENT, resourceRoot,
            settingKey, count
        )
        return
    end
    local cleared, clearError = ANKIGTA.Store.clearEntityOverrides(settingKey)
    if not cleared then
        triggerClientEvent(
            client, SETTINGS_REJECTED_EVENT, resourceRoot,
            settingKey, clearError
        )
        return
    end
    -- The globals are untouched -- clearing an override is not a change to the
    -- value it was overriding -- so only the entity snapshot moved, and with it
    -- the history the panel offers Undo from.
    --
    -- And the watched set, for the same reason one entity's edit moves it: a
    -- sweep that put every entity back on `Automatic` would leave every client
    -- still waiting for a press.
    if cleared.cleared > 0 then
        invalidateStudyDependents(client, false, false, "clear_entity_overrides")
    end
    sendF7Snapshot(client)
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
    pageSize,
    scope
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
        pageSize,
        scope
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
        local linkedIdentity = linkedRow and cardIdentityFromRow(linkedRow)
            or cardIdentity
        invalidateStudyDependents(client, false, linkedIdentity, "link")
        -- The words behind the card are written down as the Spatial Link is
        -- made, so a Text Label is there from the moment the link is -- and
        -- stays there once Anki is shut.
        refreshCardNoteCache(client, {linkedIdentity})
        local refresh = sendF7Snapshot
        refresh(client)
    end
end)

addEvent(START_STUDY_REQUEST_EVENT, true)
addEventHandler(START_STUDY_REQUEST_EVENT, resourceRoot, function(
    reviewMode
)
    if not client or source ~= resourceRoot then
        return
    end
    local requested, requestError = requestStudyStart(
        client,
        false,
        reviewMode
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
    reviewMode
)
    if not client or source ~= resourceRoot then
        return
    end
    local requested, requestError = requestStudyStart(
        client,
        true,
        reviewMode
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
    -- Unlinking is what makes a cached note pointless, and keeping it would be
    -- a copy of somebody's card held after they said to forget it (ADR 0017).
    -- Before the invalidation, so the labels rebuilt by it are rebuilt from a
    -- cache that no longer holds the card nothing points at.
    ANKIGTA.Store.pruneCardNoteCache()
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
        target.adoptable and "adoptable" or "selected",
        target.mapId or false,
        target.entityId or false,
        target.purpose,
        -- The element itself, for the one case where there is no identity yet
        -- to name it by. The panel holds it until a card says what it is for.
        target.element or false
    )
end)

--- Adopt an object the stock Map Editor placed, by linking a card to it.
--
-- The card is the reason the object becomes a Map Entity, so the two arrive
-- together rather than as an empty adoption followed by a link that may never
-- come.
--
-- Nothing is written into anybody's `.map`. The object already has a durable
-- name there -- the `id` attribute MTA hands back as `getElementID` -- so the
-- store only has to write down what the object already is.
local function failAdoption(player, reason)
    triggerClientEvent(
        player,
        PENDING_NOTICE_EVENT,
        resourceRoot,
        "notice.adoptFailed",
        reason
    )
end

--- The element a name refers to, for a row the list offered rather than one
--- the player pointed at. The name is derived from the element, so deriving it
--- again over the world finds the same one -- or nothing, if it has gone.
local function elementByAdoptionName(name, player)
    local context = currentMapContext(player)
    if not context then
        return nil
    end
    local deletedDimension = context.workingDimension
        and context.workingDimension + 1 or false
    for _, kind in ipairs(SUPPORTED_ENTITY_ORDER) do
        for _, element in ipairs(getElementsByType(kind)) do
            local candidate = getElementID(element)
            if type(candidate) ~= "string" or candidate == "" then
                candidate = positionalName(element)
            end
            if candidate == name
                and owningResource(element) == context.candidateOwner
                and not isEditorRepresentation(element)
                and (not deletedDimension
                    or getElementDimension(element) ~= deletedDimension)
            then
                return element
            end
        end
    end
    return nil
end

--- Take something standing in the world into the store, with no card involved.
--
-- Adoption used to happen only on the way to a link, which made a Map Entity a
-- thing that could not exist without an Anki Card. The glossary has always said
-- the opposite: a Spatial Link is a link *between* a Map Entity and one card,
-- so the entity is what the link is made of rather than something the link
-- brings into being. Naming an object, or saying how close you have to stand
-- to it, is not a statement about any card -- and until now neither could be
-- made until a card had been chosen.
local function adoptOffer(player, entityElement)
    local target, reason = validatePickEntity(player, entityElement, "pick")
    if not target then
        return false, reason
    end
    if not target.adoptable then
        return false, "entity_already_adopted"
    end
    -- A play-test copy is the same entity seen from inside the test: the
    -- editor wrote the map it has open out to `editor_test` on the Test press,
    -- and both copies carry the id that one document gave them. Recording the
    -- copy would write a Spatial Link against a resource the next Test press
    -- rewrites -- so what is recorded is the entity as the editor holds it,
    -- which is also what makes the same object linked inside a test and
    -- outside one one Map Entity rather than two. Outside a test this answers
    -- with what it was given, and the map is the one the player is standing in.
    local enduring, enduringError = ANKIGTA.World.enduring(entityElement)
    if not enduring then
        return false, enduringError
    end
    local record, recordError = adoptionRecord(
        enduring.element,
        enduring.context or currentMapContext(player)
    )
    if not record then
        return false, recordError
    end
    local row, adoptError = ANKIGTA.Store.adoptMapEntity(record)
    if not row then
        return false, adoptError
    end
    -- Remembered on the element so the next pick resolves without the walk,
    -- and so a second Link on the same object is recognised as a replacement
    -- rather than adopting it twice. On both copies where there are two: the
    -- one the player pointed at is the one they will point at again while the
    -- test is running.
    setElementData(enduring.element, "ankigtaEntityId", record.entityId)
    if enduring.element ~= entityElement then
        setElementData(entityElement, "ankigtaEntityId", record.entityId)
    end
    return record
end

addEvent(ADOPT_ENTITY_REQUEST_EVENT, true)
addEventHandler(ADOPT_ENTITY_REQUEST_EVENT, resourceRoot, function(
    entityElement,
    cardIdentity
)
    if not client or source ~= resourceRoot then
        return
    end
    -- Pick Entity sends the element it was aimed at; the list sends the name
    -- it displayed. Both end up here as the same thing.
    if type(entityElement) == "string" then
        entityElement = elementByAdoptionName(entityElement, client)
        if not entityElement then
            return failAdoption(client, "entity_no_longer_in_the_world")
        end
    end
    local record, adoptError = adoptOffer(client, entityElement)
    if not record then
        return failAdoption(client, adoptError)
    end

    local linked, linkError = linkCardToEntity(
        client,
        record.mapId,
        record.entityId,
        cardIdentity
    )
    if not linked then
        return failAdoption(client, linkError)
    end
    invalidateStudyDependents(client, false, cardIdentity, "link")
    sendF7Snapshot(client)
end)

--- What one Map Entity says of its own, set on the entity itself.
--
-- The prior resource put the radius next to the object rather than in a global
-- setting, and it was right: how close you must stand is a property of the
-- thing, not of the player. It is not the only one -- how the card opens, on
-- which key, and what mark the thing wears are all properties of the thing --
-- so this takes whichever of them the message mentions and leaves the rest.
--
-- Which fields those are comes from the schema rather than from a list here.
-- Six writers used to spell out their own, and the one that was missed wrote a
-- default over whatever the entity said.
--
-- Validated against the same rule the global setting uses, so one value cannot
-- be legal in Settings and illegal here.
addEvent(ENTITY_METADATA_REQUEST_EVENT, true)
addEventHandler(ENTITY_METADATA_REQUEST_EVENT, resourceRoot, function(
    mapId, entityId, metadata
)
    if not client or source ~= resourceRoot then
        return
    end
    local authorized, authorizationError = playerAuthorization(client)
    if not authorized then
        return
    end
    if type(metadata) ~= "table" then
        return
    end
    if metadata.name ~= nil and type(metadata.name) ~= "string" then
        return
    end
    local row, readError = ANKIGTA.Store.getMapEntity(mapId, entityId)
    if not row then
        -- Nothing stored under that identity. The panel is either naming an
        -- offer -- and editing one is exactly what takes it in -- or naming an
        -- entity by the identity it had *before* it was adopted, because
        -- adoption renames it and the row on screen is one snapshot behind.
        -- Both are answered by asking the store about the element itself.
        local element = elementByAdoptionName(entityId, client)
        if not element then
            outputDebugString(
                "[ANKIGTA] entity_element_not_found map=" .. tostring(mapId)
                    .. " entity=" .. tostring(entityId),
                2
            )
        end
        if element then
            local adopted = rowForRuntimeElement(element)
            if adopted then
                mapId, entityId = adopted.map_id, adopted.entity_id
            else
                local record, adoptError = adoptOffer(client, element)
                if not record then
                    -- Everything the refusal turned on, because "not loaded"
                    -- about a thing standing in front of the player is a claim
                    -- only this side can check. The stamp and the owning
                    -- resource are what `findMapEntityByRuntimeElement` reads.
                    outputDebugString(
                        "[ANKIGTA] entity_adopt_refused"
                            .. " map=" .. tostring(mapId)
                            .. " entity=" .. tostring(entityId)
                            .. " reason=" .. tostring(adoptError)
                            .. " stamp=" .. tostring(
                                getElementData(element, "ankigtaEntityId")
                            )
                            .. " stampedMap=" .. tostring(
                                getElementData(element, "ankigtaMapId")
                            )
                            .. " type=" .. tostring(getElementType(element)),
                        2
                    )
                    triggerClientEvent(
                        client, PENDING_NOTICE_EVENT, resourceRoot,
                        "notice.entityUpdateFailed", adoptError
                    )
                    return
                end
                mapId, entityId = record.mapId, record.entityId
            end
            row = ANKIGTA.Store.getMapEntity(mapId, entityId)
        end
    end
    if not row then
        -- Named, because "not loaded" about an entity plainly standing in the
        -- world is a claim the player cannot check and this side can. The
        -- identity the panel asked by is the whole of what is in doubt.
        outputDebugString(
            "[ANKIGTA] entity_metadata_unresolved map=" .. tostring(mapId)
                .. " entity=" .. tostring(entityId)
                .. " reason=" .. tostring(readError or "entity_missing"),
            2
        )
        triggerClientEvent(
            client, PENDING_NOTICE_EVENT, resourceRoot,
            "notice.entityUpdateFailed", readError or "entity_missing"
        )
        return
    end
    --- One overridable field as it will be stored, or the reason it will not be.
    --
    -- Three answers, not two, and one rule for all of them. A value is an
    -- override; `"inherit"` is the field emptied, which means "follow the
    -- global again" and stores nothing; and absent means this message is not
    -- about that field at all, so whatever the row already said stands.
    --
    -- `"inherit"` rather than `false`, which is what it used to be: `false` is
    -- a value `Show corona` can hold -- "not on this one, whatever the global
    -- says" -- so it cannot also be how a field says it holds nothing. One word
    -- for one meaning, and it collides with no colour, key name or mode.
    --
    -- Checked against the schema's own rule for the setting it overrides,
    -- because a value cannot be legal in Settings and illegal here, and the
    -- schema is the side both can reach. Validated before it is normalized,
    -- which is the order every other caller uses: normalizing first hands
    -- whatever arrived over the wire straight to the rule's own conversion,
    -- and `coronaColor` lowercases -- so a client sending `true` would take
    -- the handler down instead of being told no.
    local INHERIT = "inherit"
    local function proposed(sent, stored, key)
        if sent == nil then
            return stored
        end
        if sent == INHERIT then
            return nil
        end
        local valid, reason = ANKIGTA.Settings.validate(key, sent)
        if not valid then
            return nil, reason
        end
        return ANKIGTA.Settings.normalize(key, sent)
    end

    -- Everything the row already says, so setting one field does not quietly
    -- erase the others -- and every override the schema declares, so one added
    -- later is carried here by being declared rather than by this being edited.
    local stored = ANKIGTA.Store.metadataOf(row)
    local wanted = {
        name = metadata.name ~= nil and metadata.name or (row.entity_name or ""),
        entityTag = row.entity_tag or "",
    }
    for _, key in ipairs(ANKIGTA.Settings.entityOverridableKeys()) do
        local field = ANKIGTA.Settings.entityOverrideField(key)
        local value, refused = proposed(metadata[field], stored[field], key)
        if refused then
            triggerClientEvent(
                client, PENDING_NOTICE_EVENT, resourceRoot,
                "notice.entityUpdateFailed", refused
            )
            return
        end
        wanted[field] = value
    end

    local updated, updateError = ANKIGTA.Store.updateEntityMetadata(
        mapId,
        entityId,
        wanted
    )
    if not updated then
        triggerClientEvent(
            client, PENDING_NOTICE_EVENT, resourceRoot,
            "notice.entityUpdateFailed", updateError
        )
        return
    end
    -- An override is part of what the watched set says, and the watched set is
    -- what the client acts on: an entity told to open by a key would go on
    -- opening by itself until the next time Anki happened to be asked.
    --
    -- Over the schema's fields rather than over what arrived, so a *cleared*
    -- override counts too -- it is absent from `wanted` and present in
    -- `stored`, which is the direction a loop over the message would miss. Only
    -- when one really changed, so naming a thing does not cost a round trip to
    -- the companion.
    for _, key in ipairs(ANKIGTA.Settings.entityOverridableKeys()) do
        local field = ANKIGTA.Settings.entityOverrideField(key)
        if stored[field] ~= wanted[field] then
            invalidateStudyDependents(client, false, false, "entity_metadata")
            break
        end
    end
    sendF7Snapshot(client)
end)

--- The note behind a card, for the inspector.
--
-- Asked for when a card is selected rather than carried on every search: a
-- page of fifty cards would pay fifty note reads for the one that gets looked
-- at.
local function sendNote(player, ok, payload)
    triggerClientEvent(
        player,
        NOTE_SNAPSHOT_EVENT,
        resourceRoot,
        ok == true,
        ok == true and payload or false,
        ok ~= true and tostring(payload) or false
    )
end

addEvent(NOTE_READ_REQUEST_EVENT, true)
addEventHandler(NOTE_READ_REQUEST_EVENT, resourceRoot, function(cardIdentity)
    if not client or source ~= resourceRoot then
        return
    end
    local player = client
    ANKIGTA.CompanionGateway.requestNoteRead(
        player,
        cardIdentity,
        function(ok, value)
            sendNote(player, ok, value)
        end
    )
end)

addEvent(NOTE_UPDATE_REQUEST_EVENT, true)
addEventHandler(NOTE_UPDATE_REQUEST_EVENT, resourceRoot, function(
    cardIdentity, fields, tags
)
    if not client or source ~= resourceRoot then
        return
    end
    local player = client
    ANKIGTA.CompanionGateway.requestNoteUpdate(
        player,
        cardIdentity,
        type(fields) == "table" and fields or {},
        type(tags) == "table" and tags or {},
        function(ok, value)
            sendNote(player, ok, value)
            if not ok then
                triggerClientEvent(
                    player, PENDING_NOTICE_EVENT, resourceRoot,
                    "notice.noteUpdateFailed", tostring(value)
                )
                return
            end
            -- What the note says now, read back after the write, is what its
            -- Text Label should say now. Taken from the answer rather than
            -- from the request: Anki may rewrite a field on save, and a label
            -- showing what was typed rather than what was stored would
            -- disagree with the card it came from.
            local note = type(value) == "table" and value.note or nil
            if type(note) == "table" then
                ANKIGTA.Store.cacheCardNote(cardIdentity, note.fields)
                sendTextLabels(player)
                sendF7Snapshot(player)
            end
        end
    )
end)

addEvent(RECOVERY_REQUEST_EVENT, true)
addEventHandler(RECOVERY_REQUEST_EVENT, resourceRoot, function()
    if not client or source ~= resourceRoot then
        return
    end
    sendRecoveryState(client)
end)

addEvent(RESTORE_REQUEST_EVENT, true)
addEventHandler(RESTORE_REQUEST_EVENT, resourceRoot, function(backupId)
    if not client or source ~= resourceRoot then
        return
    end
    if not playerAuthorization(client) then
        return
    end
    local restored, restoreError = restoreDatabaseBackup(client, backupId)
    triggerClientEvent(
        client,
        PENDING_NOTICE_EVENT,
        resourceRoot,
        restored and "notice.restored" or "notice.restoreFailed",
        restored and restored.restored or restoreError
    )
    -- Either way the screen is told what is on disk now, so a failed restore
    -- leaves the choice open rather than an empty window.
    sendRecoveryState(client)
    if restored then
        sendF7Snapshot(client)
    end
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

    -- Deliberately nothing is pushed to players here. On a restart this side
    -- comes up first, and a client that has not started its own scripts yet
    -- has registered no events, so every push lands as "event is not added
    -- clientside" and is simply lost. Each client asks for what it needs from
    -- its own `onClientResourceStart` -- authorization, settings and the
    -- recovery state all have a request -- and asking is the half that can
    -- know it is ready.
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
    if reviewModeInForce() == SHOW_TEXT_MODE then
        -- The one door into Review Mode, so this is the one place that has to
        -- refuse. `Show text` presents no card, and a card that was never
        -- presented must not be rateable: ADR 0027 lets a *badly* presented
        -- card be rated because the player saw it, and here there is nothing
        -- to have seen. Rating it would write a repetition that did not
        -- happen (ADR 0029).
        return false, "show_text_mode"
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

-- Study state: counters, candidates and the next target ----------------------
--
-- One refresh answers three questions that have to agree with each other: how
-- much work there is, which Spatial Link may open by itself, and which Map
-- Entity carries the marker. They are all statements about the same moment, so
-- they come from one read of the world and one answer from Anki.
--
-- Nothing here decides a card's state or which card is next. Both come from
-- Anki through the companion (ADR 0017); a card Anki did not report on is
-- simply not counted and not activated.

local SPATIAL_CANDIDATES_EVENT = "ankigta:spatialCandidates"
local NEXT_CARD_EVENT = "ankigta:nextCard"
local STATISTICS_EVENT = "ankigta:statistics"
local SPATIAL_OPEN_REQUEST_EVENT = "ankigta:requestSpatialOpen"
local CARD_STATES_REFRESHED_EVENT = "ankigta:cardStatesRefreshed"
local STUDY_STATE_EVENT = "ankigta:studyStateChanged"

local EMPTY_COUNTS = {new = 0, learning = 0, due = 0, early = 0, total = 0}

--- Which observed card states a Spatial Link may activate on.
--
-- The same table `Statistics` counts by, for the same reason: a card that is
-- not part of the work to be done is not a card to walk into. `not_due` is
-- conditional on the early-review setting and is handled where it is read.
local ACTIVATABLE_STATES = {
    new = true,
    learning = true,
    review = true,
    not_due = "early",
}

local function cardStateKey(collectionUuid, cardId)
    return tostring(collectionUuid) .. "/" .. tostring(cardId)
end

--- Tell the client there is nothing to watch.
--
-- Sent rather than left implicit: this is how `Pause studying` turns the
-- Activation Zone and the marker off, and a client that simply stopped hearing
-- from the server would keep the last set forever.
local function sendPausedStudyState(player)
    triggerClientEvent(player, STATISTICS_EVENT, resourceRoot, EMPTY_COUNTS)
    triggerClientEvent(player, SPATIAL_CANDIDATES_EVENT, resourceRoot, {})
    triggerClientEvent(player, NEXT_CARD_EVENT, resourceRoot, false, {})
end

--- Every Text Label the world should be showing, sent to one player.
--
-- Sent whether or not `Show text` is the current mode: outside it the set is
-- empty, and that empty set is how the labels go away when the player changes
-- mode. A client that simply stopped hearing about them would go on drawing
-- the last set it was given.
--
-- Independent of the companion, of any session and of every card's state. The
-- words come out of ANKIGTA's own cache, so the labels are there with Anki
-- shut, and they are there whether or not a card is due (ADR 0029).
sendTextLabels = function(player)
    if not playerAuthorization(player) then
        return false, "forbidden"
    end
    local reach = tonumber(ANKIGTA.SettingsStore.get("textLabelDistance"))
        or ANKIGTA.Settings.default("textLabelDistance")
    if reviewModeInForce() ~= SHOW_TEXT_MODE then
        triggerClientEvent(player, TEXT_LABELS_EVENT, resourceRoot, {}, reach)
        return true
    end
    local rows = ANKIGTA.Store.listMapEntities()
    if type(rows) ~= "table" then
        return false, "storage_unavailable"
    end
    local notes = ANKIGTA.Store.cachedCardNotes()
    local labels = ANKIGTA.TextLabels.build(
        rows,
        type(notes) == "table" and notes or {},
        ANKIGTA.TextLabels.globals(),
        -- The same set of maps the session takes cards from. A link on a map
        -- nobody has loaded has no object standing anywhere to label.
        ANKIGTA.World.loadedMapIds(rows)
    )
    triggerClientEvent(player, TEXT_LABELS_EVENT, resourceRoot, labels, reach)
    return true
end

--- Read the words behind these cards out of Anki and write them down.
--
-- The cache is what a Text Label is drawn from, so this is the only thing in
-- `Show text` that needs the companion at all -- and it is needed once per
-- change, not per frame and not per label. Anki stays the owner of what it
-- returns (ADR 0017); what is stored is a copy for display.
--
-- `identities` names the cards to refresh, or nothing for all of them. One
-- card is what a new Spatial Link asks for; all of them is what connecting
-- asks for, because anything may have changed while ANKIGTA was not looking.
refreshCardNoteCache = function(player, identities)
    if not playerAuthorization(player) then
        return false, "forbidden"
    end
    local wanted = identities or activeCardIdentities()
    if type(wanted) ~= "table" or #wanted == 0 then
        return false, "no_links"
    end
    return ANKIGTA.CompanionGateway.requestNotes(
        player,
        wanted,
        function(ok, payload)
            if ok ~= true or type(payload) ~= "table" then
                -- The labels already on screen stay as they were. A stale line
                -- is a line the note really said once; an empty one would say
                -- the note is blank, which is a different and false claim.
                return
            end
            for _, note in ipairs(payload.notes or {}) do
                ANKIGTA.Store.cacheCardNote(note.identity, note.fields)
            end
            if identities == nil then
                -- A full refresh is also when a card nothing links to any more
                -- stops being worth keeping a copy of.
                ANKIGTA.Store.pruneCardNoteCache()
            end
            sendTextLabels(player)
        end
    )
end

--- Ask Anki for the state of every linked card, and for the next one.
local function refreshStudyState(player)
    if not playerAuthorization(player) then
        return false, "forbidden"
    end
    -- Here, and first, because this is what `invalidateStudyDependents` runs:
    -- every link, unlink, relink, metadata edit, override sweep and undo comes
    -- through it. An override that only reached the client the next time Anki
    -- happened to be asked is the defect ticket 05 found, and a mode that
    -- never asks Anki at all would never have been told.
    sendTextLabels(player)
    if reviewModeInForce() == SHOW_TEXT_MODE then
        -- No session, so no counters and nothing to walk into. The labels sent
        -- just above are the whole of what this mode puts in the world, and
        -- asking the companion for card states would be asking a question this
        -- mode has no use for -- with Anki shut, one that cannot be answered.
        sendPausedStudyState(player)
        return true
    end
    local identities, identityError = activeCardIdentities()
    if not identities then
        return false, identityError
    end
    if #identities == 0 then
        sendPausedStudyState(player)
        return true
    end
    return ANKIGTA.CompanionGateway.requestCardStates(player, identities)
end

addEvent(CARD_STATES_REFRESHED_EVENT, false)
addEventHandler(CARD_STATES_REFRESHED_EVENT, resourceRoot, function(
    player,
    cardStates,
    nextCard
)
    if source ~= resourceRoot or not playerAuthorization(player) then
        return
    end
    local rows = ANKIGTA.Store.listMapEntities()
    if type(rows) ~= "table" then
        return
    end
    local loadedMaps = ANKIGTA.World.loadedMapIds(rows)
    local allowNotDue = studyTakesNotDueCards()

    triggerClientEvent(
        player,
        STATISTICS_EVENT,
        resourceRoot,
        ANKIGTA.Statistics.summarize(
            rows,
            cardStates,
            loadedMaps,
            allowNotDue
        )
    )

    -- Identities and metadata only. Where the Runtime Instance is now is the
    -- client's to read off the live element (Implementation Decision 14), and
    -- a coordinate sent from here would be the authored one wearing the
    -- current one's name.
    local candidates, bearers = {}, {}
    for _, row in ipairs(rows) do
        if row.link_state == "active"
            and loadedMaps[row.map_id] == true
            and type(row.collection_uuid) == "string"
            and tonumber(row.card_id) ~= nil
        then
            local state = cardStates[
                cardStateKey(row.collection_uuid, tonumber(row.card_id))
            ]
            local activatable = state and ACTIVATABLE_STATES[state] or false
            if activatable == "early" and not allowNotDue then
                -- Preview only, so not something to walk into (story 35).
                activatable = false
            end
            if activatable then
                local cardIdentity = {
                    collectionUuid = row.collection_uuid,
                    cardId = tonumber(row.card_id),
                }
                -- No corona flag on a candidate. Whether something already
                -- marks this spot is a question about what is being drawn
                -- right now, which is the client's own answer -- a corona
                -- appears when its Runtime Instance is here and goes when it
                -- is not, and neither is something the server watches.
                --
                -- What the entity says of its own about how it opens travels
                -- with it, absent where it says nothing: the client resolves
                -- "follows the global" against the settings it already holds,
                -- so changing a global moves every candidate without the
                -- server sending the set again.
                local overrides = ANKIGTA.Store.overridesOf(row)
                local candidate = {
                    mapId = row.map_id,
                    entityId = row.entity_id,
                    cardIdentity = cardIdentity,
                    radius = overrides.radius,
                    activationType = overrides.activationType,
                    activationKey = overrides.activationKey,
                    eligible = true,
                }
                table.insert(candidates, candidate)
                if sameCardIdentity(cardIdentity, nextCard) then
                    table.insert(bearers, {
                        mapId = row.map_id,
                        entityId = row.entity_id,
                    })
                end
            end
        end
    end

    triggerClientEvent(
        player,
        SPATIAL_CANDIDATES_EVENT,
        resourceRoot,
        candidates
    )
    triggerClientEvent(
        player,
        NEXT_CARD_EVENT,
        resourceRoot,
        (#bearers > 0 and nextCard) or false,
        bearers
    )
end)

--- The one paused reason that means nobody has decided anything yet.
--
-- `paused` and `stopped` are decisions, `rebuilding` is a transition, and an
-- identity state is a question for a person. Starting through any of them would
-- be arguing with whoever put the session down — and opening Anki's own
-- Reviewer is exactly that, with no automatic return by design (CONTEXT.md).
local UNDECIDED_SESSION = "not_started"

--- Start studying without being asked to.
--
-- The session is a consequence of Exact Card Admission, not a preference: a
-- filtered deck the add-on owns has to exist before a card can be rated
-- legitimately. Nobody needs to press a button for that to be true, and the
-- four buttons that used to exist were there because something had to be
-- pressed rather than because anything had to be decided.
local function maybeAutoStartStudy(player, study)
    if type(study) ~= "table" or study.sessionActive == true then
        return false
    end
    if study.pausedReason ~= UNDECIDED_SESSION then
        return false
    end
    local identities = activeCardIdentities()
    if not identities or #identities == 0 then
        -- Nothing is linked, so there is no session to build and no message
        -- worth sending about it.
        return false
    end
    return requestStudyStart(player, false, nil)
end

--- Whether the companion was connected the last time the status changed.
--
-- Kept so the cache is refreshed on *becoming* connected rather than on every
-- health poll that says it still is: a full note read over a reference world
-- is thousands of cards, and paying for it once a second would be paying for
-- it to say nothing changed.
local companionWasConnected = false

addEvent(STUDY_STATE_EVENT, false)
addEventHandler(STUDY_STATE_EVENT, resourceRoot, function(player, status)
    if source ~= resourceRoot or not playerAuthorization(player) then
        return
    end
    local connected = type(status) == "table" and status.state == "connected"
    if connected and not companionWasConnected
        and reviewModeInForce() == SHOW_TEXT_MODE
    then
        -- Only in the mode that draws them. Reading every linked note is
        -- thousands of cards over a reference world, and paying for it on
        -- every connection for a mode nothing displays would be spending
        -- ticket 30's budget on a cache nobody reads.
        refreshCardNoteCache(player)
    end
    companionWasConnected = connected
    local study = type(status) == "table" and status.study or nil
    if type(study) ~= "table" or study.sessionActive ~= true then
        maybeAutoStartStudy(player, study)
        -- Labels do not wait for a session, because in the mode that draws
        -- them there is never going to be one (ADR 0029).
        sendTextLabels(player)
        sendPausedStudyState(player)
        return
    end
    refreshStudyState(player)
end)

-- Link, unlink, replace and relink all pass through here, and each of them
-- changes what may activate.
addEventHandler(SESSION_INVALIDATED_EVENT, resourceRoot, function(player)
    if source == resourceRoot and playerAuthorization(player) then
        refreshStudyState(player)
    end
end)

--- Open the card a Spatial Link points at, because the player walked into it.
--
-- The client names a Map Entity; the server decides which card that is. Going
-- through `openReviewModeFor` is the point: spatial opening is not a second
-- way into Review Mode, so it cannot skip Exact Card Admission on the way.
function openSpatialReview(player, mapId, entityId, proposedIdentity)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    if type(mapId) ~= "string" or type(entityId) ~= "string" then
        return false, "invalid_map_entity"
    end
    local row, readError = ANKIGTA.Store.getMapEntity(mapId, entityId)
    if not row then
        return false, readError or "entity_missing"
    end
    if row.link_state ~= "active" then
        return false, "link_not_active"
    end
    local identity = cardIdentityFromRow(row)
    if not identity then
        return false, "invalid_card_identity"
    end
    -- A stale client proposal is refused rather than silently corrected: the
    -- card it is about is not the card it would open.
    if proposedIdentity ~= nil
        and proposedIdentity ~= false
        and not sameCardIdentity(identity, proposedIdentity)
    then
        return false, "card_changed"
    end
    return openReviewModeFor(player, identity)
end

addEvent(SPATIAL_OPEN_REQUEST_EVENT, true)
addEventHandler(SPATIAL_OPEN_REQUEST_EVENT, resourceRoot, function(
    mapId,
    entityId,
    cardIdentity
)
    if not client or source ~= resourceRoot then
        return
    end
    local opened, reason = openSpatialReview(client, mapId, entityId, cardIdentity)
    if not opened and reason ~= "review_open" then
        -- A card already being open is the ordinary case while one is open,
        -- not something to tell the player about.
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.spatialOpenFailed",
            reason
        )
    end
end)

-- Teleport -------------------------------------------------------------------

local TELEPORT_REQUEST_EVENT = "ankigta:teleportToEntity"
local TELEPORT_ARRIVED_EVENT = "ankigta:teleportArrived"

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
    local record = ANKIGTA.Store.getMapEntity(mapId, entityId)
    if not record then
        -- Not in the store: the list also offers what is merely standing in
        -- the world, and "take me to it" is most useful for exactly those --
        -- a thing you have not taken in yet is a thing you have not found.
        local element = elementByAdoptionName(entityId, player)
        if not element then
            return false, "entity_missing"
        end
        local x, y, z = getElementPosition(element)
        return ANKIGTA.Teleport.toMapEntity(player, {
            mapId = mapId,
            entityId = entityId,
            authoredX = x,
            authoredY = y,
            authoredZ = z,
            interior = getElementInterior(element) or 0,
            dimension = getElementDimension(element) or 0,
        })
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

--- The player answered "yes, remove it" about an object they deleted.
--
-- The one place a Map Entity is removed rather than marked. It happens because
-- the object is gone from the map and the player said so, and Change History
-- holds it, so an answer given too quickly is one Undo away.
function forgetMapEntity(player, mapId, entityId)
    local authorized, authorizationError = playerAuthorization(player)
    if not authorized then
        return false, authorizationError.category
    end
    if type(mapId) ~= "string" or type(entityId) ~= "string" then
        return false, "invalid_map_entity"
    end
    return ANKIGTA.Store.forgetMapEntity(mapId, entityId)
end

addEvent(FORGET_ENTITY_REQUEST_EVENT, true)
addEventHandler(FORGET_ENTITY_REQUEST_EVENT, resourceRoot, function(
    mapId, entityId
)
    if not client or source ~= resourceRoot then
        return
    end
    local forgotten, reason = forgetMapEntity(client, mapId, entityId)
    if not forgotten then
        triggerClientEvent(
            client, PENDING_NOTICE_EVENT, resourceRoot,
            "notice.forgetFailed", reason
        )
        return
    end
    invalidateStudyDependents(client, false, false, "forget")
    sendF7Snapshot(client)
end)

addEvent(TELEPORT_REQUEST_EVENT, true)
addEventHandler(TELEPORT_REQUEST_EVENT, resourceRoot, function(mapId, entityId)
    if not client or source ~= resourceRoot then
        return
    end
    local moved, reason, target = teleportPlayerToMapEntity(
        client, mapId, entityId
    )
    if not moved then
        triggerClientEvent(
            client,
            PENDING_NOTICE_EVENT,
            resourceRoot,
            "notice.teleportFailed",
            reason
        )
        return
    end
    -- Where the player now is, so the client can take the view there too. In
    -- the stock Map Editor the camera is what holds the player, and only the
    -- client can move it.
    triggerClientEvent(client, TELEPORT_ARRIVED_EVENT, resourceRoot, target)
end)

--- Stopping the resource has to reach Anki, not only the database.
--
-- A stop that only closed SQLite would leave every card of the session sitting
-- in the owned filtered deck, in a deck the user did not put them in, with
-- nothing left running to take them out (story 46). So the stop is asked for
-- here, before the store closes.
--
-- Best effort, and documented as such: MTA tears a resource's pending
-- `fetchRemote` down with the resource, so a stop issued at teardown may never
-- reach the companion. What makes that recoverable rather than lost is that
-- the companion owns the deck and rebuilds it from scratch on the next
-- session start, and that `Pause studying` and `Stop` do the same thing while
-- something is still running to hear the answer. The removal instructions in
-- `docs/operations/installation.md` say to use one of them first for exactly
-- this reason.
addEventHandler("onResourceStop", resourceRoot, function()
    for _, player in ipairs(getElementsByType("player")) do
        if playerAuthorization(player) then
            ANKIGTA.CompanionGateway.requestSessionStop(player)
            break
        end
    end
    ANKIGTA.Store.close()
end)

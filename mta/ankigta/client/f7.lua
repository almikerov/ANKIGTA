local F7_REQUEST_EVENT = "ankigta:requestF7"
local F7_SNAPSHOT_EVENT = "ankigta:f7Snapshot"
local F7_DENIED_EVENT = "ankigta:f7Denied"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"
local AUTHORIZATION_REQUEST_EVENT = "ankigta:requestAuthorization"
local PENDING_NOTICE_EVENT = "ankigta:pendingMapSaveNotice"
local RECHECK_REQUEST_EVENT = "ankigta:recheckPendingMapSave"
local COPY_DECISION_REQUEST_EVENT = "ankigta:resolveMapCopyDecision"
local CARD_PICKER_REQUEST_EVENT = "ankigta:requestCardPicker"
local CARD_PICKER_SNAPSHOT_EVENT = "ankigta:cardPickerSnapshot"
local LINK_CARD_REQUEST_EVENT = "ankigta:linkCardToEntity"
local UNLINK_CARD_REQUEST_EVENT = "ankigta:unlinkCardFromEntity"
local REPLACE_CARD_REQUEST_EVENT = "ankigta:replaceCardForEntity"
local CARD_STATE_REFRESH_REQUEST_EVENT = "ankigta:refreshCardState"
local RELINK_ENTITY_REQUEST_EVENT = "ankigta:relinkEntity"
local UNDO_REQUEST_EVENT = "ankigta:undo"
local REDO_REQUEST_EVENT = "ankigta:redo"
local PICK_ENTITY_START_EVENT = "ankigta:pickEntityStart"
local PICK_ENTITY_REQUEST_EVENT = "ankigta:pickEntity"
local PICK_ENTITY_RESULT_EVENT = "ankigta:pickEntityResult"
local PICK_ENTITY_FINISHED_EVENT = "ankigta:pickEntityFinished"
local OPEN_SETTINGS_EVENT = "ankigta:openSettings"

ANKIGTA = ANKIGTA or {}

--- Every user-facing string in this window goes through here.
-- The lookup happens when the control is written rather than when the file
-- loads, so a language change reaches the next snapshot without a restart.
local function text(key, ...)
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.format(key, ...)
    end
    return key
end

--- Display text for a Spatial Link state.
-- The state itself is a stable technical value the client compares against and
-- the server stores; only what the player reads follows the language.
local function linkStateText(state)
    return text("f7.linkState." .. tostring(state))
end

local authorized = false
local window = nil
local grid = nil
local recheckButton = nil
local copyOriginalButton = nil
local copyNewButton = nil
local relinkButton = nil
local relinkPreviewWindow = nil
local cardPickerButton = nil
local cardPickerWindow = nil
local unlinkButton = nil
local replaceButton = nil
local linkConfirmationWindow = nil
local cardGrid = nil
local cardRows = {}
local deckFilterEdit = nil
local cardSearchButton = nil
local undoButton = nil
local redoButton = nil
local selectedCardIdentity = nil
local selectedEntity = nil
local selectedEntry = nil
local cardPickerMode = "link"
local replaceOldIdentity = nil
local oldCardIdentity = nil
local newCardIdentity = nil
local entityRows = {}
local relinkSource = nil
local relinkTarget = nil
local selectedMapId = nil
local selectedEntityId = nil
local pendingRelinkSourceMapId = nil
local pendingRelinkSourceEntityId = nil
local pendingMapId = nil
local pendingEntityId = nil
local copyMapId = nil
local copyEntityId = nil
local cursorOwned = false
local cursorWasShowing = false
-- Kept so the window can be rebuilt in another language without asking the
-- server for the same rows again.
local lastSnapshot = nil
local lastCardPickerSnapshot = nil

local function closeF7()
    if isElement(window) then
        destroyElement(window)
    end
    window = nil
    grid = nil
    recheckButton = nil
    copyOriginalButton = nil
    copyNewButton = nil
    relinkButton = nil
    cardPickerButton = nil
    unlinkButton = nil
    replaceButton = nil
    if isElement(cardPickerWindow) then
        destroyElement(cardPickerWindow)
    end
    cardPickerWindow = nil
    cardGrid = nil
    cardRows = {}
    deckFilterEdit = nil
    cardSearchButton = nil
    undoButton = nil
    redoButton = nil
    selectedCardIdentity = nil
    selectedEntity = nil
    selectedEntry = nil
    cardPickerMode = "link"
    replaceOldIdentity = nil
    oldCardIdentity = nil
    newCardIdentity = nil
    entityRows = {}
    relinkSource = nil
    relinkTarget = nil
    pendingMapId = nil
    pendingEntityId = nil
    copyMapId = nil
    copyEntityId = nil
    if cursorOwned then
        showCursor(cursorWasShowing)
        cursorOwned = false
        cursorWasShowing = false
    end
    if isElement(relinkPreviewWindow) then
        destroyElement(relinkPreviewWindow)
    end
    relinkPreviewWindow = nil
    if isElement(linkConfirmationWindow) then
        destroyElement(linkConfirmationWindow)
    end
    linkConfirmationWindow = nil
end

local function runtimeStatus(runtime)
    if not runtime.available then
        return text("f7.runtime.destroyed")
    end

    local element = getElementByID(runtime.referenceId)
    if not isElement(element) or not isElementStreamedIn(element) then
        return text("f7.runtime.notStreamed")
    end

    return text("f7.runtime.streamed")
end

local function authoredPosition(mapEntity)
    local position = mapEntity.authored.position
    local world = mapEntity.authored.world
    return text(
        "f7.authoredPosition",
        position.x,
        position.y,
        position.z,
        world.interior,
        world.dimension
    )
end

local function metadataSummary(entry)
    local metadata = entry.metadata or entry.link.metadata or {}
    -- The name and the Entity Tag are the user's own words and are substituted
    -- in untouched; only the labels around them are translated.
    return text(
        "f7.metadataSummary",
        tostring(metadata.name or ""),
        tostring(metadata.entityTag or ""),
        tonumber(metadata.radius) or 3,
        metadata.showRadius and text("common.yes") or text("common.no")
    )
end

local function renderRelinkPreview()
    if not relinkSource then
        return
    end
    if isElement(relinkPreviewWindow) then
        destroyElement(relinkPreviewWindow)
    end
    local width = 700
    local height = 230
    local screenWidth, screenHeight = guiGetScreenSize()
    relinkPreviewWindow = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        text("f7.relink.title"),
        false
    )
    guiCreateLabel(
        16,
        32,
        width - 32,
        42,
        text(
            "f7.relink.missing",
            relinkSource.mapEntity.mapId .. "/"
                .. relinkSource.mapEntity.entityId
        ),
        false,
        relinkPreviewWindow
    )
    guiCreateLabel(
        16,
        76,
        width - 32,
        42,
        text(
            "f7.relink.target",
            relinkTarget
                and relinkTarget.mapEntity.mapId .. "/"
                    .. relinkTarget.mapEntity.entityId
                or text("f7.relink.chooseTarget")
        ),
        false,
        relinkPreviewWindow
    )
    guiCreateLabel(
        16,
        120,
        width - 32,
        42,
        text("f7.relink.metadataMoved", metadataSummary(relinkSource)),
        false,
        relinkPreviewWindow
    )
    local confirmButton = guiCreateButton(
        width - 270,
        height - 38,
        116,
        26,
        text("common.confirm"),
        false,
        relinkPreviewWindow
    )
    local cancelButton = guiCreateButton(
        width - 140,
        height - 38,
        116,
        26,
        text("common.cancel"),
        false,
        relinkPreviewWindow
    )
    guiSetEnabled(confirmButton, relinkTarget ~= nil)
    local pickTargetButton = guiCreateButton(
        16,
        height - 38,
        116,
        26,
        text("f7.relink.pickTarget"),
        false,
        relinkPreviewWindow
    )
    addEventHandler("onClientGUIClick", pickTargetButton, function()
        pendingRelinkSourceMapId = relinkSource.mapEntity.mapId
        pendingRelinkSourceEntityId = relinkSource.mapEntity.entityId
        destroyElement(relinkPreviewWindow)
        relinkPreviewWindow = nil
        closeF7()
        triggerEvent(PICK_ENTITY_START_EVENT, resourceRoot, "relink")
    end, false)
    addEventHandler("onClientGUIClick", confirmButton, function()
        if relinkTarget then
            triggerServerEvent(
                RELINK_ENTITY_REQUEST_EVENT,
                resourceRoot,
                relinkSource.mapEntity.mapId,
                relinkSource.mapEntity.entityId,
                relinkTarget.mapEntity.mapId,
                relinkTarget.mapEntity.entityId
            )
        end
        destroyElement(relinkPreviewWindow)
        relinkPreviewWindow = nil
        pendingRelinkSourceMapId = nil
        pendingRelinkSourceEntityId = nil
    end, false)
    addEventHandler("onClientGUIClick", cancelButton, function()
        pendingRelinkSourceMapId = nil
        pendingRelinkSourceEntityId = nil
        destroyElement(relinkPreviewWindow)
        relinkPreviewWindow = nil
    end, false)
end

local function linkIdentityText(identity)
    if type(identity) ~= "table" then
        return text("common.empty")
    end
    return text(
        "f7.cardIdentity",
        tostring(identity.collectionUuid or ""),
        tostring(identity.cardId or "")
    )
end

local function linkCanBeChanged(entry)
    if not entry or type(entry.link) ~= "table" then
        return false
    end
    return entry.link.state == "Active Spatial Link"
        or entry.link.state == "Card missing"
end

local function renderUnlinkConfirmation(entry)
    if not entry or not linkCanBeChanged(entry) then
        return
    end
    if isElement(linkConfirmationWindow) then
        destroyElement(linkConfirmationWindow)
    end
    local width = 620
    local height = 190
    local screenWidth, screenHeight = guiGetScreenSize()
    linkConfirmationWindow = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        text("f7.unlink.title"),
        false
    )
    guiCreateLabel(
        16,
        32,
        width - 32,
        40,
        text(
            "f7.entityLabel",
            entry.mapEntity.mapId .. "/" .. entry.mapEntity.entityId
        ),
        false,
        linkConfirmationWindow
    )
    guiCreateLabel(
        16,
        72,
        width - 32,
        40,
        text("f7.cardLabel", linkIdentityText(entry.link.cardIdentity)),
        false,
        linkConfirmationWindow
    )
    guiCreateLabel(
        16,
        112,
        width - 32,
        28,
        text("f7.unlink.explanation"),
        false,
        linkConfirmationWindow
    )
    local confirmButton = guiCreateButton(
        width - 270,
        height - 38,
        116,
        26,
        text("f7.unlink.confirm"),
        false,
        linkConfirmationWindow
    )
    local cancelButton = guiCreateButton(
        width - 140,
        height - 38,
        116,
        26,
        text("common.cancel"),
        false,
        linkConfirmationWindow
    )
    addEventHandler("onClientGUIClick", confirmButton, function()
        triggerServerEvent(
            UNLINK_CARD_REQUEST_EVENT,
            resourceRoot,
            entry.mapEntity.mapId,
            entry.mapEntity.entityId,
            entry.link.cardIdentity
        )
        destroyElement(linkConfirmationWindow)
        linkConfirmationWindow = nil
    end, false)
    addEventHandler("onClientGUIClick", cancelButton, function()
        destroyElement(linkConfirmationWindow)
        linkConfirmationWindow = nil
    end, false)
end

local function renderReplaceConfirmation(entry, oldIdentity, newIdentity)
    if not entry or not linkCanBeChanged(entry) then
        return
    end
    if isElement(linkConfirmationWindow) then
        destroyElement(linkConfirmationWindow)
    end
    local width = 650
    local height = 210
    local screenWidth, screenHeight = guiGetScreenSize()
    linkConfirmationWindow = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        text("f7.replace.title"),
        false
    )
    guiCreateLabel(
        16,
        32,
        width - 32,
        32,
        text(
            "f7.entityLabel",
            entry.mapEntity.mapId .. "/" .. entry.mapEntity.entityId
        ),
        false,
        linkConfirmationWindow
    )
    guiCreateLabel(
        16,
        68,
        width - 32,
        32,
        text("f7.replace.oldCard", linkIdentityText(oldIdentity)),
        false,
        linkConfirmationWindow
    )
    guiCreateLabel(
        16,
        104,
        width - 32,
        32,
        text("f7.replace.newCard", linkIdentityText(newIdentity)),
        false,
        linkConfirmationWindow
    )
    guiCreateLabel(
        16,
        140,
        width - 32,
        28,
        text("f7.replace.explanation"),
        false,
        linkConfirmationWindow
    )
    local confirmButton = guiCreateButton(
        width - 270,
        height - 38,
        116,
        26,
        text("f7.replace.confirm"),
        false,
        linkConfirmationWindow
    )
    local cancelButton = guiCreateButton(
        width - 140,
        height - 38,
        116,
        26,
        text("common.cancel"),
        false,
        linkConfirmationWindow
    )
    addEventHandler("onClientGUIClick", confirmButton, function()
        triggerServerEvent(
            REPLACE_CARD_REQUEST_EVENT,
            resourceRoot,
            entry.mapEntity.mapId,
            entry.mapEntity.entityId,
            oldIdentity,
            newIdentity
        )
        destroyElement(linkConfirmationWindow)
        linkConfirmationWindow = nil
    end, false)
    addEventHandler("onClientGUIClick", cancelButton, function()
        destroyElement(linkConfirmationWindow)
        linkConfirmationWindow = nil
    end, false)
end

local function renderSnapshot(snapshot)
    closeF7()

    local width = 900
    local height = 360
    local screenWidth, screenHeight = guiGetScreenSize()
    window = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        text("f7.title"),
        false
    )
    grid = guiCreateGridList(16, 32, width - 32, height - 84, false, window)
    guiGridListAddColumn(grid, text("f7.column.mapEntity"), 0.17)
    guiGridListAddColumn(grid, text("f7.column.type"), 0.08)
    guiGridListAddColumn(grid, text("f7.column.authored"), 0.29)
    guiGridListAddColumn(grid, text("f7.column.runtime"), 0.24)
    guiGridListAddColumn(grid, text("f7.column.link"), 0.18)

    local hasPending = false
    entityRows = {}
    relinkSource = nil
    relinkTarget = nil
    for _, entry in ipairs(snapshot.entities) do
        local row = guiGridListAddRow(grid)
        entityRows[row] = entry
        local mapEntity = entry.mapEntity
        guiGridListSetItemText(
            grid,
            row,
            1,
            mapEntity.mapId .. " / " .. mapEntity.entityId,
            false,
            false
        )
        guiGridListSetItemText(grid, row, 2, mapEntity.type, false, false)
        guiGridListSetItemText(
            grid,
            row,
            3,
            authoredPosition(mapEntity),
            false,
            false
        )
        guiGridListSetItemText(
            grid,
            row,
            4,
            runtimeStatus(entry.runtimeInstance),
            false,
            false
        )
        local linkText = linkStateText(entry.link.state)
        if entry.link.guidanceKey then
            linkText = linkText .. " — " .. text(entry.link.guidanceKey)
        end
        guiGridListSetItemText(grid, row, 5, linkText, false, false)
        hasPending = hasPending or entry.link.recheckAvailable == true
        if entry.link.copyCollision == true then
            copyMapId = mapEntity.mapId
            copyEntityId = mapEntity.entityId
            linkText = linkText .. " — " .. text("f7.copyDecisionHint")
            guiGridListSetItemText(grid, row, 5, linkText, false, false)
        end
        if entry.link.recheckAvailable == true then
            pendingMapId = mapEntity.mapId
            pendingEntityId = mapEntity.entityId
        end
        if (entry.link.state == "Active Spatial Link"
                or entry.link.state == "Card missing")
            and entry.link.cardIdentity
        then
            triggerServerEvent(
                CARD_STATE_REFRESH_REQUEST_EVENT,
                resourceRoot,
                entry.link.cardIdentity
            )
        end
    end
    addEventHandler("onClientGUIClick", grid, function()
        local selectedRow = guiGridListGetSelectedItem(grid)
        local entry = entityRows[selectedRow]
        if not entry then
            return
        end
        selectedEntry = entry
        selectedEntity = entry.mapEntity
        if entry.link.state == "Entity missing"
            and entry.link.relinkAvailable == true
        then
            relinkSource = entry
        elseif entry.link.state == "Unlinked" then
            relinkTarget = entry
        else
            relinkSource = nil
            relinkTarget = nil
        end
        if isElement(relinkButton) then
            guiSetEnabled(
                relinkButton,
                relinkSource ~= nil
            )
        end
        if isElement(unlinkButton) then
            guiSetEnabled(unlinkButton, linkCanBeChanged(entry))
        end
        if isElement(replaceButton) then
            guiSetEnabled(replaceButton, linkCanBeChanged(entry))
        end
    end, false)

    if selectedMapId and selectedEntityId then
        for row, entry in pairs(entityRows) do
            local mapEntity = entry.mapEntity
            if mapEntity.mapId == selectedMapId
                and mapEntity.entityId == selectedEntityId
            then
                guiGridListSetSelectedItem(grid, row, 1)
                selectedEntity = mapEntity
                selectedEntry = entry
                break
            end
        end
    end

    if pendingRelinkSourceMapId and pendingRelinkSourceEntityId then
        for _, entry in pairs(entityRows) do
            local mapEntity = entry.mapEntity
            if mapEntity.mapId == pendingRelinkSourceMapId
                and mapEntity.entityId == pendingRelinkSourceEntityId
            then
                relinkSource = entry
            end
            if mapEntity.mapId == selectedMapId
                and mapEntity.entityId == selectedEntityId
            then
                relinkTarget = entry
            end
        end
    end

    recheckButton = guiCreateButton(
        width - 190,
        height - 42,
        174,
        26,
        text("f7.recheck"),
        false,
        window
    )
    guiSetEnabled(recheckButton, hasPending)
    addEventHandler("onClientGUIClick", recheckButton, function()
        if pendingMapId and pendingEntityId then
            triggerServerEvent(
                RECHECK_REQUEST_EVENT,
                resourceRoot,
                pendingMapId,
                pendingEntityId
            )
        end
    end, false)

    copyOriginalButton = guiCreateButton(
        16,
        height - 74,
        180,
        26,
        text("f7.copyOriginal"),
        false,
        window
    )
    copyNewButton = guiCreateButton(
        204,
        height - 74,
        140,
        26,
        text("f7.copyNew"),
        false,
        window
    )
    guiSetEnabled(copyOriginalButton, copyMapId ~= nil)
    guiSetEnabled(copyNewButton, copyMapId ~= nil)
    addEventHandler("onClientGUIClick", copyOriginalButton, function()
        if copyMapId and copyEntityId then
            triggerServerEvent(
                COPY_DECISION_REQUEST_EVENT,
                resourceRoot,
                copyMapId,
                copyEntityId,
                "original_or_renamed"
            )
        end
    end, false)
    addEventHandler("onClientGUIClick", copyNewButton, function()
        if copyMapId and copyEntityId then
            triggerServerEvent(
                COPY_DECISION_REQUEST_EVENT,
                resourceRoot,
                copyMapId,
                copyEntityId,
                "new_copy"
            )
        end
    end, false)

    relinkButton = guiCreateButton(
        292,
        height - 42,
        150,
        26,
        text("f7.relink"),
        false,
        window
    )
    guiSetEnabled(
        relinkButton,
        relinkSource ~= nil
    )
    addEventHandler("onClientGUIClick", relinkButton, function()
        renderRelinkPreview()
    end, false)

    unlinkButton = guiCreateButton(
        16,
        height - 42,
        120,
        26,
        text("f7.unlink"),
        false,
        window
    )
    replaceButton = guiCreateButton(
        144,
        height - 42,
        140,
        26,
        text("f7.replaceCard"),
        false,
        window
    )
    guiSetEnabled(unlinkButton, false)
    guiSetEnabled(replaceButton, false)
    addEventHandler("onClientGUIClick", unlinkButton, function()
        renderUnlinkConfirmation(selectedEntry)
    end, false)
    addEventHandler("onClientGUIClick", replaceButton, function()
        if selectedEntry and linkCanBeChanged(selectedEntry) then
            cardPickerMode = "replace"
            replaceOldIdentity = selectedEntry.link.cardIdentity
            oldCardIdentity = replaceOldIdentity
            triggerServerEvent(CARD_PICKER_REQUEST_EVENT, resourceRoot)
        end
    end, false)

    cardPickerButton = guiCreateButton(
        532,
        height - 74,
        150,
        26,
        text("f7.cardPicker"),
        false,
        window
    )
    local hasUnlinkedEntity = false
    for _, entry in ipairs(snapshot.entities) do
        if entry.link.state == "Unlinked" then
            hasUnlinkedEntity = true
            if not selectedEntry then
                selectedEntry = entry
                selectedEntity = entry.mapEntity
            end
            break
        end
    end
    guiSetEnabled(
        cardPickerButton,
        (hasUnlinkedEntity or selectedEntry ~= nil) and snapshot.cardPicker
            and snapshot.cardPicker.enabled == true
    )
    addEventHandler("onClientGUIClick", cardPickerButton, function()
        if selectedEntry and selectedEntry.link.state == "Unlinked" then
            cardPickerMode = "link"
            triggerServerEvent(CARD_PICKER_REQUEST_EVENT, resourceRoot)
        end
    end, false)

    local pickEntityButton = guiCreateButton(
        700,
        height - 74,
        174,
        26,
        text("f7.pickEntity"),
        false,
        window
    )
    guiSetEnabled(pickEntityButton, #snapshot.entities > 0)
    addEventHandler("onClientGUIClick", pickEntityButton, function()
        closeF7()
        triggerEvent(PICK_ENTITY_START_EVENT, resourceRoot, "pick")
    end, false)

    local settingsButton = guiCreateButton(
        360,
        height - 74,
        150,
        26,
        text("settings.title"),
        false,
        window
    )
    addEventHandler("onClientGUIClick", settingsButton, function()
        triggerEvent(OPEN_SETTINGS_EVENT, resourceRoot)
    end, false)

    undoButton = guiCreateButton(
        512,
        height - 42,
        88,
        26,
        text("f7.undo"),
        false,
        window
    )
    redoButton = guiCreateButton(
        606,
        height - 42,
        88,
        26,
        text("f7.redo"),
        false,
        window
    )
    local history = snapshot.history or {}
    guiSetEnabled(undoButton, history.canUndo == true)
    guiSetEnabled(redoButton, history.canRedo == true)
    addEventHandler("onClientGUIClick", undoButton, function()
        triggerServerEvent(UNDO_REQUEST_EVENT, resourceRoot)
    end, false)
    addEventHandler("onClientGUIClick", redoButton, function()
        triggerServerEvent(REDO_REQUEST_EVENT, resourceRoot)
    end, false)

    cursorWasShowing = isCursorShowing()
    cursorOwned = true
    showCursor(true)
end

addEvent(PICK_ENTITY_START_EVENT, false)
addEvent(PICK_ENTITY_FINISHED_EVENT, false)
addEventHandler(PICK_ENTITY_FINISHED_EVENT, resourceRoot, function(
    success,
    reason,
    mapId,
    entityId,
    mode
)
    if success == true then
        selectedMapId = mapId
        selectedEntityId = entityId
    elseif mode == "relink" then
        pendingRelinkSourceMapId = nil
        pendingRelinkSourceEntityId = nil
    end
    if mode == "relink" and success ~= true then
        outputChatBox(
            text("notice.relinkFailed", tostring(reason)),
            255,
            196,
            64
        )
    elseif success ~= true and reason ~= "resource_stop" then
        outputChatBox(
            text("notice.pickEntityFailed", tostring(reason)),
            255,
            196,
            64
        )
    end
    if reason ~= "resource_stop" then
        triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
    end
end)

local function renderCardPicker(snapshot)
    if isElement(cardPickerWindow) then
        destroyElement(cardPickerWindow)
    end
    selectedCardIdentity = nil
    local width = 620
    local height = 320
    local screenWidth, screenHeight = guiGetScreenSize()
    cardPickerWindow = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        cardPickerMode == "replace"
            and text("cardPicker.replaceTitle")
            or text("cardPicker.title"),
        false
    )
    deckFilterEdit = guiCreateEdit(
        16, 32, width - 220, 26, "", false, cardPickerWindow
    )
    guiSetProperty(deckFilterEdit, "NormalTextColour", "FF000000")
    cardSearchButton = guiCreateButton(
        width - 190,
        32,
        174,
        26,
        text("cardPicker.search"),
        false,
        cardPickerWindow
    )
    cardGrid = guiCreateGridList(
        16, 66, width - 32, height - 110, false, cardPickerWindow
    )
    guiGridListAddColumn(cardGrid, text("cardPicker.column.card"), 0.22)
    guiGridListAddColumn(cardGrid, text("cardPicker.column.deck"), 0.28)
    guiGridListAddColumn(cardGrid, text("cardPicker.column.state"), 0.22)
    guiGridListAddColumn(cardGrid, text("cardPicker.column.collection"), 0.24)
    cardRows = {}
    for _, card in ipairs(snapshot.cards or {}) do
        local row = guiGridListAddRow(cardGrid)
        local identity = card.identity or {}
        local deck = card.deck or {}
        guiGridListSetItemText(
            cardGrid, row, 1, tostring(identity.cardId or ""), false, false
        )
        guiGridListSetItemText(
            cardGrid, row, 2, tostring(deck.name or ""), false, false
        )
        guiGridListSetItemText(
            cardGrid, row, 3, tostring(card.state or ""), false, false
        )
        guiGridListSetItemText(
            cardGrid, row, 4, tostring(identity.collectionUuid or ""), false, false
        )
        local existingNames = {}
        for _, link in ipairs(snapshot.existingLinks or {}) do
            if link.collectionUuid == identity.collectionUuid
                and tonumber(link.cardId) == tonumber(identity.cardId)
            then
                table.insert(
                    existingNames,
                    tostring(link.mapId) .. "/" .. tostring(link.entityId)
                )
            end
        end
        if #existingNames > 0 then
            guiGridListSetItemText(
                cardGrid,
                row,
                3,
                text(
                    "cardPicker.alreadyLinked",
                    tostring(card.state or ""),
                    table.concat(existingNames, ", ")
                ),
                false,
                false
            )
        end
        cardRows[row] = identity
    end
    local linkButton = guiCreateButton(
        width - 210,
        height - 36,
        194,
        26,
        cardPickerMode == "replace"
            and text("cardPicker.previewReplacement")
            or text("cardPicker.link"),
        false,
        cardPickerWindow
    )
    guiSetEnabled(linkButton, false)
    addEventHandler("onClientGUIClick", cardGrid, function()
        local row = guiGridListGetSelectedItem(cardGrid)
        selectedCardIdentity = cardRows[row]
        guiSetEnabled(
            linkButton,
            selectedCardIdentity ~= nil and selectedEntity ~= nil
        )
    end, false)
    addEventHandler("onClientGUIClick", linkButton, function()
        if selectedCardIdentity and selectedEntry then
            if cardPickerMode == "replace" then
                newCardIdentity = selectedCardIdentity
                renderReplaceConfirmation(
                    selectedEntry,
                    oldCardIdentity,
                    newCardIdentity
                )
            else
                triggerServerEvent(
                    LINK_CARD_REQUEST_EVENT,
                    resourceRoot,
                    selectedEntry.mapEntity.mapId,
                    selectedEntry.mapEntity.entityId,
                    selectedCardIdentity
                )
            end
        end
    end, false)
    addEventHandler("onClientGUIClick", cardSearchButton, function()
        local deckFilter = guiGetText(deckFilterEdit)
        triggerServerEvent(
            CARD_PICKER_REQUEST_EVENT,
            resourceRoot,
            "",
            deckFilter,
            0,
            50
        )
    end, false)
end

local function requestF7()
    if not authorized then
        return
    end
    if type(isPickEntityActive) == "function" and isPickEntityActive() then
        return
    end

    if isElement(window) then
        closeF7()
        return
    end

    triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
end

bindKey("F7", "down", requestF7)

addEvent(AUTHORIZATION_EVENT, true)
addEventHandler(AUTHORIZATION_EVENT, resourceRoot, function(value)
    authorized = value == true
    if not authorized then
        closeF7()
    end
end)

addEvent(F7_SNAPSHOT_EVENT, true)
addEventHandler(F7_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if authorized and type(snapshot) == "table" and snapshot.visible == true then
        lastSnapshot = snapshot
        renderSnapshot(snapshot)
    end
end)

-- Rebuilt from the snapshot already in hand rather than re-asked for: the
-- language is a client-side setting, and a window open while the player changes
-- it has no business waiting on the server to read differently.
if ANKIGTA.Locale then
    ANKIGTA.Locale.onChange(function()
        -- Read before rebuilding: rebuilding the main window closes the Card
        -- Picker and resets the mode it was opened in.
        local hadWindow = isElement(window)
        local hadPicker = isElement(cardPickerWindow)
        local pickerMode = cardPickerMode
        local pickerOldIdentity = oldCardIdentity
        -- What the player typed is theirs; a relabel must not throw it away.
        local deckFilter = hadPicker and guiGetText(deckFilterEdit) or nil
        if hadWindow and lastSnapshot then
            renderSnapshot(lastSnapshot)
        end
        if hadPicker and lastCardPickerSnapshot then
            cardPickerMode = pickerMode
            oldCardIdentity = pickerOldIdentity
            renderCardPicker(lastCardPickerSnapshot)
            if deckFilter then
                guiSetText(deckFilterEdit, deckFilter)
            end
        end
    end)
end

addEvent(F7_DENIED_EVENT, true)
addEventHandler(F7_DENIED_EVENT, resourceRoot, function()
    authorized = false
    closeF7()
end)

addEvent(CARD_PICKER_SNAPSHOT_EVENT, true)
addEventHandler(CARD_PICKER_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if authorized and type(snapshot) == "table" and snapshot.enabled == true then
        lastCardPickerSnapshot = snapshot
        renderCardPicker(snapshot)
    end
end)

addEvent(PENDING_NOTICE_EVENT, true)
-- The server sends the key and the outcome code, never a sentence: the language
-- is a client-owned setting (ADR 0014), so only this side knows which one to
-- render. The outcome code is a stable technical value and is passed through.
addEventHandler(PENDING_NOTICE_EVENT, resourceRoot, function(noticeKey, outcome)
    if type(noticeKey) == "string" then
        outputChatBox(text(noticeKey, tostring(outcome)), 255, 196, 64)
    end
end)

addEventHandler("onClientResourceStart", resourceRoot, function()
    triggerServerEvent(AUTHORIZATION_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, closeF7)

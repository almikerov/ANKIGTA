ANKIGTA = ANKIGTA or {}

-- The panel.
--
-- One local CEF page behind F7, in place of the windows this resource had
-- grown: connection, entities, Card Picker, settings. The page is a view — it
-- holds no state of its own and decides nothing. This file owns the state,
-- pushes it in whole, and takes named actions back.
--
-- Local, not remote, and that is load-bearing: the browser process only
-- honours `window.mta` for a local browser (prototype 0006), so a panel
-- created remote would render and then be deaf.

local PANEL_ACTION_EVENT = "ankigta:panelAction"
local STATUS_EVENT = "ankigta:companionStatus"
local F7_REQUEST_EVENT = "ankigta:requestF7"
local F7_SNAPSHOT_EVENT = "ankigta:f7Snapshot"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"
local AUTHORIZATION_REQUEST_EVENT = "ankigta:requestAuthorization"
local CONNECT_EVENT = "ankigta:connectCompanion"
local SETTINGS_UPDATE_EVENT = "ankigta:updateConnectionSettings"
local START_STUDY_REQUEST_EVENT = "ankigta:startStudy"
local OPEN_SETTINGS_EVENT = "ankigta:openSettings"
local STATUS_REQUEST_EVENT = "ankigta:requestCompanionStatus"
local RECHECK_REQUEST_EVENT = "ankigta:recheckPendingMapSave"
local COPY_DECISION_REQUEST_EVENT = "ankigta:resolveMapCopyDecision"
local CARD_PICKER_REQUEST_EVENT = "ankigta:requestCardPicker"
local CARD_PICKER_SNAPSHOT_EVENT = "ankigta:cardPickerSnapshot"
local LINK_CARD_REQUEST_EVENT = "ankigta:linkCardToEntity"
local UNLINK_CARD_REQUEST_EVENT = "ankigta:unlinkCardFromEntity"
local REPLACE_CARD_REQUEST_EVENT = "ankigta:replaceCardForEntity"
local RELINK_ENTITY_REQUEST_EVENT = "ankigta:relinkEntity"
local UNDO_REQUEST_EVENT = "ankigta:undo"
local REDO_REQUEST_EVENT = "ankigta:redo"
local PICK_ENTITY_START_EVENT = "ankigta:pickEntityStart"
local PICK_ENTITY_FINISHED_EVENT = "ankigta:pickEntityFinished"
local PENDING_NOTICE_EVENT = "ankigta:pendingMapSaveNotice"
local PAGE_URL = "http://mta/local/client/panel/index.html"

local authorized = false
local guiBrowser = nil
local browser = nil
local pageReady = false
local cursorOwned = false
local cursorWasShowing = false

-- The last thing each source told us. The page is redrawn from these, so a
-- language change or a new status repaints without asking anyone again.
local lastStatus = nil
local lastSnapshot = nil
local lastCards = nil
-- What the player picked, kept here rather than on the page: the page is a
-- view, and a selection the two sides disagree about is how a confirmation
-- ends up acting on the wrong row.
local selectedMapId = nil
local selectedEntityId = nil
local selectedCard = nil
local notice = false
-- Set when Pick Entity was started to choose a relink target.
local relinkSourceMapId = nil
local relinkSourceEntityId = nil
-- Set where a selection arrives from the world, read and cleared by the next
-- render. One-shot on purpose: a filter typed *after* the pick is the player's
-- latest word and must survive.
local selectionArrivedFromOutside = false
-- What the player typed to narrow the list. Kept here so a rebuild for another
-- language does not throw away their filter.
local entityFilter = ""
-- When the panel and the last search were asked for, so the report can say how
-- long each took rather than only that it arrived. Measured on this side,
-- because this is the side that waits.
local panelRequestedAt = false
local searchRequestedAt = false

local function record(section, values)
    if ANKIGTA.Diagnostics then
        ANKIGTA.Diagnostics.record(section, values)
    end
end

function isPanelOpen()
    return isElement(guiBrowser)
end

--- Give the cursor back exactly as it was found.
-- Called from every path that ends the panel, including the one where the
-- browser could not be created: a panel that fails to open must not leave the
-- player holding a cursor they cannot dismiss.
local function releaseCursor()
    if not cursorOwned then
        return
    end
    showCursor(cursorWasShowing)
    cursorOwned = false
    cursorWasShowing = false
end

local function takeCursor()
    if cursorOwned then
        return
    end
    cursorWasShowing = isCursorShowing()
    cursorOwned = true
    showCursor(true)
end

local function closePanel()
    if isElement(guiBrowser) then
        destroyElement(guiBrowser)
    end
    guiBrowser = nil
    browser = nil
    pageReady = false
    releaseCursor()
end

--- Which section the panel should be showing.
-- Not a stored preference: it follows the state of the world, because the
-- reason to open the panel with no connection is always the connection.
local function section()
    if not lastStatus or lastStatus.state ~= "connected" then
        return "connection"
    end
    return "entities"
end

--- Rank a row the way a reader thinks about it.
-- Never by raw identifier. A Map Entity someone has already linked is the one
-- they came back for; one that needs a decision is the one that cannot wait;
-- the rest are alphabetical so the list does not move around underneath them.
local LINK_STATE_RANK = {
    ["Identity Collision"] = 1,
    ["Pending Map Save"] = 2,
    ["Entity missing"] = 3,
    ["Card missing"] = 4,
    ["Active Spatial Link"] = 5,
    ["Unlinked"] = 6,
}

--- Which of the three things a Runtime Instance can be right now.
--
-- Decided on this side because only this side can look at the element: the
-- server knows whether the Map Entity still exists, not whether it is
-- streamed in around the player.
local function runtimeStatusKey(runtime)
    if type(runtime) ~= "table" or not runtime.available then
        return "f7.runtime.destroyed"
    end
    local element = getElementByID(runtime.referenceId)
    if not isElement(element) or not isElementStreamedIn(element) then
        return "f7.runtime.notStreamed"
    end
    return "f7.runtime.streamed"
end

--- Does this entry answer to what was typed?
--
-- Over the *stored* record, never over what happens to be streamed in: an
-- entity whose Runtime Instance is gone is found by the same words that find
-- one standing in front of the player (story 51). Plain substring, not a
-- pattern, so a name with brackets in it is searchable by its brackets.
local function matches(entry, query)
    if query == "" then
        return true
    end
    local needle = string.lower(query)
    local mapEntity = entry.mapEntity
    local metadata = entry.metadata or entry.link and entry.link.metadata or {}
    local haystacks = {
        mapEntity.mapId,
        mapEntity.entityId,
        mapEntity.type,
        metadata.name,
        metadata.entityTag,
        entry.link and entry.link.state,
    }
    for _, value in ipairs(haystacks) do
        if type(value) == "string"
            and string.find(string.lower(value), needle, 1, true)
        then
            return true
        end
    end
    return false
end

--- The entries a query keeps, in the order they arrived.
-- Exposed as a pure function because the rule is worth testing without a
-- window, a page or a render in the way.
function panelMatching(entities, query)
    local kept = {}
    for _, entry in ipairs(entities or {}) do
        if matches(entry, query or "") then
            table.insert(kept, entry)
        end
    end
    return kept
end

--- Drop a filter that would hide something the player must see.
--
-- Picking an entity in the world and finding an empty list is the filter
-- winning an argument it should not be in. The same holds for the source of a
-- relink in progress: hiding it strands the operation half-done.
local function dropFilterHiding(snapshot)
    if entityFilter == "" then
        return
    end
    for _, entry in ipairs(snapshot and snapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        local mustShow = (
            selectionArrivedFromOutside
            and mapEntity.mapId == selectedMapId
            and mapEntity.entityId == selectedEntityId
        ) or (
            mapEntity.mapId == relinkSourceMapId
            and mapEntity.entityId == relinkSourceEntityId
        )
        if mustShow and not matches(entry, entityFilter) then
            entityFilter = ""
            return
        end
    end
end

local function entityRows(snapshot)
    dropFilterHiding(snapshot)
    selectionArrivedFromOutside = false
    local rows = {}
    for _, entry in ipairs(snapshot and snapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        table.insert(rows, {
            mapId = mapEntity.mapId,
            entityId = mapEntity.entityId,
            type = mapEntity.type,
            name = entry.metadata and entry.metadata.name
                or entry.link.metadata and entry.link.metadata.name
                or "",
            linkState = entry.link.state,
            guidanceKey = entry.link.guidanceKey or false,
            runtimeKey = runtimeStatusKey(entry.runtimeInstance),
            recheckAvailable = entry.link.recheckAvailable == true,
            copyCollision = entry.link.copyCollision == true,
        })
        if not matches(entry, entityFilter) then
            table.remove(rows)
        end
    end
    table.sort(rows, function(left, right)
        local leftRank = LINK_STATE_RANK[left.linkState] or 99
        local rightRank = LINK_STATE_RANK[right.linkState] or 99
        if leftRank ~= rightRank then
            return leftRank < rightRank
        end
        local leftName = left.name ~= "" and left.name or left.entityId
        local rightName = right.name ~= "" and right.name or right.entityId
        if leftName ~= rightName then
            return leftName < rightName
        end
        -- Total, so two rows never swap places between one render and the next.
        return left.mapId < right.mapId
    end)
    return rows
end

--- The Card Picker's rows, in an order a reader can follow.
--
-- Never by cardId. The deck is what someone searched by, the state is what
-- decides whether the card can be used at all, and the id is the tie-break of
-- last resort rather than the first sort key.
local function cardRows(snapshot)
    local rows = {}
    for _, card in ipairs(snapshot and snapshot.cards or {}) do
        local identity = card.identity or {}
        local deck = card.deck or {}
        table.insert(rows, {
            cardId = tostring(identity.cardId or ""),
            collectionUuid = tostring(identity.collectionUuid or ""),
            deck = tostring(deck.name or ""),
            state = tostring(card.state or ""),
            question = tostring(card.question or ""),
            linkedTo = card.linkedTo or false,
        })
    end
    table.sort(rows, function(left, right)
        if left.deck ~= right.deck then
            return left.deck < right.deck
        end
        if left.state ~= right.state then
            return left.state < right.state
        end
        return left.cardId < right.cardId
    end)
    return rows
end

local function localeTable()
    local strings = ANKIGTA.Locale and ANKIGTA.Locale.strings
    if not strings then
        return {}
    end
    local active = strings[ANKIGTA.Locale.language] or {}
    local merged = {}
    -- English underneath, so a key the active language lacks still renders as
    -- words rather than as its own name.
    for key, value in pairs(strings.en or {}) do
        merged[key] = value
    end
    for key, value in pairs(active) do
        merged[key] = value
    end
    return merged
end

--- What the top bar says about studying.
--
-- A line, not a menu. The session lifts itself when nobody has decided
-- otherwise, so the only action worth offering is the way back from a decision
-- someone made -- and that one is offered only when it applies.
local function studyState()
    local study = lastStatus and lastStatus.study or nil
    if type(study) ~= "table" then
        return {active = false, resumable = false}
    end
    local pausedReason = study.pausedReason or false
    return {
        active = study.sessionActive == true,
        progress = tonumber(study.progress) or 0,
        total = tonumber(study.total) or 0,
        pausedReason = pausedReason,
        -- `rebuilding` is a transition and `not_started` lifts itself, so
        -- neither is something to offer a button for.
        resumable = study.sessionActive ~= true
            and pausedReason ~= false
            and pausedReason ~= "rebuilding"
            and pausedReason ~= "not_started",
    }
end

local function push()
    if not pageReady or not isElement(browser) then
        return
    end
    local state = {
        section = section(),
        language = ANKIGTA.Locale and ANKIGTA.Locale.language or "en",
        locale = localeTable(),
        connection = {
            state = lastStatus and lastStatus.state or "disconnected",
            category = lastStatus and lastStatus.category or false,
            sessionCategory = lastStatus and lastStatus.sessionCategory or false,
            warningCategory = lastStatus and lastStatus.warningCategory or false,
        },
        entities = entityRows(lastSnapshot),
        entityFilter = entityFilter,
        entityTotal = #(lastSnapshot and lastSnapshot.entities or {}),
        study = studyState(),
        selected = {
            mapId = selectedMapId or false,
            entityId = selectedEntityId or false,
            cardId = selectedCard and selectedCard.cardId or false,
        },
        history = {
            canUndo = lastSnapshot and lastSnapshot.history
                and lastSnapshot.history.canUndo == true or false,
            canRedo = lastSnapshot and lastSnapshot.history
                and lastSnapshot.history.canRedo == true or false,
        },
        cardPicker = {
            enabled = lastSnapshot and lastSnapshot.cardPicker
                and lastSnapshot.cardPicker.enabled == true or false,
            cards = cardRows(lastCards),
        },
        notice = notice,
    }
    local encoded = toJSON(state, true)
    if not encoded then
        outputDebugString("[ANKIGTA] panel_state_encode_failed", 2)
        return
    end
    executeBrowserJavascript(
        browser,
        "window.ANKIGTA && window.ANKIGTA.receive(" .. encoded .. ");"
    )
end

local function openPanel()
    if isPanelOpen() then
        return
    end
    local screenWidth, screenHeight = guiGetScreenSize()
    -- UI Scale reaches the panel too (ticket 28). The rendered size gives way
    -- before the screen does; the setting itself is never clamped, so a scale
    -- chosen for a bigger monitor survives being played on a smaller one.
    local scale = ANKIGTA.Layout and ANKIGTA.Layout.scale() or 1
    local width = math.min(
        screenWidth - 40, math.floor(screenWidth * 0.82 * scale)
    )
    local height = math.min(
        screenHeight - 40, math.floor(screenHeight * 0.8 * scale)
    )
    guiBrowser = guiCreateBrowser(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        true,
        true,
        false
    )
    if not isElement(guiBrowser) then
        guiBrowser = nil
        -- Nothing was taken, so there is nothing to give back, and the player
        -- is left exactly as they were.
        return
    end
    browser = guiGetBrowser(guiBrowser)
    takeCursor()
    addEventHandler("onClientBrowserCreated", browser, function()
        loadBrowserURL(source, PAGE_URL)
    end)
    if isElement(browser) then
        loadBrowserURL(browser, PAGE_URL)
    end
end

function togglePanel()
    if not authorized then
        return
    end
    -- Pick Entity has the world and the cursor; a panel over it would be a
    -- panel between the player and the thing they are aiming at.
    if type(isPickEntityActive) == "function" and isPickEntityActive() then
        return
    end
    if isPanelOpen() then
        closePanel()
        return
    end
    openPanel()
    if not isPanelOpen() then
        return
    end
    panelRequestedAt = getTickCount()
    triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
    -- The gateway publishes a status when it changes and when a player logs
    -- in. A panel opened at any other moment has been told nothing, and
    -- treating silence as disconnection showed the gate over a healthy link.
    triggerServerEvent(STATUS_REQUEST_EVENT, resourceRoot)
end

bindKey("F7", "down", togglePanel)

-- Kept from the window this replaces: reachable by command as well as by key,
-- because "always reachable" has to hold when the key is bound to something
-- else or the panel is the thing that is wrong.
addCommandHandler("ankigta-connect", function()
    triggerServerEvent(CONNECT_EVENT, resourceRoot)
end)

addCommandHandler("ankigta-connection", togglePanel)

-- --- what the page sends back -------------------------------------------------

local actions = {}

function actions.ready()
    pageReady = true
    push()
end

function actions.close()
    closePanel()
end

function actions.connect()
    triggerServerEvent(CONNECT_EVENT, resourceRoot)
end

--- The way into the settings panel, which is still CEGUI.
-- Kept as a door rather than a copy: two settings surfaces would be two places
-- to fix one wrong default.
function actions.openSettings()
    triggerEvent(OPEN_SETTINGS_EVENT, resourceRoot)
end

function actions.startStudy()
    triggerServerEvent(START_STUDY_REQUEST_EVENT, resourceRoot)
end

function actions.updateConnection(payload)
    triggerServerEvent(SETTINGS_UPDATE_EVENT, resourceRoot, payload)
end

--- The selected Map Entity, by the identity the server knows it by.
-- Not an index into a list: the list is re-sorted whenever the snapshot
-- changes, and an index would quietly start pointing at a different row.
function actions.select(payload)
    selectedMapId = type(payload.mapId) == "string" and payload.mapId or nil
    selectedEntityId = type(payload.entityId) == "string"
        and payload.entityId or nil
    push()
end

local function selectedEntry()
    for _, entry in ipairs(lastSnapshot and lastSnapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        if mapEntity.mapId == selectedMapId
            and mapEntity.entityId == selectedEntityId
        then
            return entry
        end
    end
    return nil
end

function actions.recheck()
    if selectedMapId and selectedEntityId then
        triggerServerEvent(
            RECHECK_REQUEST_EVENT, resourceRoot, selectedMapId, selectedEntityId
        )
    end
end

function actions.copyDecision(payload)
    local decision = payload.decision
    if decision ~= "original_or_renamed" and decision ~= "new_copy" then
        return
    end
    if selectedMapId and selectedEntityId then
        triggerServerEvent(
            COPY_DECISION_REQUEST_EVENT,
            resourceRoot,
            selectedMapId,
            selectedEntityId,
            decision
        )
    end
end

function actions.searchCards(payload)
    searchRequestedAt = getTickCount()
    triggerServerEvent(
        CARD_PICKER_REQUEST_EVENT,
        resourceRoot,
        tostring(payload.query or ""),
        tostring(payload.deck or ""),
        0,
        50
    )
end

function actions.selectCard(payload)
    if type(payload.cardId) ~= "string" or payload.cardId == "" then
        selectedCard = nil
    else
        selectedCard = {
            cardId = payload.cardId,
            collectionUuid = tostring(payload.collectionUuid or ""),
        }
    end
    push()
end

local function cardIdentity()
    if not selectedCard then
        return nil
    end
    return {
        collectionUuid = selectedCard.collectionUuid,
        cardId = tonumber(selectedCard.cardId),
    }
end

function actions.link()
    local entry = selectedEntry()
    local identity = cardIdentity()
    if not entry or not identity then
        return
    end
    triggerServerEvent(
        LINK_CARD_REQUEST_EVENT,
        resourceRoot,
        entry.mapEntity.mapId,
        entry.mapEntity.entityId,
        identity
    )
end

function actions.unlink()
    local entry = selectedEntry()
    if not entry or type(entry.link.cardIdentity) ~= "table" then
        return
    end
    triggerServerEvent(
        UNLINK_CARD_REQUEST_EVENT,
        resourceRoot,
        entry.mapEntity.mapId,
        entry.mapEntity.entityId,
        entry.link.cardIdentity
    )
end

function actions.replaceCard()
    local entry = selectedEntry()
    local identity = cardIdentity()
    if not entry or not identity or type(entry.link.cardIdentity) ~= "table" then
        return
    end
    triggerServerEvent(
        REPLACE_CARD_REQUEST_EVENT,
        resourceRoot,
        entry.mapEntity.mapId,
        entry.mapEntity.entityId,
        entry.link.cardIdentity,
        identity
    )
end

function actions.pickEntity(payload)
    local mode = payload.mode == "relink" and "relink" or "pick"
    if mode == "relink" then
        local entry = selectedEntry()
        if not entry then
            return
        end
        relinkSourceMapId = entry.mapEntity.mapId
        relinkSourceEntityId = entry.mapEntity.entityId
    end
    -- Pick Entity needs the world, so the panel gets out of the way first.
    closePanel()
    triggerEvent(PICK_ENTITY_START_EVENT, resourceRoot, mode)
end

function actions.relink()
    local entry = selectedEntry()
    if not entry or not relinkSourceMapId or not relinkSourceEntityId then
        return
    end
    triggerServerEvent(
        RELINK_ENTITY_REQUEST_EVENT,
        resourceRoot,
        relinkSourceMapId,
        relinkSourceEntityId,
        entry.mapEntity.mapId,
        entry.mapEntity.entityId
    )
    relinkSourceMapId = nil
    relinkSourceEntityId = nil
end

function actions.undo()
    triggerServerEvent(UNDO_REQUEST_EVENT, resourceRoot)
end

function actions.redo()
    triggerServerEvent(REDO_REQUEST_EVENT, resourceRoot)
end

function actions.filter(payload)
    entityFilter = type(payload.text) == "string" and payload.text or ""
    push()
end

function actions.dismissNotice()
    notice = false
    push()
end

addEvent(PANEL_ACTION_EVENT, true)
addEventHandler(PANEL_ACTION_EVENT, resourceRoot, function(action, rawPayload)
    if type(action) ~= "string" then
        return
    end
    local handler = actions[action]
    if not handler then
        outputDebugString("[ANKIGTA] panel_unknown_action action=" .. action, 2)
        return
    end
    local payload = nil
    if type(rawPayload) == "string" and rawPayload ~= "" then
        payload = fromJSON(rawPayload)
    end
    handler(type(payload) == "table" and payload or {})
end)

-- --- what changes underneath it -----------------------------------------------

addEvent(STATUS_EVENT, true)
addEventHandler(STATUS_EVENT, resourceRoot, function(status)
    if source ~= resourceRoot or type(status) ~= "table" then
        return
    end
    lastStatus = status
    if ANKIGTA.Diagnostics then
        -- What the session is doing, for the same report the spatial and F7
        -- state go into. A rebuild in flight is the state most worth having in
        -- a bug report, and it is the one hardest to describe in words. This
        -- moved here from the study window; the window went, the report did
        -- not.
        local study = type(status.study) == "table" and status.study or {}
        ANKIGTA.Diagnostics.record("session", {
            connection = status.state or false,
            sessionActive = study.sessionActive == true,
            pausedReason = study.pausedReason or false,
            cardCount = study.cardCount or false,
            progress = study.progress or false,
            total = study.total or false,
            filteredDeckCreated = study.filteredDeckCreated == true,
        })
    end
    push()
end)

addEvent(F7_SNAPSHOT_EVENT, true)
addEventHandler(F7_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if not authorized or type(snapshot) ~= "table" then
        return
    end
    lastSnapshot = snapshot
    local arrivedAt = getTickCount()
    push()
    local server = type(snapshot.diagnostics) == "table"
        and snapshot.diagnostics
        or {}
    record("f7", {
        -- The whole wait as the player feels it: key press to rows on screen.
        openMs = panelRequestedAt and (getTickCount() - panelRequestedAt) or false,
        renderMs = getTickCount() - arrivedAt,
        serverBuildMs = server.buildMs or false,
        entityCount = server.entityCount or false,
        linkCount = server.linkCount or false,
        mapEntities = server.mapEntities or false,
        spatialLinks = server.spatialLinks or false,
        overReferenceVolume = server.overReferenceVolume == true,
    })
    panelRequestedAt = false
end)

addEvent(CARD_PICKER_SNAPSHOT_EVENT, true)
addEventHandler(CARD_PICKER_SNAPSHOT_EVENT, resourceRoot, function(snapshot)
    if not authorized or type(snapshot) ~= "table" then
        return
    end
    lastCards = snapshot
    local arrivedAt = getTickCount()
    push()
    local cards = type(snapshot.cards) == "table" and snapshot.cards or {}
    local shown = 0
    for _ in ipairs(cards) do
        shown = shown + 1
    end
    record("search", {
        -- Only a search the player started is timed; a picker opened from a
        -- link carries no wait to report.
        pageMs = searchRequestedAt
            and (getTickCount() - searchRequestedAt)
            or false,
        renderMs = getTickCount() - arrivedAt,
        deckFilter = snapshot.deckFilter or false,
        page = snapshot.page or 0,
        pageSize = snapshot.pageSize or false,
        shown = shown,
        total = snapshot.total or false,
    })
    searchRequestedAt = false
end)

addEvent(PENDING_NOTICE_EVENT, true)
-- The server sends the key and the outcome code; the side that draws is the
-- side that translates.
addEventHandler(PENDING_NOTICE_EVENT, resourceRoot, function(noticeKey, outcome)
    if type(noticeKey) ~= "string" then
        return
    end
    notice = {key = noticeKey, detail = tostring(outcome)}
    if ANKIGTA.Locale then
        outputChatBox(
            ANKIGTA.Locale.format(noticeKey, tostring(outcome)), 255, 196, 64
        )
    end
    push()
end)

addEvent(PICK_ENTITY_FINISHED_EVENT, false)
addEventHandler(PICK_ENTITY_FINISHED_EVENT, resourceRoot, function(
    success, reason, mapId, entityId, mode
)
    if success == true then
        selectedMapId = mapId
        selectedEntityId = entityId
        selectionArrivedFromOutside = true
    elseif mode == "relink" then
        relinkSourceMapId = nil
        relinkSourceEntityId = nil
    end
    if success ~= true and reason ~= "resource_stop" and ANKIGTA.Locale then
        outputChatBox(
            ANKIGTA.Locale.format(
                mode == "relink" and "notice.relinkFailed"
                    or "notice.pickEntityFailed",
                tostring(reason)
            ),
            255, 196, 64
        )
    end
    if reason ~= "resource_stop" then
        -- Pick Entity closed the panel on its way out; bring it back where the
        -- player left off rather than making them press F7 again.
        togglePanel()
    end
end)

addEvent(AUTHORIZATION_EVENT, true)
addEventHandler(AUTHORIZATION_EVENT, resourceRoot, function(value)
    authorized = value == true
    if not authorized then
        closePanel()
    end
end)

if ANKIGTA.Locale then
    ANKIGTA.Locale.onChange(push)
end

addEventHandler("onClientResourceStart", resourceRoot, function()
    triggerServerEvent(AUTHORIZATION_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, closePanel)

ANKIGTA.Panel = {
    isOpen = isPanelOpen,
    close = closePanel,
    rows = entityRows,
    matching = panelMatching,
}

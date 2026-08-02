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
local CONNECTION_UPDATE_EVENT = "ankigta:updateConnectionSettings"
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
local SETTINGS_REQUEST_EVENT = "ankigta:requestSettings"
local SETTINGS_SNAPSHOT_EVENT = "ankigta:settingsSnapshot"
local SETTINGS_UPDATE_EVENT = "ankigta:updateSetting"
local SETTINGS_REJECTED_EVENT = "ankigta:settingRejected"
local CONNECTION_SETTINGS_REQUEST_EVENT = "ankigta:requestConnectionSettings"
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
-- Which section the player asked for, when it is theirs to ask. The connection
-- gate is not a request but a consequence, so it stays out of this.
local requestedSection = nil
-- Server-owned values as last reported, and the reason a row was refused. Kept
-- per key so the reason sits on the row that earned it rather than at the top
-- of a form.
local serverValues = {}
local settingsRejections = {}
-- What was sent to the server and not yet answered. Shown in place of the
-- stored value while it is in flight: snapping the field back to the old
-- number while the owner is still deciding reads exactly like a refusal.
local settingsPending = {}
-- When the panel and the last search were asked for, so the report can say how
-- long each took rather than only that it arrived. Measured on this side,
-- because this is the side that waits.
local panelRequestedAt = false
local searchRequestedAt = false

-- Filled in further down, declared here: the commands and the Review Mode
-- entry wire themselves to it before those definitions are reached.
local actions = {}

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
    dragFrom = nil
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
    return requestedSection or "entities"
end

-- --- settings ----------------------------------------------------------------

--- Rows are derived from the schema, never listed here.
--
-- A setting added to `shared/settings.lua` shows up in the panel by existing,
-- which is the property that stopped `pauseOnReviewerOpen` from being ticked
-- while unreachable.
--
-- What is left out is decided by rule kind rather than by name, so the rule
-- covers the next one too: a secret is never sent back to a page, and a
-- placement is dragged rather than typed. Naming the keys here would also put
-- the word for a credential into a client script, which is exactly what the
-- server-side-only guard is there to prevent.
local SETTINGS_NOT_SHOWN = {secret = true, placement = true}

local function offered(key, rule)
    return not SETTINGS_NOT_SHOWN[rule.kind or ""]
end

-- Owned by the add-on, which publishes them. The panel routes to the section
-- that already edits them instead of offering a second field for the same
-- value: two places to change one setting is one place too many.
local SETTINGS_DELEGATED = {connectionPort = true}

local function schema()
    return ANKIGTA.Settings
end

local function ownedByServer(key)
    return schema().authorityOf(key) == schema().SERVER
end

local function currentValue(key)
    if ownedByServer(key) then
        if settingsPending[key] ~= nil then
            return settingsPending[key]
        end
        local value = serverValues[key]
        if value ~= nil then
            return value
        end
        return schema().default(key)
    end
    if ANKIGTA.ClientSettings then
        return ANKIGTA.ClientSettings.get(key)
    end
    return schema().default(key)
end

local function settingsRows()
    local rows = {}
    for _, key in ipairs(schema().orderedKeys()) do
        local definition = schema().definition(key)
        local rule = definition and definition.rule or {}
        if offered(key, rule) then
            local row = {
                key = key,
                labelKey = "settings." .. key,
                kind = SETTINGS_DELEGATED[key] and "delegated"
                    or rule.kind or "unknown",
                value = currentValue(key),
                owner = ownedByServer(key) and "server" or "client",
                error = settingsRejections[key] or false,
            }
            if SETTINGS_DELEGATED[key] then
                row.value = false
            elseif rule.kind == "number" then
                row.min = rule.minimum
                row.max = rule.maximum
                row.step = rule.step
                row.decimals = rule.decimals
            elseif rule.kind == "choice" then
                row.options = rule.values
            end
            table.insert(rows, row)
        end
    end
    return rows
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
        settings = {rows = settingsRows()},
    }
    local encoded = toJSON(state, true)
    if not encoded then
        outputDebugString("[ANKIGTA] panel_state_encode_failed", 2)
        return
    end
    -- `toJSON` serialises its argument *list*, so one table comes back wrapped:
    -- `[{...}]`. Unwrapped here rather than on the page, because the page is a
    -- view and has no business knowing how Lua packed the trip. Sending the
    -- list is how every label rendered as its own key: `state.section` was
    -- undefined, so every section stayed hidden and `locale` was empty.
    executeBrowserJavascript(
        browser,
        "window.ANKIGTA && window.ANKIGTA.receive((" .. encoded .. ")[0]);"
    )
end

-- The panel is a surface like the windows it replaces, so UI Scale sizes it and
-- a placement is stored as a fraction of the screen (ticket 28). Being a page
-- rather than a CEGUI window changes only who moves it.
if ANKIGTA.Layout then
    ANKIGTA.Layout.define("panel", {
        width = 1180,
        height = 700,
        margin = 20,
        anchorX = 0.5,
        anchorY = 0.5,
    })
end

local function panelRect()
    if ANKIGTA.Layout then
        return ANKIGTA.Layout.rect("panel")
    end
    local screenWidth, screenHeight = guiGetScreenSize()
    local width = math.min(screenWidth - 40, 1180)
    local height = math.min(screenHeight - 40, 700)
    return (screenWidth - width) / 2, (screenHeight - height) / 2, width, height
end

local function openPanel()
    if isPanelOpen() then
        return
    end
    local x, y, width, height = panelRect()
    guiBrowser = guiCreateBrowser(
        x,
        y,
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

-- Where the cursor and the panel were when the drag began. The page reports
-- only that a drag started: the cursor is MTA's to report, and a mouse button
-- released outside the page never reaches it, so the loop watches the button.
local dragFrom = nil

local function stopDrag()
    dragFrom = nil
end

local function followCursor()
    if not dragFrom or not isPanelOpen() then
        return stopDrag()
    end
    if not getKeyState("mouse1") then
        return stopDrag()
    end
    local cursorX, cursorY = getCursorPosition()
    if not cursorX or not cursorY then
        return stopDrag()
    end
    local screenWidth, screenHeight = guiGetScreenSize()
    local x = dragFrom.x + (cursorX * screenWidth - dragFrom.cursorX)
    local y = dragFrom.y + (cursorY * screenHeight - dragFrom.cursorY)
    if ANKIGTA.Layout then
        -- Clamping, storing, writing and repositioning are the layout
        -- manager's, so a drag cannot put the panel somewhere the next
        -- resolution cannot show, and it survives a restart. `remember`
        -- rather than `moveTo`: the second moves, only the first writes.
        ANKIGTA.Layout.remember("panel", x, y)
        local placedX, placedY = ANKIGTA.Layout.rect("panel")
        guiSetPosition(guiBrowser, placedX, placedY, false)
        return
    end
    guiSetPosition(guiBrowser, x, y, false)
end

addEventHandler("onClientRender", root, followCursor)

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

--- The two ways out of a layout that went wrong.
--
-- Both are commands rather than only buttons, because "always reachable" has
-- to hold in the case they exist for: the panel is the wrong size, in the
-- wrong place, or off the screen entirely. A button inside it would be behind
-- the very problem it fixes.
addCommandHandler("ankigta-ui", function()
    if not authorized then
        return
    end
    if not isPanelOpen() then
        openPanel()
        if not isPanelOpen() then
            return
        end
    end
    actions.openSettings()
end)

addCommandHandler("ankigta-ui-reset", function()
    if ANKIGTA.Layout then
        ANKIGTA.Layout.reset()
    end
    if isPanelOpen() then
        local x, y = panelRect()
        guiSetPosition(guiBrowser, x, y, false)
        push()
    end
end)

-- --- what the page sends back -------------------------------------------------


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
    requestedSection = "settings"
    -- Server-owned values are the server's to report; ask, then render what
    -- comes back rather than guessing from a default.
    triggerServerEvent(SETTINGS_REQUEST_EVENT, resourceRoot)
    push()
end

--- Put UI scale and every placement back where they shipped.
function actions.resetLayout()
    if ANKIGTA.Layout then
        ANKIGTA.Layout.reset()
    end
    if isPanelOpen() then
        local x, y = panelRect()
        guiSetPosition(guiBrowser, x, y, false)
    end
    notice = {key = "ui.resetDone", detail = false}
    push()
end

--- Turn HUD dragging on and off.
-- A mode rather than a setting: it is on while the player is placing the
-- counters and off the moment they are done, so it is never written down.
function actions.editHud(payload)
    if ANKIGTA.Layout then
        ANKIGTA.Layout.setHudEditMode(payload.value == true)
    end
    push()
end

function actions.closeSettings()
    requestedSection = nil
    push()
end

--- The one path every change takes, whichever control started it.
--
-- Validated against the schema before anything is stored or sent: a value the
-- schema refuses comes back as the reason it gave, on its own row. Nothing is
-- clamped -- a mistyped 200 quietly becoming 50 leaves the player with a
-- setting they never chose and no way to notice.
function actions.setSetting(payload)
    local key = payload.key
    if type(key) ~= "string" then
        return
    end
    local definition = schema().definition(key)
    if not definition or not offered(key, definition.rule or {}) then
        return
    end
    if SETTINGS_DELEGATED[key] then
        -- Not edited here: this takes the player to the side that owns it.
        requestedSection = "connection"
        triggerServerEvent(CONNECTION_SETTINGS_REQUEST_EVENT, resourceRoot)
        push()
        return
    end
    local value = schema().normalize(key, payload.value)
    local valid, reason = schema().validate(key, value)
    if not valid then
        settingsRejections[key] = reason
        push()
        return
    end

    if ownedByServer(key) then
        -- Not redrawn here on purpose: snapping the field back while the
        -- server is still deciding looks exactly like a rejection. The
        -- snapshot that follows is what shows the new value.
        settingsRejections[key] = nil
        settingsPending[key] = value
        triggerServerEvent(
            SETTINGS_UPDATE_EVENT, resourceRoot, key, value, payload.mapId
        )
        push()
        return
    end

    local stored, storeReason = ANKIGTA.ClientSettings.set(key, value)
    if not stored then
        settingsRejections[key] = storeReason
        push()
        return
    end
    settingsRejections[key] = nil
    push()
end

function actions.dragStart()
    if not isPanelOpen() or not isCursorShowing() then
        return
    end
    local cursorX, cursorY = getCursorPosition()
    if not cursorX or not cursorY then
        return
    end
    local screenWidth, screenHeight = guiGetScreenSize()
    local x, y = guiGetPosition(guiBrowser, false)
    dragFrom = {
        cursorX = cursorX * screenWidth,
        cursorY = cursorY * screenHeight,
        x = x,
        y = y,
    }
end

function actions.dragEnd()
    stopDrag()
end

function actions.startStudy()
    triggerServerEvent(START_STUDY_REQUEST_EVENT, resourceRoot)
end

function actions.updateConnection(payload)
    triggerServerEvent(CONNECTION_UPDATE_EVENT, resourceRoot, payload)
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

-- Review Mode has its own way in, and it asks by name rather than by knowing
-- where the panel keeps its sections.
addEvent(OPEN_SETTINGS_EVENT, false)
addEventHandler(OPEN_SETTINGS_EVENT, resourceRoot, function()
    if not authorized then
        return
    end
    if not isPanelOpen() then
        openPanel()
        if not isPanelOpen() then
            return
        end
    end
    actions.openSettings()
end)

addEvent(SETTINGS_SNAPSHOT_EVENT, true)
addEventHandler(SETTINGS_SNAPSHOT_EVENT, resourceRoot, function(values)
    if source ~= resourceRoot or type(values) ~= "table" then
        return
    end
    serverValues = type(values.values) == "table" and values.values or values
    -- The owner has spoken, so nothing is in flight any more and what it says
    -- is what the row shows -- including when it says something else.
    settingsPending = {}
    push()
end)

addEvent(SETTINGS_REJECTED_EVENT, true)
addEventHandler(SETTINGS_REJECTED_EVENT, resourceRoot, function(key, reason)
    if source ~= resourceRoot or type(key) ~= "string" then
        return
    end
    -- The server refused after the fact, so the reason lands on the row that
    -- earned it rather than in the chat, where it would scroll away.
    settingsRejections[key] = reason or "settings.error.not_saved"
    settingsPending[key] = nil
    push()
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

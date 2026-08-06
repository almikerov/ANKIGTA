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
local TELEPORT_REQUEST_EVENT = "ankigta:teleportToEntity"
local TELEPORT_ARRIVED_EVENT = "ankigta:teleportArrived"
local ENTITY_METADATA_REQUEST_EVENT = "ankigta:updateEntityMetadata"
local ADOPT_ENTITY_REQUEST_EVENT = "ankigta:adoptEntity"
local FORGET_ENTITY_REQUEST_EVENT = "ankigta:forgetMapEntity"
local NOTE_READ_REQUEST_EVENT = "ankigta:requestNote"
local NOTE_UPDATE_REQUEST_EVENT = "ankigta:updateNote"
local NOTE_SNAPSHOT_EVENT = "ankigta:noteSnapshot"
local UNDO_REQUEST_EVENT = "ankigta:undo"
local REDO_REQUEST_EVENT = "ankigta:redo"
local PICK_ENTITY_START_EVENT = "ankigta:pickEntityStart"
local PICK_ENTITY_FINISHED_EVENT = "ankigta:pickEntityFinished"
local PENDING_NOTICE_EVENT = "ankigta:pendingMapSaveNotice"
local SETTINGS_REQUEST_EVENT = "ankigta:requestSettings"
local SETTINGS_SNAPSHOT_EVENT = "ankigta:settingsSnapshot"
local SETTINGS_UPDATE_EVENT = "ankigta:updateSetting"
local SETTINGS_REJECTED_EVENT = "ankigta:settingRejected"
local CLEAR_ENTITY_OVERRIDES_EVENT = "ankigta:clearEntityOverrides"
local ENTITY_OVERRIDE_COUNT_EVENT = "ankigta:entityOverrideCount"
local CONNECTION_SETTINGS_REQUEST_EVENT = "ankigta:requestConnectionSettings"
local CONNECTION_SETTINGS_SNAPSHOT_EVENT = "ankigta:connectionSettingsSnapshot"
local PAGE_URL = "http://mta/local/client/panel/index.html"
-- The notices a completed search answers, and so retires.
local CARD_PICKER_NOTICES = {
    ["notice.cardPickerRejected"] = true,
    ["notice.cardPickerUnavailable"] = true,
}

local authorized = false
local guiBrowser = nil
local browser = nil
-- Where the cursor and the panel were when the drag began, declared up here
-- because `closePanel` clears it. Declared below its first use, `dragFrom = nil`
-- in `closePanel` compiled as a *global* assignment and left the real one set:
-- the panel then jumped by the old delta the next time it opened with the
-- button held, which is the panel drifting on its own.
local dragFrom = nil
local pageReady = false
local cursorOwned = false
local focusedCamera = nil
-- What camera focus took hold of while the camera was away, and how that thing
-- stood before it did. Letting go has to put the state back rather than assume
-- what it was.
local focusedHold = nil

-- The last thing each source told us. The page is redrawn from these, so a new
-- status or a new scale repaints without asking anyone again.
local lastStatus = nil
-- Sanitized connection fields as last reported by the server. The token value
-- never crosses this boundary; the page only needs to know whether its masked
-- field represents an existing token.
local connectionSettings = {}
local connectionSettingsVersion = 0
local lastSnapshot = nil
local lastCards = nil
-- What the player picked, kept here rather than on the page: the page is a
-- view, and a selection the two sides disagree about is how a confirmation
-- ends up acting on the wrong row.
local selectedMapId = nil
local selectedEntityId = nil
local selectedCard = nil
-- The note behind the selected card, as the companion last reported it, and
-- the reason it could not be read. Held here rather than on the page for the
-- same reason the selection is: the page is a view.
local selectedNote = false
local noteError = false
local notice = false
-- Set when Pick Entity was started to choose a relink target.
local relinkSourceMapId = nil
local relinkSourceEntityId = nil
-- An object the stock Map Editor placed that ANKIGTA has not adopted yet. It
-- has no `(mapId, entityId)` to be selected by, so it is held as the element
-- itself until a card gives it an identity.
local adoptionTarget = nil
-- Set where a selection arrives from the world, read and cleared by the next
-- render. One-shot on purpose: a filter typed *after* the pick is the player's
-- latest word and must survive.
local selectionArrivedFromOutside = false
-- What the player typed to narrow the list. Kept here so a rebuild the player
-- did not ask for does not throw away their filter.
local entityFilter = ""
-- Which section the player asked for, when it is theirs to ask. The connection
-- gate is not a request but a consequence, so it stays out of this.
local requestedSection = nil
-- Server-owned values as last reported, and the reason a row was refused. Kept
-- per key so the reason sits on the row that earned it rather than at the top
-- of a form.
local serverValues = {}
local settingsRejections = {}
--- The sweep the player has asked about and not yet answered: which setting,
--- and how many links the server says it would put back on the global.
local pendingOverrideClear = false
--- Deleted objects the player has already answered about, this session.
local answeredDeletions = {}

--- Which deleted objects the player has not answered about yet.
--
-- The answer is remembered for as long as the session lasts. "Keep" is a real
-- answer -- the link stays and the row does not come back -- and asking again
-- on the next snapshot would make it look like it had not been heard.
local function unansweredDeletions(snapshot)
    local pending = {}
    for _, entry in ipairs(snapshot and snapshot.deletedFromMap or {}) do
        local key = tostring(entry.mapId) .. "\0" .. tostring(entry.entityId)
        if not answeredDeletions[key] then
            pending[#pending + 1] = entry
        end
    end
    return pending
end

local function firstDeletion()
    return unansweredDeletions(lastSnapshot)[1]
end

-- What was sent to the server and not yet answered. Shown in place of the
-- stored value while it is in flight: snapping the field back to the old
-- number while the owner is still deciding reads exactly like a refusal.
local settingsPending = {}
-- When the panel and the last search were asked for, so the report can say how
-- long each took rather than only that it arrived. Measured on this side,
-- because this is the side that waits.
local panelRequestedAt = false
local searchRequestedAt = false
--- Whether this opening of the panel has already asked for cards. The picker
--- fills itself once per open; a snapshot arrives whenever anything at all
--- changes, and searching on each of them would restart the list under the
--- player every few seconds.
local searchIssued = false
--- Whether the card editor is slid out. Held here as well as on the page,
--- because the panel's own width follows it.
local editorOpen = false
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

--- Stop asking for the cursor.
--
-- `showCursor(false)`, never "whatever it was before I looked". MTA counts
-- cursor requests across resources -- `static int m_iShowingCursor` -- and
-- shows it while any resource is asking. Reading `isCursorShowing()` on the way
-- in therefore reads *somebody else's* answer, and handing it back on the way
-- out means never letting go: open another resource's window first, then this
-- one, then close both, and the cursor stays on screen with nothing left to
-- dismiss it.
--
-- Called from every path that ends the panel, including the one where the
-- browser could not be created: a panel that fails to open must not leave the
-- player holding a cursor they cannot dismiss.
local function releaseCursor()
    if not cursorOwned then
        return
    end
    showCursor(false)
    cursorOwned = false
end

local function takeCursor()
    if cursorOwned then
        return
    end
    cursorOwned = true
    showCursor(true)
end

--- Does this still carry the player, so that pointing the camera back at it
--- points the camera back at them?
--
-- `getCameraTarget()` answers with the *vehicle* while the player is riding
-- one, because that is what the camera follows. Handing that element back
-- later is right only while they are still in it: get out in between, and the
-- camera stays on an empty car, watching it from wherever it was parked. The
-- player is then left with no way to see themselves at all -- which is the
-- camera not coming back rather than coming back wrong.
local function stillCarriesPlayer(element)
    return element == localPlayer
        or element == getPedOccupiedVehicle(localPlayer)
end

--- True only while `actions.teleport` is closing the panel.
--
-- The player is about to be somewhere else, so the camera the panel borrowed
-- is dropped rather than restored.
local teleporting = false

local function restoreFocusedCamera()
    if not focusedCamera then
        return
    end
    if teleporting then
        focusedCamera = nil
        return
    end
    setCameraInterior(focusedCamera.interior or 0)
    local target = focusedCamera.target
    if isElement(target) and stillCarriesPlayer(target) then
        setCameraTarget(target)
    elseif not target
        and type(focusedCamera.matrix) == "table"
        and #focusedCamera.matrix >= 6
    then
        -- No target when it was taken means somebody had the camera in a fixed
        -- position; that is theirs to have back.
        setCameraMatrix(unpack(focusedCamera.matrix))
    else
        setCameraTarget(localPlayer)
    end
    focusedCamera = nil
end

--- What carries the player's weight right now.
--
-- A ped sitting in a vehicle is moved by the vehicle, so freezing the ped
-- alone would leave the car -- and the player riding in it -- still falling.
local function physicalSubject()
    local vehicle = getPedOccupiedVehicle(localPlayer)
    if isElement(vehicle) then
        return vehicle
    end
    return localPlayer
end

--- Keep the player where they are while the camera is somewhere else.
--
-- GTA streams the world around the *camera*, not around the player. Send the
-- camera to a Map Entity far enough away and the collision under the player's
-- own feet unloads while they are still under physics: they drop through the
-- map at the very spot they were standing on.
--
-- The prior resource never met this, and not because it showed the model some
-- other way -- it moved the camera with the same `setCameraMatrix`. It never
-- owned the camera alone. It opened over a running stock Map Editor, whose
-- `attachplayer.lua` puts the player at the camera every frame with collisions
-- off and alpha 0, so there was nothing left to fall. F7 stands on its own
-- now, and its contract is that focusing a row does not move the Study Player,
-- so it pins them instead of carrying them: `CClientPed::SetFrozen` caches the
-- ped matrix and holds it, which is "stay exactly here" without a teleport.
--
-- Idempotent: focusing a second row must not overwrite the state the first
-- focus found and still has to give back.
local function holdPlayerStill()
    if focusedHold then
        return
    end
    local subject = physicalSubject()
    focusedHold = {
        element = subject,
        frozen = isElementFrozen(subject) == true,
    }
    setElementFrozen(subject, true)
end

--- Give the player back to physics, exactly as they were.
--
-- `setElementFrozen(subject, false)` would be wrong. Unlike the cursor above,
-- frozen is per-element state with one owner, so reading it on the way in
-- reads our own answer rather than somebody else's -- and a player who was
-- already frozen when F7 opened is still owed that on the way out.
local function releasePlayerHold()
    if not focusedHold then
        return
    end
    local held = focusedHold
    focusedHold = nil
    if isElement(held.element) then
        setElementFrozen(held.element, held.frozen)
    end
end

local function closePanel()
    dragFrom = nil
    releasePlayerHold()
    restoreFocusedCamera()
    if isElement(guiBrowser) then
        destroyElement(guiBrowser)
    end
    guiBrowser = nil
    browser = nil
    pageReady = false
    searchIssued = false
    editorOpen = false
    -- The panel opens where it always opens: on the list. What outlives the
    -- window is the *answer* -- the settings the player changed, which are
    -- stored and untouched by this -- and not the screen they changed it on. A
    -- window that reopens on Settings is a window whose state the player has to
    -- notice and undo before doing the thing they opened it for.
    requestedSection = nil
    -- The selection is deliberately not cleared. `Draw radius` stops drawing
    -- with the window, but the row the player was working on is still the row
    -- they were working on, so opening F7 again puts the zone straight back
    -- rather than making them find the row a second time.
    --
    -- Told rather than left to the next poll: the marks look at the world four
    -- times a second, and a sphere that hangs about for a quarter of a second
    -- after the window has gone reads as the window not having closed properly.
    if ANKIGTA.WorldMarks then
        ANKIGTA.WorldMarks.refresh()
    end
    releaseCursor()
end

--- Which section the panel should be showing.
-- Not a stored preference: it follows the state of the world, because the
-- reason to open the panel with no connection is always the connection.
--
-- A screen of its own is right for *these* settings: they are the panel's, and
-- there is nothing behind the window to look at while they are changed. The
-- pane that is beside the list rather than over it is the one that edits the
-- selected Map Entity, which is exactly the thing that has to stay in sight.
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

--- May the page change this setting at all?
local function editableFromPanel(key, rule)
    return not SETTINGS_NOT_SHOWN[rule.kind or ""]
end

-- Owned by the add-on, which publishes them. The panel routes to the section
-- that already edits them instead of offering a second field for the same
-- value: two places to change one setting is one place too many.
local SETTINGS_DELEGATED = {connectionPort = true}

local function schema()
    return ANKIGTA.Settings
end

--- Does the *Settings* list carry a row for it?
--
-- Not the same question as `editableFromPanel`. `drawRadius` is edited from the
-- panel -- it is a toggle on the entity pane, beside the `Show corona` it is
-- half a decision with -- and is not a row here. Which surface a setting
-- belongs to is the schema's answer, so a second one moving is a line there
-- rather than a list of exceptions kept in this file.
local function shownInSettings(key, rule)
    return editableFromPanel(key, rule) and schema().shownWith(key) == "settings"
end

local function ownedByServer(key)
    return schema().authorityOf(key) == schema().SERVER
end

local function storedValue(key)
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

--- The value as the player should read it.
--
-- The one boundary between a number that has been stored and shipped about and
-- a number somebody looks at, so the rounding happens here rather than at each
-- of the places that show one: the Settings row, the global an entity follows,
-- and the entity pane all come through this.
--
-- What it is for: a server-owned number reaches this side as a 32-bit float, so
-- a stored `0.6` arrives as `0.60000001999999997` and read as `0.60000002` --
-- a wrong rendering of the right value. Rounded to the precision the setting's
-- own rule declares, it also compares equal to what the player chose, so the
-- snapshot that follows an edit does not read as somebody else editing it back.
local function currentValue(key)
    return schema().rounded(key, storedValue(key))
end

local function settingsRows()
    local rows = {}
    for _, key in ipairs(schema().orderedKeys()) do
        local definition = schema().definition(key)
        local rule = definition and definition.rule or {}
        if shownInSettings(key, rule) then
            -- A sentence under the control, where one setting needs saying
            -- more than its name says. A setting gains one by gaining the
            -- string, so there is no list here of which rows have a note --
            -- the string table is the list, and a note with no row to sit
            -- under is a key nothing looks up.
            local noteKey = "settings." .. key .. ".note"
            local strings = ANKIGTA.Locale and ANKIGTA.Locale.strings or {}
            local row = {
                key = key,
                labelKey = "settings." .. key,
                noteKey = strings[noteKey] and noteKey or false,
                kind = SETTINGS_DELEGATED[key] and "delegated"
                    or rule.kind or "unknown",
                value = currentValue(key),
                owner = ownedByServer(key) and "server" or "client",
                error = settingsRejections[key] or false,
                -- A setting a link can override gets the control that clears
                -- those overrides everywhere, and gets it by having an
                -- override rather than by being named in a list here. The next
                -- overridable setting appears with this control already beside
                -- it.
                clearOverrides = schema().entityOverrideColumn(key) ~= false,
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
            elseif rule.kind == "key" then
                -- Not a list to choose from -- the key is pressed now -- but
                -- the two lists the press is judged against, which are the two
                -- refusals it can earn. A name absent from `bindableKeys` is a
                -- key MTA cannot name; a name present there and absent from the
                -- free ones is a key ANKIGTA already answers to.
                --
                -- Sent rather than kept on the page, and read there by the
                -- entity pane's control as well as by this row's: which keys
                -- ANKIGTA can bind is the schema's answer, and a page holding
                -- its own copy is a second answer that can disagree with the
                -- rule that validates the value.
                row.options = schema().offeredKeys()
                row.bindableKeys = schema().bindableKeys
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
-- A running MTA client can receive this changed cache=false script one restart
-- before a newly-added shared manifest script.  Keep F7 alive during that
-- incremental reload; entity_types.lua installs the same canonical values on
-- a clean resource start.
ANKIGTA.EntityTypes = ANKIGTA.EntityTypes or {
    order = {"object", "vehicle", "ped", "marker"},
    supported = {object = true, vehicle = true, ped = true, marker = true},
}
local PANEL_ENTITY_TYPES = ANKIGTA.EntityTypes.order
local PANEL_ENTITY_TYPE = ANKIGTA.EntityTypes.supported

--- Is this element EDF's own drawing of another element rather than the
--- element itself?
--
-- Read off the element, because that is all `edfIsRepresentation` does
-- (`edf/edf.lua`: `return getElementData(elem, "edf:rep")`) and because the
-- export exists server-side only -- `edf/meta.xml` lists a much shorter client
-- half. Calling it here failed every time and wrote a line to
-- `clientscript.log` on every list refresh; the `pcall` around it turned the
-- failure into "nothing is ever a representation".
local function isEditorRepresentation(element)
    return getElementData(element, "edf:rep") == true
end

--- Resolve the real copy of a Map Entity when editor and play-test copies
-- temporarily share the same MTA ID. Prefer the streamed copy because that is
-- the one the player can actually see and focus right now.
--- Every identity an element answers to, in the order they are trusted.
--
-- Three of them, because an element answers to different ones depending on who
-- put it there: the persistent one ANKIGTA wrote, the one the stock Map Editor
-- keeps while the map is open in it, and the one the `.map` file gave it.
--
-- Read here and nowhere else. Both callers below need the same three, and two
-- copies of "what identifies an element" is two places for a fourth to be
-- added to only one of.
local function elementIdentities(element)
    return getElementData(element, "ankigtaEntityId"),
        getElementData(element, "me:ID"),
        getElementID(element)
end

--- Does this element stand for the Map Entity named by `mapId`/`entityId`?
local function elementStandsFor(element, mapId, entityId)
    local persistentId, editorId, elementId = elementIdentities(element)
    local elementMapId = getElementData(element, "ankigtaMapId")
    return (persistentId == entityId or editorId == entityId
            or elementId == entityId)
        and (not elementMapId or elementMapId == mapId)
        and not isEditorRepresentation(element)
end

local function runtimeElement(mapId, entityId, streamedOnly)
    local unstreamed = false
    for _, kind in ipairs(PANEL_ENTITY_TYPES) do
        for _, element in ipairs(getElementsByType(kind)) do
            if elementStandsFor(element, mapId, entityId) then
                if isElementStreamedIn(element) then
                    return element
                end
                if not streamedOnly then
                    unstreamed = element
                end
            end
        end
    end
    return unstreamed
end

--- A Map Entity named by the pair the server knows it by.
--
-- Never by entity id alone. The stock Map Editor names what it places `object
-- (1)`, `object (2)` and so on, counting from one per map -- so two loaded maps
-- collide on their first object, and an index keyed on the id alone quietly
-- files one map's element under the other map's row.
--
-- Exported, because `runtimeElementsFor` answers in it and the world marks
-- read that answer: two copies of one separator is a corona that silently
-- stops resolving the day one of them changes.
local function panelEntityKey(mapId, entityId)
    return tostring(mapId) .. "/" .. tostring(entityId)
end

--- The streamed Runtime Instance of each of several Map Entity, at once.
--
-- One walk of the world for the whole set, keyed by `panelEntityKey`. The
-- world holds thousands of elements and `runtimeElement` walks all of them per
-- identity; what draws marks asks about every entity that shows one, and doing
-- that a walk at a time is the world once per mark.
--
-- Streamed only: a mark is drawn on a thing that is here, and an entity whose
-- Runtime Instance is not streamed has nothing to draw one on.
local function runtimeElementsFor(keys)
    local wanted, found = {}, {}
    local any = false
    for _, key in ipairs(keys or {}) do
        -- A list per id, because the same id in two maps is two Map Entity and
        -- both of them may be asked for at once.
        local sought = wanted[key.entityId]
        if sought == nil then
            sought = {}
            wanted[key.entityId] = sought
        end
        sought[#sought + 1] = key.mapId
        any = true
    end
    if not any then
        return found
    end

    local function claim(element, entityId)
        if not entityId then
            return
        end
        for _, mapId in ipairs(wanted[entityId] or {}) do
            local key = panelEntityKey(mapId, entityId)
            if found[key] == nil
                and elementStandsFor(element, mapId, entityId)
            then
                found[key] = element
            end
        end
    end

    for _, kind in ipairs(PANEL_ENTITY_TYPES) do
        for _, element in ipairs(getElementsByType(kind)) do
            if isElementStreamedIn(element) then
                -- Looked up by each identity the element answers to rather
                -- than compared against every wanted key in turn: the world
                -- holds thousands of elements, and a scan per key inside a
                -- scan of the world is the product of the two. Each is passed
                -- separately because an element carries only some of them, and
                -- a list with a hole in it ends at the hole.
                local persistentId, editorId, elementId =
                    elementIdentities(element)
                claim(element, persistentId)
                claim(element, editorId)
                claim(element, elementId)
            end
        end
    end
    return found
end

--- The name the user typed for this entity, or "" if nobody has named it.
--
-- Theirs and only theirs: what a row falls back to when nobody has named it is
-- `editorName` below, and the two must not be confused. The name *box* is
-- filled from this one -- pre-filling it with the editor's name is how
-- `ped (1)` gets stored as somebody's cosmetic name the first time they touch
-- the field.
local function givenName(entry)
    local typed = entry.metadata and entry.metadata.name
    if type(typed) ~= "string" or typed == "" then
        typed = entry.link and entry.link.metadata and entry.link.metadata.name
    end
    if type(typed) == "string" and typed ~= "" then
        return typed
    end
    return ""
end

--- What the Map Editor calls this thing, which is what the row is called.
--
-- Already stored, and stored as the identity itself: the editor's `assignID`
-- writes `ped (1)` into the element's id, adoption reads it, and it is the
-- `entity_id` half of the Map Entity's primary key. So the row is headed by
-- what the player reads in the editor's own list, with nothing derived and
-- nothing looked up.
--
-- Deriving one from the model instead is what this replaced, and it was wrong
-- twice over: two peds of one skin both read `Ped skin 0` while the editor
-- beside them said `ped (1)` and `ped (2)`, and a marker -- which has no model
-- at all -- fell through to `Unnamed Map Entity`.
--
-- The model name is not lost where MTA has one: the editor has already put it
-- inside the id, which is why `object (sw_hedstones) (1)` and
-- `vehicle (Clover) (1)` read the way they do. Where MTA has none, nothing
-- pretends otherwise.
--
-- An entity no editor named -- a freeroam vehicle, taken in by where it stands
-- -- reads as the positional name it really has. That is honest; inventing a
-- better-looking one would name two of them the same.
local function editorName(entry)
    local entityId = entry.mapEntity and entry.mapEntity.entityId
    if type(entityId) == "string" and entityId ~= "" then
        return entityId
    end
    -- Nothing at all to show. A stored Map Entity always has an `entity_id`,
    -- so this is the guard rather than a case the player meets.
    return ANKIGTA.Locale.text("f7.entity.unnamed")
end

--- Which MTA call, if any, can put a name to this type's model.
--
-- One table rather than a type test at each call, because the two answers are
-- one fact -- what `CModelNames` holds -- and stating it twice is how the two
-- come to disagree. A type absent from here has no name to be had: MTA has none
-- for a ped skin at all, there is no ped table in `CModelNames`, and no id->name
-- table is shipped to invent one.
--
-- Named at call time rather than captured: an incremental client reload can
-- hand this script to a client before the engine functions are in scope.
local MODEL_NAME_SOURCE = {
    -- 400-611, which is the vehicle range and a little past what `CModelNames`
    -- knows.
    vehicle = function(model)
        return getVehicleNameFromModel and getVehicleNameFromModel(model)
    end,
    -- `CModelNames` holds the object table, and answers `false` *and* logs
    -- `Expected valid model ID` for anything outside it -- which is what filled
    -- the client log with a warning per ped per snapshot when every type was
    -- asked.
    object = function(model)
        return engineGetModelNameFromID and engineGetModelNameFromID(model)
    end,
}

--- What MTA can tell us about the model, for the filter and never for the row.
--
-- Not a name for the thing -- `editorName` is that -- but a fact about it, and
-- one a player searches by: the skin number finds the ped wearing it, and
-- "Infernus" finds the car. Empty where there is nothing to be had.
--
-- Client-side because that is where the model tables are: the server has no
-- `engineGetModelNameFromID`.
local function modelSearchTerms(entry)
    local mapEntity = entry.mapEntity
    -- A marker has no model at all: `getElementModel` answers `false` on the
    -- real server, and the NOT NULL column stores that as 0. Asked by type
    -- rather than by the number, because **skin 0 is a real ped** -- it is the
    -- skin in the owner's own store -- and a guard on `model > 0` would have
    -- made exactly that ped unfindable.
    if mapEntity.type == "marker" then
        return {}
    end
    local model = tonumber(mapEntity.model)
    if not model then
        return {}
    end
    local terms = {tostring(model)}
    local source = MODEL_NAME_SOURCE[mapEntity.type]
    -- Model 0 is not in `CModelNames` under any type, so asking about one is
    -- the warning again for no answer.
    if source and model > 0 then
        local name = source(model)
        if type(name) == "string" and name ~= "" then
            terms[#terms + 1] = name
        end
    end
    return terms
end

--- What the row is headed by: the name somebody gave it, or the editor's.
local function readableName(entry)
    local typed = givenName(entry)
    if typed ~= "" then
        return typed
    end
    return editorName(entry)
end

--- Does this entry answer to what was typed?
--
-- Over the *stored* record, never over what happens to be streamed in: an
-- entity whose Runtime Instance is gone is found by the same words that find
-- one standing in front of the player (story 51). Plain substring, not a
-- pattern, so a name with brackets in it is searchable by its brackets.
--
-- The entity id is in here as well as the given name. Naming a thing replaces
-- what the row said, so a filter that only knew the new name would make the
-- old one -- the one the Map Editor still shows -- unsearchable the moment it
-- stopped being displayed.
--
-- And the model with them, though no row is headed by one any more. The skin a
-- ped wears and the name of a car are facts about the thing that a player
-- searches by, and dropping them from the row was not a reason to stop finding
-- it by them.
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
    for _, term in ipairs(modelSearchTerms(entry)) do
        haystacks[#haystacks + 1] = term
    end
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

--- Every Map Entity in the last snapshot, and how it asks to be marked.
--
-- Off the snapshot rather than off `entityRows`, which applies the filter the
-- player typed: a row hidden from a list is still a thing standing in the
-- world, and hiding it must not put its corona out.
--
-- Every override is passed through as it arrived, absent and all. What an
-- absent field means is settled at the drawing, which is the one place that
-- knows what the entity would be following instead -- and flattening it here
-- would need a word for "nothing of its own" that no value can also be, which
-- `Show corona` broke the moment it gained one.
local function panelMarkable()
    local marks = {}
    for _, entry in ipairs(lastSnapshot and lastSnapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        local metadata = type(entry.metadata) == "table" and entry.metadata or {}
        marks[#marks + 1] = {
            mapId = mapEntity.mapId,
            entityId = mapEntity.entityId,
            radius = metadata.radius,
            showCorona = metadata.showCorona,
            coronaColor = metadata.coronaColor,
            coronaOpacity = metadata.coronaOpacity,
        }
    end
    return marks
end

--- The one link state that means a card will really open here.
--
-- Every other state -- unlinked, card missing, entity missing, waiting on a map
-- save, a collision -- is a Map Entity ANKIGTA knows about and cannot study
-- through. On the map that is one answer rather than five: the question a map
-- answers is "which of these is ready", not "why is this one not".
local LINK_STATE_ACTIVE = "Active Spatial Link"

--- Every Map Entity the last snapshot holds, for the map.
--
-- The authored position, not a Runtime Instance's. The map is the one surface
-- that shows a Map Entity the player cannot see, so a blip is wanted for an
-- entity three districts away -- and that entity has no element here to read a
-- position off. The mark that follows a thing as it moves is the corona, which
-- is attached to it.
--
-- Off the snapshot rather than off `entityRows`, for the same reason
-- `panelMarkable` is: a row hidden by the filter the player typed is still a
-- thing standing in the world, and hiding it from a list must not take it off
-- the map.
local function panelMapEntities()
    local entities = {}
    for _, entry in ipairs(lastSnapshot and lastSnapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        local authored = type(mapEntity.authored) == "table"
            and mapEntity.authored or {}
        local position = type(authored.position) == "table"
            and authored.position or {}
        local world = type(authored.world) == "table" and authored.world or {}
        local x = tonumber(position.x)
        local y = tonumber(position.y)
        local z = tonumber(position.z)
        -- A Map Entity with no position is one nothing can be put on a map at,
        -- which is a stored record too damaged to draw rather than a state.
        if x and y and z then
            entities[#entities + 1] = {
                mapId = mapEntity.mapId,
                entityId = mapEntity.entityId,
                x = x,
                y = y,
                z = z,
                dimension = tonumber(world.dimension) or 0,
                connected = entry.link
                    and entry.link.state == LINK_STATE_ACTIVE or false,
            }
        end
    end
    return entities
end

--- Which Map Entity the player has selected, if any.
--
-- The panel owns the selection -- the page is a view -- so whatever draws on
-- the world asks here rather than being told, and there is no second copy to
-- disagree with this one. It outlives the panel being closed, which is what
-- lets `Draw radius` keep drawing the zone the player was just setting up.
local function panelSelection()
    return selectedMapId or false, selectedEntityId or false
end

--- Where the Map Entity stands, in the language people use for the world.
-- The persistent identity remains on the row for actions, but is not its
-- description.  Coordinates stay useful everywhere; the GTA zone follows
-- when the client can name one for that position.
local function entityDescription(mapEntity)
    local position = mapEntity and mapEntity.authored
        and mapEntity.authored.position or {}
    local x, y, z = tonumber(position.x), tonumber(position.y), tonumber(position.z)
    if not x or not y or not z then
        return ""
    end
    local coordinates = string.format("%.2f, %.2f, %.2f", x, y, z)
    local location = getZoneName and getZoneName(x, y, z) or false
    if type(location) == "string" and location ~= "" then
        return coordinates .. " · " .. location
    end
    return coordinates
end

local function entityRows(snapshot)
    dropFilterHiding(snapshot)
    selectionArrivedFromOutside = false
    -- What a row with none of its own follows. Read once per render rather
    -- than per row: they are one global each, and asking the store fifty times
    -- for one would not make it any more current.
    local globalRadius = tonumber(currentValue("activationRadius")) or 3
    local globalShowCorona = currentValue("showCorona") == true
    local globalCoronaColor = currentValue("coronaColor")
    local globalCoronaOpacity = tonumber(currentValue("coronaOpacity"))
    local globalActivationType = currentValue("activationType")
    local globalActivationKey = currentValue("activationKey")
    local globalLabelField = currentValue("textLabelField")
    local globalLabelColor = currentValue("textLabelColor")
    local globalLabelSize = tonumber(currentValue("textLabelSize"))
    local rows = {}
    for _, entry in ipairs(snapshot and snapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        local given = givenName(entry)
        local original = editorName(entry)
        local metadata = type(entry.metadata) == "table" and entry.metadata or {}
        -- Through the same door the globals above came through. An override
        -- crossed the same wire, and both are read at the precision the one
        -- rule behind them declares -- which for a radius is none, because it
        -- steps in halves and a half is exact in a 32-bit float. Asked anyway,
        -- so "how is this number read" has one answer for both sides of the
        -- override rather than one per key.
        local ownRadius = schema().rounded(
            "activationRadius", tonumber(metadata.radius)
        )
        -- `nil` where the entity says nothing of its own, which is what the
        -- store means by a NULL override column.
        local ownShowCorona = metadata.showCorona
        local ownCoronaColor = type(metadata.coronaColor) == "string"
            and metadata.coronaColor ~= ""
            and metadata.coronaColor
            or nil
        -- And this is the one the tail was found on: an entity told `0.55` of
        -- its own reads `0.55000001` without it, exactly as the global did.
        local ownCoronaOpacity = schema().rounded(
            "coronaOpacity", tonumber(metadata.coronaOpacity)
        )
        local ownActivationType = type(metadata.activationType) == "string"
            and metadata.activationType ~= ""
            and metadata.activationType
            or nil
        local ownActivationKey = type(metadata.activationKey) == "string"
            and metadata.activationKey ~= ""
            and metadata.activationKey
            or nil
        -- The Text Label's three, read exactly the way the corona's are: a
        -- NULL override column arrives as an absent field, and the size goes
        -- through the same rounding the opacity does -- it is a two-decimal
        -- number that crossed a wire, so `1.15` reads `1.14999998` without it.
        local ownLabelField = type(metadata.textLabelField) == "string"
            and metadata.textLabelField ~= ""
            and metadata.textLabelField
            or nil
        local ownLabelColor = type(metadata.textLabelColor) == "string"
            and metadata.textLabelColor ~= ""
            and metadata.textLabelColor
            or nil
        local ownLabelSize = schema().rounded(
            "textLabelSize", tonumber(metadata.textLabelSize)
        )
        -- Spelt out rather than as an `and`/`or` chain: the entity's own answer
        -- may be `false`, and `a and b or c` hands `false` to `c` -- which
        -- would make "no corona on this one" read as "follows the global".
        local showCorona = globalShowCorona
        if ownShowCorona ~= nil then
            showCorona = ownShowCorona == true
        end
        table.insert(rows, {
            mapId = mapEntity.mapId,
            entityId = mapEntity.entityId,
            type = mapEntity.type,
            name = readableName(entry),
            -- What the player typed, kept apart from what the row is headed
            -- by: the name field edits this one, and filling it with the
            -- editor's name is how `ped (1)` becomes somebody's cosmetic name.
            givenName = given,
            -- A cosmetic name replaces the editor's, which is the point -- but
            -- the editor's is the only thing tying this row to what the Map
            -- Editor shows, so a renamed row keeps saying it.
            originalName = given ~= "" and original ~= given and original
                or false,
            description = entityDescription(mapEntity),
            model = tonumber(entry.mapEntity.model) or 0,
            linkState = entry.link.state,
            guidanceKey = entry.link.guidanceKey or false,
            -- The value actually in force, which for a row that has never been
            -- told otherwise is the global. Sending an entity's own default of
            -- 3 made every row look like a decision somebody had taken, and
            -- changing the global then appeared to do nothing.
            radius = ownRadius or globalRadius,
            radiusInherited = ownRadius == nil,
            -- The mark the entity wears, and what it looks like. Each field is
            -- the value actually in force -- the entity's own where it has
            -- one, the global where it has not -- with a flag beside it saying
            -- which, because a colour that came from Settings looks exactly
            -- like a colour somebody chose.
            showCorona = showCorona,
            showCoronaInherited = ownShowCorona == nil,
            coronaColor = ownCoronaColor or globalCoronaColor,
            coronaColorInherited = ownCoronaColor == nil,
            coronaOpacity = ownCoronaOpacity or globalCoronaOpacity,
            coronaOpacityInherited = ownCoronaOpacity == nil,
            -- Which way in this entity offers, and the key that takes it. Same
            -- shape as the radius above: the value in force, and whether it is
            -- the entity's own.
            activationType = ownActivationType or globalActivationType,
            activationTypeInherited = ownActivationType == nil,
            activationKey = ownActivationKey or globalActivationKey,
            activationKeyInherited = ownActivationKey == nil,
            -- What this entity would carry in `Show text`: the three settings
            -- in force on it, and beside them what the label really says.
            --
            -- Sent on every row whatever the mode is. The overrides are edited
            -- here, and a player setting them has to see what they did without
            -- changing mode first -- and a chosen field that falls through to
            -- another one has to read as a fall-through rather than as
            -- correct, which is the whole reason `textLabel` travels at all.
            textLabelField = ownLabelField or globalLabelField,
            textLabelFieldInherited = ownLabelField == nil,
            textLabelColor = ownLabelColor or globalLabelColor,
            textLabelColorInherited = ownLabelColor == nil,
            textLabelSize = ownLabelSize or globalLabelSize,
            textLabelSizeInherited = ownLabelSize == nil,
            textLabel = entry.textLabel or false,
            -- What is on the row now, so the replace confirmation can name
            -- what it is about to throw away rather than saying "unknown".
            linkedCard = type(entry.link.cardIdentity) == "table"
                and tostring(entry.link.cardIdentity.cardId or "") or false,
            recheckAvailable = entry.link.recheckAvailable == true,
            copyCollision = entry.link.copyCollision == true,
            -- In the world but not in the store yet: Link takes it in.
            adoptable = entry.adoptable == true,
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
local function mapNamesForCard(cardIdentity, f7Snapshot)
    local current = {}
    local currentMap = f7Snapshot and f7Snapshot.currentMap or {}
    for _, mapId in ipairs(currentMap.mapIds or {}) do
        current[tostring(mapId)] = true
    end
    local names, foreignNames, seen, seenForeign = {}, {}, {}, {}
    for _, link in ipairs(f7Snapshot and f7Snapshot.cardLinks or {}) do
        if tostring(link.collectionUuid or "")
                == tostring(cardIdentity.collectionUuid or "")
            and tostring(link.cardId or "") == tostring(cardIdentity.cardId or "")
        then
            local name = tostring(link.mapName or link.mapId or "")
            if name ~= "" and not seen[name] then
                seen[name] = true
                names[#names + 1] = name
            end
            if name ~= "" and not current[tostring(link.mapId)]
                and not seenForeign[name]
            then
                seenForeign[name] = true
                foreignNames[#foreignNames + 1] = name
            end
        end
    end
    table.sort(names)
    table.sort(foreignNames)
    return #names > 0 and table.concat(names, ", ") or false,
        #foreignNames > 0 and table.concat(foreignNames, ", ") or false
end

local function cardRows(snapshot, f7Snapshot)
    local rows, seenCards = {}, {}
    local function appendCard(card)
        local identity = card.identity or {}
        local deck = card.deck or {}
        local identityKey = tostring(identity.collectionUuid or "")
            .. "\0" .. tostring(identity.cardId or "")
        if seenCards[identityKey] then
            return
        end
        seenCards[identityKey] = true
        local linkedMapName, foreignMapName = mapNamesForCard(identity, f7Snapshot)
        table.insert(rows, {
            cardId = tostring(identity.cardId or ""),
            collectionUuid = tostring(identity.collectionUuid or ""),
            deck = tostring(deck.name or ""),
            state = tostring(card.state or ""),
            -- What Anki lists the note by. A row headed by a card id names
            -- nothing the player chose it for.
            --
            -- `sortField`, the name the companion and Anki both use, rather
            -- than `label`: **Text Label** is a line drawn on a Map Entity and
            -- this is the heading of a row in the Card Picker, and one word
            -- for the two of them is a word that stops meaning either.
            sortField = tostring(card.sortField or ""),
            linkedTo = card.linkedTo or false,
            linked = linkedMapName ~= false,
            linkedMapName = linkedMapName,
            foreignMap = foreignMapName ~= false,
            foreignMapName = foreignMapName,
        })
    end
    for _, card in ipairs(snapshot and snapshot.cards or {}) do
        appendCard(card)
    end
    -- A foreign link must remain visible even when the current Anki search or
    -- page did not return that card. Its durable identity is enough to offer a
    -- selectable placeholder; a later search can enrich the same row.
    for _, link in ipairs(f7Snapshot and f7Snapshot.cardLinks or {}) do
        local identity = {
            collectionUuid = link.collectionUuid,
            cardId = link.cardId,
        }
        local _, foreignMapName = mapNamesForCard(identity, f7Snapshot)
        if foreignMapName then
            appendCard({identity = identity})
        end
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

--- The decks a filter can be chosen from, by name.
--
-- The picker took a deck as typed text, so a name spelled wrong and a deck
-- with nothing in it looked exactly alike. A list cannot be misspelled.
local function deckNames(snapshot)
    local names = {}
    for _, deck in ipairs(snapshot and snapshot.decks or {}) do
        if type(deck.name) == "string" and deck.name ~= "" then
            names[#names + 1] = deck.name
        end
    end
    return names
end

--- The whole string table, for a page that holds keys rather than words.
local function localeTable()
    return ANKIGTA.Locale and ANKIGTA.Locale.strings or {}
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
        --
        -- Nor is `Show text`. There is no session in it to resume (ADR 0029)
        -- and the server refuses to build one, so a button offered here would
        -- be a button whose only outcome is an error message.
        resumable = study.sessionActive ~= true
            and pausedReason ~= false
            and pausedReason ~= "rebuilding"
            and pausedReason ~= "not_started"
            and currentValue("reviewMode") ~= "show_text",
    }
end

local function push()
    if not pageReady or not isElement(browser) then
        return
    end
    local state = {
        section = section(),
        locale = localeTable(),
        connection = {
            state = lastStatus and lastStatus.state or "disconnected",
            category = lastStatus and lastStatus.category or false,
            sessionCategory = lastStatus and lastStatus.sessionCategory or false,
            warningCategory = lastStatus and lastStatus.warningCategory or false,
            port = connectionSettings.port or false,
            tokenConfigured = connectionSettings.tokenConfigured == true,
            tokenDisabled = connectionSettings.tokenDisabled == true,
            settingsVersion = connectionSettingsVersion,
            portError = settingsRejections.connectionPort or false,
            tokenError = settingsRejections.connectionToken or false,
        },
        entities = entityRows(lastSnapshot),
        -- Objects the player deleted from the map. Not rows -- that is the
        -- point of deleting one -- so they travel beside the list, and the
        -- ones already answered about are dropped here rather than asked
        -- again on every snapshot.
        deletedFromMap = unansweredDeletions(lastSnapshot),
        -- Whether a click on a row also points the camera at it. The player's
        -- own answer, and pushed with the state like everything else the page
        -- draws from: the page decides nothing.
        focusOnSelect = currentValue("focusOnSelect") ~= false,
        -- The other way of looking the pane offers. It is on the entity pane
        -- rather than in Settings and it is still the client's own, so it
        -- travels beside `focusOnSelect` rather than among the settings rows.
        drawRadius = currentValue("drawRadius") == true,
        entityFilter = entityFilter,
        entityTotal = #(lastSnapshot and lastSnapshot.entities or {}),
        study = studyState(),
        selected = {
            mapId = selectedMapId or false,
            entityId = selectedEntityId or false,
            cardId = selectedCard and selectedCard.cardId or false,
            -- An object waiting to be adopted has no row to point at, so the
            -- page is told it exists rather than left to infer it from a
            -- selection that is deliberately empty.
            adopting = isElement(adoptionTarget) or false,
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
            cards = cardRows(lastCards, lastSnapshot),
            decks = deckNames(lastCards),
            deckFilter = lastCards and lastCards.deckFilter or false,
            -- What was actually searched for, as the companion understood it.
            -- The page keeps its own field while typing; this is what the
            -- rows below it are an answer to.
            query = lastCards and lastCards.query or "",
            scope = lastCards and lastCards.scope or "cards",
        },
        -- What the selected card actually says, once it has been read.
        note = selectedNote or false,
        noteError = noteError or false,
        notice = notice,
        settings = {
            rows = settingsRows(),
            -- The question the sweep asks before it runs, or `false` while
            -- nothing has been asked. It is the server's count, so the page
            -- names the number of links that are really about to change.
            pendingClear = pendingOverrideClear or false,
        },
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
-- 1180 was two columns, 590 each: the Map Entity list and the Card Picker. The
-- selected entity's own pane is a third, 400 wide, and it is here rather than in
-- the editor's share below because it never folds away -- so it is part of how
-- big this window is rather than something the window grows for.
--
-- That distinction is load-bearing, not tidiness. The layout manager clamps a
-- drag and stores the placement against the width it was told, and the browser
-- is drawn at the width `panelRect` works out; a permanent difference between
-- the two means a drag is remembered at one position and drawn at another, and
-- the panel jumps by the difference the moment it is grabbed.
if ANKIGTA.Layout then
    ANKIGTA.Layout.define("panel", {
        width = 1580,
        height = 700,
        margin = 20,
        anchorX = 0.5,
        anchorY = 0.5,
    })
end

--- How much wider the panel is while the card editor is out, as a share of
--- its own width.
--
-- The editor slides out beside the two lists rather than taking a third of the
-- room from them. Fitting a third column inside a window sized for two is what
-- left every column cramped: the lists did not ask to be narrower because
-- somebody opened an editor.
local EDITOR_WIDTH_SHARE = 0.34

local function panelRect()
    local x, y, width, height
    if ANKIGTA.Layout then
        x, y, width, height = ANKIGTA.Layout.rect("panel")
    else
        local screenWidth, screenHeight = guiGetScreenSize()
        width = math.min(screenWidth - 40, 1180)
        height = math.min(screenHeight - 40, 700)
        x = (screenWidth - width) / 2
        y = (screenHeight - height) / 2
    end
    if not editorOpen then
        return x, y, width, height
    end
    -- Grown from the width already in force, so UI Scale and any clamp the
    -- layout applied are carried rather than recomputed.
    local screenWidth = guiGetScreenSize()
    width = math.min(width * (1 + EDITOR_WIDTH_SHARE), screenWidth)
    -- Widening at a fixed left edge would push the right edge off screen for a
    -- panel already sitting near it.
    if x + width > screenWidth then
        x = math.max(0, screenWidth - width)
    end
    return x, y, width, height
end

--- Give the panel the size its current shape asks for.
--
-- `CGUIWebBrowser_Impl::SetSize` resizes the underlying web view as well as the
-- CEGUI element, so the page is re-laid out at the new width rather than
-- stretched.
local function resizePanel()
    if not isPanelOpen() then
        return
    end
    local x, y, width, height = panelRect()
    guiSetPosition(guiBrowser, x, y, false)
    guiSetSize(guiBrowser, width, height, false)
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
    -- The other half of what `closePanel` does: the zone belongs to the window,
    -- so it goes up with it rather than at the next poll.
    if ANKIGTA.WorldMarks then
        ANKIGTA.WorldMarks.refresh()
    end
end

-- The page reports only that a drag started: the cursor is MTA's to report, and
-- a mouse button released outside the page never reaches it, so the loop
-- watches the button. `dragFrom` itself is declared at the top of this file.
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
    triggerServerEvent(CONNECTION_SETTINGS_REQUEST_EVENT, resourceRoot)
end

--- The key this panel opens on, when the schema cannot be asked.
--
-- Pinned equal to `Settings.reservedKeys.panel` by a test, so the two cannot
-- drift while this exists to be used at all.
local FALLBACK_PANEL_KEY = "F7"

--- Through the schema, not by name. `activationKey` is refused when it names
--- a key ANKIGTA already answers to, and that refusal is only honest while
--- the list it reads is the list this binds from.
--
-- Asked when the resource starts rather than while this chunk loads, and asked
-- defensively. A running client receives a changed `cache="false"` script one
-- restart before a changed or newly added shared one -- the same window
-- `ANKIGTA.EntityTypes` is guarded against above -- so `ANKIGTA.Settings` can
-- still be absent here. It was: this line read it at load time from ticket 05
-- until this fix, and a chunk that errors never reaches the command handlers
-- below it. So F7 and `/ankigta-connection` went away together, which is the
-- one combination that leaves no way back in.
local function panelKey()
    local settings = schema()
    local reserved = settings and settings.reservedKeys
    if reserved and reserved.panel then
        return reserved.panel
    end
    outputDebugString(
        "[ANKIGTA] settings schema absent while binding the panel key;"
            .. " falling back to " .. FALLBACK_PANEL_KEY,
        2
    )
    return FALLBACK_PANEL_KEY
end

addEventHandler("onClientResourceStart", resourceRoot, function()
    bindKey(panelKey(), "down", togglePanel)
end)

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

--- The way into the panel's own settings.
-- A screen of its own, and rightly: there is nothing behind the window to look
-- at while these are changed. The pane that had to stop covering the list is
-- the one that edits the selected Map Entity, and it is a column now.
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
    if not definition or not editableFromPanel(key, definition.rule or {}) then
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
        triggerServerEvent(SETTINGS_UPDATE_EVENT, resourceRoot, key, value)
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
    settingsRejections.connectionPort = nil
    if payload.keepToken ~= true then
        settingsRejections.connectionToken = nil
    end
    triggerServerEvent(CONNECTION_UPDATE_EVENT, resourceRoot, payload)
    push()
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

--- Take me to the thing I have selected.
--
-- The prior resource had this next to its object list, and it is why a player
-- could work at all: a row you cannot find in the world is a row you cannot
-- judge. The server owns the move, including for a row that is only an offer.
function actions.teleport()
    local entry = selectedEntry()
    if not entry then
        return
    end
    -- Teleport is the one row action that leaves F7. The panel goes first, so
    -- the player is looking at the world when they arrive -- but the camera it
    -- borrowed for a focus is NOT handed back, because handing it back aims
    -- the view at wherever the player used to be standing.
    teleporting = true
    closePanel()
    teleporting = false
    triggerServerEvent(
        TELEPORT_REQUEST_EVENT,
        resourceRoot,
        entry.mapEntity.mapId,
        entry.mapEntity.entityId
    )
end

--- How close the player must stand to *this* entity, and how it is marked.
--
-- Properties of the thing rather than of the player, which is why they live on
-- the row and not in Settings. Offered for an offer too: the server takes the
-- entity in when it is first written to, so naming a thing or saying how close
-- you must stand to it no longer waits for a card to be chosen.
--
-- Three answers per field, and they are not the same: absent means the player
-- did not touch it, `"inherit"` means they cleared it and the entity follows
-- Settings again, and a value means they set one. Coercing `"inherit"` to
-- `nil` here is how "clear this" would silently become "leave it alone".
--
-- `"inherit"` rather than `false`: `Show corona` is overridable now, and
-- `false` is one of the two things it can be told to be.
local INHERIT = "inherit"

local function overridden(sent, convert)
    if sent == nil or sent == INHERIT then
        return sent
    end
    return convert and convert(sent) or sent
end

function actions.setEntityMarks(payload)
    local entry = selectedEntry()
    if not entry then
        return
    end
    triggerServerEvent(
        ENTITY_METADATA_REQUEST_EVENT,
        resourceRoot,
        entry.mapEntity.mapId,
        entry.mapEntity.entityId,
        {
            radius = overridden(payload.radius, tonumber),
            showCorona = overridden(payload.showCorona),
            coronaColor = overridden(payload.coronaColor),
            coronaOpacity = overridden(payload.coronaOpacity, tonumber),
            activationType = overridden(payload.activationType),
            activationKey = overridden(payload.activationKey),
            textLabelField = overridden(payload.textLabelField),
            textLabelColor = overridden(payload.textLabelColor),
            textLabelSize = overridden(payload.textLabelSize, tonumber),
        }
    )
end

--- Clear one setting's overrides on every link, once the player has agreed.
--
-- Asked first, always: the sweep is not undone by pressing the control again,
-- so the server answers with how many links it would change and the page shows
-- that before anything happens.
function actions.clearEntityOverrides(payload)
    local key = payload and payload.key
    if type(key) ~= "string" or not schema().entityOverrideColumn(key) then
        return
    end
    local confirmed = payload.confirmed == true
    if confirmed then
        -- The question has been answered, so it goes off screen now rather
        -- than when the next snapshot happens to arrive.
        pendingOverrideClear = false
        push()
    end
    triggerServerEvent(CLEAR_ENTITY_OVERRIDES_EVENT, resourceRoot, key, confirmed)
end

--- Leave the sweep unasked.
function actions.cancelClearEntityOverrides()
    pendingOverrideClear = false
    push()
end

--- Point the camera at a row without moving the Study Player.
--
-- Sent by the same click that selects, because selecting a row and looking at
-- it are the same intention almost every time. The identity arrives with the
-- click itself so the click and the round-trip that follows it cannot leave
-- the camera acting on the previously selected row.
function actions.focusEntity(payload)
    if type(payload.mapId) ~= "string" or type(payload.entityId) ~= "string" then
        return
    end
    local entry = nil
    for _, candidate in ipairs(lastSnapshot and lastSnapshot.entities or {}) do
        if candidate.mapEntity.mapId == payload.mapId
            and candidate.mapEntity.entityId == payload.entityId
        then
            entry = candidate
            break
        end
    end
    if not entry then
        return
    end
    local mapEntity = entry.mapEntity
    local authored = type(mapEntity.authored) == "table" and mapEntity.authored or {}
    local position = type(authored.position) == "table" and authored.position or {}
    local world = type(authored.world) == "table" and authored.world or {}
    local x = tonumber(position.x)
    local y = tonumber(position.y)
    local z = tonumber(position.z)
    local interior = tonumber(world.interior) or 0
    local kind = mapEntity.type

    -- Prefer the current Runtime Instance even when it is not streamed. If
    -- the client has no element at all, the authored Map Entity position is
    -- still enough to point the camera at a distant row.
    local element = runtimeElement(payload.mapId, payload.entityId, false)
    if isElement(element) then
        local runtimeX, runtimeY, runtimeZ = getElementPosition(element)
        if type(runtimeX) == "number" then
            x, y, z = runtimeX, runtimeY, runtimeZ
        end
        interior = getElementInterior(element) or interior
        kind = getElementType(element) or kind
    end
    if type(x) ~= "number" or type(y) ~= "number" or type(z) ~= "number" then
        return
    end
    local distance = kind == "vehicle" and 9 or 6
    -- Hold first, then move the camera. The other order leaves a window in
    -- which the camera has already gone and the player is still falling.
    holdPlayerStill()
    if not focusedCamera then
        focusedCamera = {
            matrix = {getCameraMatrix()},
            target = getCameraTarget(),
            interior = getCameraInterior(),
        }
    end
    setCameraInterior(interior)
    setCameraMatrix(
        x + distance,
        y + distance,
        z + math.max(3, distance * 0.55),
        x,
        y,
        z,
        0,
        70
    )
end

function actions.setEntityName(payload)
    local entry = selectedEntry()
    if not entry or type(payload.name) ~= "string" then
        return
    end
    triggerServerEvent(
        ENTITY_METADATA_REQUEST_EVENT,
        resourceRoot,
        entry.mapEntity.mapId,
        entry.mapEntity.entityId,
        {name = payload.name}
    )
end

function actions.recheck()
    if selectedMapId and selectedEntityId then
        triggerServerEvent(
            RECHECK_REQUEST_EVENT, resourceRoot, selectedMapId, selectedEntityId
        )
    end
end

--- Remove everything ANKIGTA holds about an object that left the map.
function actions.forgetEntity()
    local entry = firstDeletion()
    if not entry then
        return
    end
    triggerServerEvent(
        FORGET_ENTITY_REQUEST_EVENT,
        resourceRoot,
        entry.mapId,
        entry.entityId
    )
end

--- Keep the saved link, and stop asking.
function actions.keepDeletedEntity()
    local entry = firstDeletion()
    if not entry then
        return
    end
    answeredDeletions[
        tostring(entry.mapId) .. "\0" .. tostring(entry.entityId)
    ] = true
    push()
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

--- The page has slid the card editor out, or put it away.
--
-- The page cannot resize its own window, so it says which shape it is in and
-- this gives it the room. Held on this side too, so that reopening F7 starts
-- from the panel's own width rather than from whatever the page last did.
function actions.editorVisible(payload)
    local open = payload.open == true
    if open == editorOpen then
        return
    end
    editorOpen = open
    resizePanel()
end

function actions.searchCards(payload)
    searchRequestedAt = getTickCount()
    triggerServerEvent(
        CARD_PICKER_REQUEST_EVENT,
        resourceRoot,
        -- The expression as written. Anki is the thing that understands
        -- `deck:Spanish -is:suspended`, so nothing on the way there touches it.
        tostring(payload.query or ""),
        tostring(payload.deck or ""),
        0,
        50,
        -- Absent rather than empty when the page did not choose: the server
        -- refuses a scope it does not have, and "" is not one of them.
        type(payload.scope) == "string" and payload.scope ~= ""
            and payload.scope
            or false
    )
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

function actions.selectCard(payload)
    -- A different card means the note on screen belongs to nobody until the
    -- new one arrives. Leaving the old one up would let a save write the
    -- fields of one card onto another.
    selectedNote = false
    noteError = false
    if type(payload.cardId) ~= "string" or payload.cardId == "" then
        selectedCard = nil
    else
        selectedCard = {
            cardId = payload.cardId,
            collectionUuid = tostring(payload.collectionUuid or ""),
        }
        triggerServerEvent(
            NOTE_READ_REQUEST_EVENT, resourceRoot, cardIdentity()
        )
    end
    push()
end

--- Write the inspector's fields and tags back to Anki.
function actions.saveNote(payload)
    local identity = cardIdentity()
    if not identity or type(payload.fields) ~= "table" then
        return
    end
    triggerServerEvent(
        NOTE_UPDATE_REQUEST_EVENT,
        resourceRoot,
        identity,
        payload.fields,
        type(payload.tags) == "table" and payload.tags or {}
    )
end

function actions.link()
    local identity = cardIdentity()
    if not identity then
        return
    end
    -- An object with no identity yet is adopted by the act of linking: the
    -- card is what it is for, so the card is what brings it into the store.
    if isElement(adoptionTarget) then
        triggerServerEvent(
            ADOPT_ENTITY_REQUEST_EVENT,
            resourceRoot,
            adoptionTarget,
            identity
        )
        adoptionTarget = nil
        return
    end
    local entry = selectedEntry()
    if not entry then
        return
    end
    -- A row the list offered rather than one the store holds: it is named, so
    -- the server can find it again, but there is nothing yet to link to.
    if entry.adoptable == true then
        triggerServerEvent(
            ADOPT_ENTITY_REQUEST_EVENT,
            resourceRoot,
            entry.mapEntity.entityId,
            identity
        )
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
    -- What is marked has just changed, so what is drawn is out of date until
    -- the next look at the world -- which is a quarter of a second away and
    -- is exactly the pause between ticking `Show corona` and seeing one.
    if ANKIGTA.WorldMarks then
        ANKIGTA.WorldMarks.refresh()
    end
    -- And the map, for the same reason: a link made a moment ago is an entity
    -- that has just stopped reading as disconnected.
    if ANKIGTA.Indicator and ANKIGTA.Indicator.refreshMap then
        ANKIGTA.Indicator.refreshMap()
    end
    -- Cards without being asked for. Opening the picker *is* the question, and
    -- an empty list behind a button reads as "your collection has nothing" --
    -- which is also why the deck list was missing: the companion sends it with
    -- a search page, so until one had run there were no decks to choose from.
    if not searchIssued
        and type(snapshot.cardPicker) == "table"
        and snapshot.cardPicker.enabled == true
    then
        searchIssued = true
        actions.searchCards({})
    end
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
    -- A search that answered clears the last complaint about searching, and
    -- only that one. Nothing else dismisses a notice, so "Anki did not accept
    -- the search" would otherwise sit over the correct rows the player got by
    -- fixing exactly what it complained about.
    if notice and CARD_PICKER_NOTICES[notice.key] then
        notice = false
    end
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

--- The player has been moved. Take the view with them.
--
-- Inside the stock Map Editor the camera is what holds the player:
-- `editor_main/client/attachplayer.lua` runs
-- `setElementPosition(localPlayer, getCameraMatrix())` on every frame, so a
-- player the server moved is dragged back before the next frame is drawn --
-- which is what "the camera goes back to its map-editor position" was. The
-- camera has to be moved instead, and only this side can move it.
--
-- Told apart by who the camera is following rather than by asking the editor
-- whether it is open: a camera with no target is a camera somebody is holding
-- in a fixed position, and that somebody is the one dragging the player.
addEvent(TELEPORT_ARRIVED_EVENT, true)
addEventHandler(TELEPORT_ARRIVED_EVENT, resourceRoot, function(target)
    if source ~= resourceRoot or type(target) ~= "table" then
        return
    end
    local x, y, z = tonumber(target.x), tonumber(target.y), tonumber(target.z)
    if not x or not y or not z then
        return
    end
    if isElement(getCameraTarget()) then
        -- An ordinary follow camera is already looking at the player, and the
        -- player has already moved.
        return
    end
    setCameraInterior(tonumber(target.interior) or 0)
    -- Beside the entity and looking at it, the same offset a focus uses, so
    -- arriving looks like the focus the player just had.
    setCameraMatrix(x + 6, y + 6, z + 3.3, x, y, z, 0, 70)
end)

addEvent(PENDING_NOTICE_EVENT, true)
-- The server sends the key and the outcome code; the side that draws is the
-- side that words it.
addEventHandler(PENDING_NOTICE_EVENT, resourceRoot, function(noticeKey, outcome)
    if type(noticeKey) ~= "string" then
        return
    end
    -- The code itself goes where a code belongs: the diagnostics report, whose
    -- whole point is that every value in it is a stable technical name a bug
    -- report can be written around. What the player is shown is the sentence.
    record("notice", {key = noticeKey, outcome = tostring(outcome)})
    -- Worded on the way in, because the page substitutes `detail` into the
    -- template as it is given and has no string table of its own to word a
    -- refusal code with. The chat line is `Locale.format`'s to word.
    notice = {
        key = noticeKey,
        detail = ANKIGTA.Locale and ANKIGTA.Locale.reason(outcome)
            or tostring(outcome),
    }
    if ANKIGTA.Locale then
        outputChatBox(
            ANKIGTA.Locale.format(noticeKey, tostring(outcome)), 255, 196, 64
        )
    end
    push()
end)

addEvent(PICK_ENTITY_FINISHED_EVENT, false)
addEventHandler(PICK_ENTITY_FINISHED_EVENT, resourceRoot, function(
    success, reason, mapId, entityId, mode, element
)
    if success == true and isElement(element) then
        -- Placed by the editor, not adopted yet. There is no row to select, so
        -- the object waits here until a card says what it is for.
        adoptionTarget = element
        selectedMapId = nil
        selectedEntityId = nil
    elseif success == true then
        adoptionTarget = nil
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

addEvent(NOTE_SNAPSHOT_EVENT, true)
addEventHandler(NOTE_SNAPSHOT_EVENT, resourceRoot, function(ok, payload, reason)
    if source ~= resourceRoot then
        return
    end
    if ok == true and type(payload) == "table" then
        -- A read answers with the card, an update with the note alone.
        selectedNote = type(payload.card) == "table" and payload.card.note
            or payload.note
        noteError = false
    else
        selectedNote = false
        noteError = reason or "unexpected_error"
    end
    push()
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

addEvent(CONNECTION_SETTINGS_SNAPSHOT_EVENT, true)
addEventHandler(CONNECTION_SETTINGS_SNAPSHOT_EVENT, resourceRoot, function(values)
    if source ~= resourceRoot or type(values) ~= "table" then
        return
    end
    connectionSettings = values
    connectionSettingsVersion = connectionSettingsVersion + 1
    push()
end)

addEvent(ENTITY_OVERRIDE_COUNT_EVENT, true)
addEventHandler(ENTITY_OVERRIDE_COUNT_EVENT, resourceRoot, function(key, count)
    if source ~= resourceRoot or type(key) ~= "string" then
        return
    end
    -- What the sweep would do, as the side that would do it counted it. Held
    -- here rather than on the page for the same reason the selection is: the
    -- page is a view, and a number it worked out itself is a number that can
    -- disagree with the one about to be acted on.
    pendingOverrideClear = {key = key, count = tonumber(count) or 0}
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

local entityRefreshTimer = nil

--- Ask the server for the entity set again, once the world stops changing.
--
-- Not gated on the panel being open. It was, and that made sense while the
-- snapshot was only ever a list on screen -- but the marks are drawn out of
-- the same snapshot and they are a property of the world, so a map loaded
-- after the player joined, or a corona another player ticked, would have gone
-- unmarked until somebody pressed F7. That is the defect this ticket is about,
-- one step further along.
--
-- Coalesced on a timer, so a map loading a thousand elements asks once.
local function scheduleEntityRefresh()
    if not authorized then
        return
    end
    if isTimer(entityRefreshTimer) then
        killTimer(entityRefreshTimer)
    end
    entityRefreshTimer = setTimer(function()
        entityRefreshTimer = nil
        if authorized then
            triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
        end
    end, 100, 1)
end

--- Would the Map Entity list ever have a row for this element?
--
-- A marker is one of the types a card can hang on, so a marker appearing is
-- normally a reason to re-read the list. ANKIGTA's own coronas are markers
-- too, and they appear and disappear as the player walks around and as a
-- colour changes -- each one asking the server to rebuild the whole snapshot,
-- which produces the next snapshot, which is what decides where the coronas
-- go. The marks say which elements are theirs so that loop cannot start.
local function couldBeARow(element)
    if not PANEL_ENTITY_TYPE[getElementType(element)] then
        return false
    end
    if ANKIGTA.WorldMarks and ANKIGTA.WorldMarks.owns(element) then
        return false
    end
    return true
end

addEventHandler("onClientElementCreate", root, function()
    if couldBeARow(source) then
        scheduleEntityRefresh()
    end
end)

addEventHandler("onClientElementDestroy", root, function()
    if couldBeARow(source) then
        scheduleEntityRefresh()
    end
end)

addEventHandler("onClientElementDataChange", root, function()
    if couldBeARow(source) then
        scheduleEntityRefresh()
    end
end)

local function refreshRuntimeAvailability()
    -- A corona streaming in is ANKIGTA drawing, not the world changing.
    if ANKIGTA.WorldMarks and ANKIGTA.WorldMarks.owns(source) then
        return
    end
    if authorized and isPanelOpen() then
        push()
    end
end

addEventHandler("onClientElementStreamIn", root, refreshRuntimeAvailability)
addEventHandler("onClientElementStreamOut", root, refreshRuntimeAvailability)

addEvent(AUTHORIZATION_EVENT, true)
addEventHandler(AUTHORIZATION_EVENT, resourceRoot, function(value)
    authorized = value == true
    if not authorized then
        closePanel()
        return
    end
    -- Asked for on the way in, not only when F7 opens. A corona is worn by the
    -- entity whether or not anyone is looking at a list, and this snapshot is
    -- where the client learns which entities wear one; without it they would
    -- appear the first time the panel was opened, and a player who never
    -- opened it would see none at all.
    triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStart", resourceRoot, function()
    triggerServerEvent(AUTHORIZATION_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, closePanel)

ANKIGTA.Panel = {
    isOpen = isPanelOpen,
    close = closePanel,
    rows = entityRows,
    matching = panelMatching,
    -- What the world marks read. The panel holds the snapshot and the
    -- selection, so what draws asks here rather than keeping a second copy
    -- that can disagree with this one.
    selection = panelSelection,
    markable = panelMarkable,
    -- What the map reads. Same rule as `markable`: the panel holds the
    -- snapshot, so what draws asks here instead of keeping a second copy.
    mapEntities = panelMapEntities,
    runtimeElements = runtimeElementsFor,
    entityKey = panelEntityKey,
    -- Which key the panel actually bound, and the literal it falls back to.
    -- Exposed so a test can hold the two equal: the fallback exists for the
    -- window where the schema cannot be read, and a fallback that opens a
    -- different key from the one the schema reserves is worse than none.
    key = panelKey,
    fallbackKey = FALLBACK_PANEL_KEY,
}

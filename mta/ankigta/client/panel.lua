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
local ENTITY_METADATA_REQUEST_EVENT = "ankigta:updateEntityMetadata"
local ADOPT_ENTITY_REQUEST_EVENT = "ankigta:adoptEntity"
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
--- Every map the server knows about, and whether its entities take part in
--- study. Held apart from `serverValues` because this one setting is per map.
local serverMaps = {}
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

local function restoreFocusedCamera()
    if not focusedCamera then
        return
    end
    setCameraInterior(focusedCamera.interior or 0)
    if isElement(focusedCamera.target) then
        setCameraTarget(focusedCamera.target)
    elseif type(focusedCamera.matrix) == "table"
        and #focusedCamera.matrix >= 6
    then
        setCameraMatrix(unpack(focusedCamera.matrix))
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

--- The one setting that is per map, as a row per map.
--
-- `includeInStudy` decides whether one map's entities take part in the study
-- session; excluding a map must not take the rest of the Active Map Set with
-- it. Built from the schema like every other setting, it came out as a single
-- switch belonging to no map at all -- one that wrote a global value nothing
-- reads, under a name that promised something about maps.
--
-- The label is the map's own name, which is the user's words and so is never
-- translated; the setting's name introduces the group above them.
--
-- A refusal is remembered against the map it was about, not against the
-- setting: one refused map must not put a red border on every other map's row.
local function rejectionKey(key, mapId)
    if type(mapId) ~= "string" or mapId == "" then
        return key
    end
    return key .. "\0" .. mapId
end

local function appendMapPreferenceRows(rows, key)
    table.insert(rows, {
        key = key,
        labelKey = "settings." .. key,
        kind = "heading",
    })
    if #serverMaps == 0 then
        table.insert(rows, {
            key = key,
            labelKey = "settings.noMaps",
            kind = "note",
        })
        return
    end
    for _, preference in ipairs(serverMaps) do
        table.insert(rows, {
            key = key,
            mapId = preference.mapId,
            labelText = preference.mapName or preference.mapId,
            kind = "boolean",
            value = preference.includeInStudy == true,
            owner = "server",
            error = settingsRejections[rejectionKey(key, preference.mapId)]
                or false,
        })
    end
end

local function settingsRows()
    local rows = {}
    for _, key in ipairs(schema().orderedKeys()) do
        local definition = schema().definition(key)
        local rule = definition and definition.rule or {}
        if key == "includeInStudy" then
            appendMapPreferenceRows(rows, key)
        elseif offered(key, rule) then
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

--- Is this the stock Map Editor's own stand-in for an element?
--
-- Read off the element rather than asked of `edf`. `edfIsRepresentation` is a
-- server-only export -- `edf.lua` is one line, `getElementData(elem,
-- "edf:rep")` -- and calling it from here answered nothing while logging an
-- MTA error per call. Not a raise, so the `pcall` that used to wrap this
-- reported success and the falsy answer read as "not a representation": the
-- filter below never fired, and the duplicate row it exists to remove was
-- never removed. `edf`'s own client half reads the same element data.
local function isEditorRepresentation(element)
    return getElementData(element, "edf:rep") == true
end

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
--
-- The editor's own representation of an object is excluded -- it carries the
-- same identity as the object it represents, so without this every entity is
-- found twice while the editor is running.
local function elementStandsFor(element, mapId, entityId)
    local persistentId, editorId, elementId = elementIdentities(element)
    local elementMapId = getElementData(element, "ankigtaMapId")
    return (persistentId == entityId or editorId == entityId
            or elementId == entityId)
        and (not elementMapId or elementMapId == mapId)
        and not isEditorRepresentation(element)
end

--- Resolve the real copy of a Map Entity when editor and play-test copies
-- temporarily share the same MTA ID. Prefer the streamed copy because that is
-- the one the player can actually see and focus right now.
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
local function panelEntityKey(mapId, entityId)
    return tostring(mapId) .. "/" .. tostring(entityId)
end

--- The streamed Runtime Instance of each of several Map Entity, at once.
--
-- One walk of the world for the whole set, keyed by `panelEntityKey`. The world
-- holds thousands of elements and `runtimeElement` walks all of them per
-- identity; what draws marks on the world asks about every entity that shows
-- one, and doing that a walk at a time is the world once per mark.
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
    --- Record this element against every Map Entity that asked for this id.
    --
    -- Narrowed to the ids somebody asked about, never the thousands in the
    -- world that nobody did: everything `elementStandsFor` does is per
    -- candidate, and it used to include a call into another resource.
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

--- Something a person can read, for a row nobody has named.
--
-- The prior resource walked `name`, `me:name`, `me:Name`, `me:ID` and then the
-- *model* name, and that last step is the one that matters: an object nobody
-- named reads as "Infernus" rather than as the hash that identifies it. The
-- model name is not user content, so translating nothing here is correct.
--
-- Client-side because that is where the model tables are: the server has no
-- `engineGetModelNameFromID`.
local function readableName(entry)
    -- The name the user typed, wherever this snapshot carried it. Theirs
    -- first and always: the model name is only for a row nobody has named.
    local typed = entry.metadata and entry.metadata.name
    if type(typed) ~= "string" or typed == "" then
        typed = entry.link and entry.link.metadata and entry.link.metadata.name
    end
    if type(typed) == "string" and typed ~= "" then
        return typed
    end
    local mapEntity = entry.mapEntity
    local model = tonumber(mapEntity.model)
    if not model then
        return ANKIGTA.Locale.text("f7.entity.unnamed")
    end
    if mapEntity.type == "vehicle" and getVehicleNameFromModel then
        local name = getVehicleNameFromModel(model)
        if type(name) == "string" and name ~= "" then
            return name
        end
    end
    if engineGetModelNameFromID then
        local name = engineGetModelNameFromID(model)
        if type(name) == "string" and name ~= "" then
            return name
        end
    end
    return ANKIGTA.Locale.text("f7.entity.unnamed")
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
    local rows = {}
    -- What an entity that says nothing of its own gets, read once rather than
    -- per row: it is the same answer for every one of them, and this runs over
    -- the whole list on every state push.
    local settingsCoronaColour = currentValue("coronaColour") or false
    for _, entry in ipairs(snapshot and snapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        table.insert(rows, {
            mapId = mapEntity.mapId,
            entityId = mapEntity.entityId,
            type = mapEntity.type,
            name = readableName(entry),
            description = entityDescription(mapEntity),
            model = tonumber(entry.mapEntity.model) or 0,
            linkState = entry.link.state,
            guidanceKey = entry.link.guidanceKey or false,
            radius = tonumber(entry.metadata and entry.metadata.radius) or 3,
            showCorona = entry.metadata
                and entry.metadata.showCorona == true or false,
            -- `false` where the entity says nothing of its own, which the page
            -- shows as an empty field and the world draws from Settings.
            coronaColour = entry.metadata
                and entry.metadata.coronaColour or false,
            coronaOpacity = entry.metadata
                and entry.metadata.coronaOpacity or false,
            -- What the empty field means, so the swatch can show the colour
            -- the corona will really be rather than nothing at all.
            settingsCoronaColour = settingsCoronaColour,
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
            question = tostring(card.question or ""),
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
        settingsRejections[rejectionKey(key, payload.mapId)] = nil
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
    -- Teleport is the one row action that leaves F7. Capture the identity
    -- first, then restore the camera/cursor before the server moves the player.
    closePanel()
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
-- the row and not in Settings. Only a row the store holds has them: an offer
-- has nothing to write them on yet.
--
-- Every field is optional and each is passed on exactly as the page sent it.
-- The three answers are not the same: absent means the player did not touch it,
-- `false` means they emptied it and the entity follows Settings again, and a
-- value means they set one. Coercing `false` to `nil` here is how "clear this"
-- would silently become "leave it alone".
function actions.setEntityRadius(payload)
    local entry = selectedEntry()
    if not entry or entry.adoptable == true then
        return
    end
    triggerServerEvent(
        ENTITY_METADATA_REQUEST_EVENT,
        resourceRoot,
        entry.mapEntity.mapId,
        entry.mapEntity.entityId,
        {
            radius = tonumber(payload.radius),
            showCorona = payload.showCorona,
            coronaColour = payload.coronaColour,
            coronaOpacity = payload.coronaOpacity,
        }
    )
end

--- Point the camera at a row without moving the Study Player.
-- The identity arrives with the double-click itself so two click events and a
-- browser/Lua round-trip cannot leave the camera acting on the previous row.
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
    if not entry or entry.adoptable == true or type(payload.name) ~= "string" then
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
    serverMaps = type(values.maps) == "table" and values.maps or {}
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

addEvent(SETTINGS_REJECTED_EVENT, true)
addEventHandler(SETTINGS_REJECTED_EVENT, resourceRoot, function(key, reason, mapId)
    if source ~= resourceRoot or type(key) ~= "string" then
        return
    end
    -- The server refused after the fact, so the reason lands on the row that
    -- earned it rather than in the chat, where it would scroll away. For the
    -- one per-map setting that means the row of the map it was about.
    settingsRejections[rejectionKey(key, mapId)] =
        reason or "settings.error.not_saved"
    settingsPending[key] = nil
    push()
end)

local entityRefreshTimer = nil

local function scheduleEntityRefresh()
    if not authorized or not isPanelOpen() then
        return
    end
    if isTimer(entityRefreshTimer) then
        killTimer(entityRefreshTimer)
    end
    entityRefreshTimer = setTimer(function()
        entityRefreshTimer = nil
        if authorized and isPanelOpen() then
            triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
        end
    end, 100, 1)
end

--- Would the Map Entity list ever have a row for this element?
--
-- A marker is one of the types a card can hang on, so a marker appearing is
-- normally a reason to re-read the list. ANKIGTA's own coronas are markers
-- too, and they appear and disappear as the player walks around and as they
-- change a colour -- each one asking the server to rebuild the whole snapshot,
-- which produces the next snapshot, which moves a corona. The marks say which
-- elements are theirs so that loop cannot start.
local function couldBeARow(element)
    if not PANEL_ENTITY_TYPE[getElementType(element)] then
        return false
    end
    if ANKIGTA.ZoneMarks and ANKIGTA.ZoneMarks.owns(element) then
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
    if ANKIGTA.ZoneMarks and ANKIGTA.ZoneMarks.owns(source) then
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
    -- Asked for once on the way in, not only when F7 opens. A corona is worn
    -- by the entity whether or not anyone is looking at the list, and the
    -- snapshot is where the client learns which entities wear one; without
    -- this, they would appear the first time the panel was opened and a player
    -- who never opened it would see none.
    triggerServerEvent(F7_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStart", resourceRoot, function()
    triggerServerEvent(AUTHORIZATION_REQUEST_EVENT, resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, closePanel)

--- Which Map Entity the player has selected, if any.
--
-- The panel owns the selection -- the page is a view -- so whatever draws on
-- the world asks here rather than being told, and there is no second copy to
-- disagree with this one. It outlives the panel being closed, which is what
-- lets `Draw radius` keep drawing the zone the player was just setting up.
local function panelSelection()
    return selectedMapId or false, selectedEntityId or false
end

--- Every Map Entity in the last snapshot, and how it asks to be marked.
--
-- Off the snapshot rather than off `entityRows`, because that one applies the
-- filter the player typed: a row hidden from a list is still a thing standing
-- in the world, and hiding it must not put its corona out.
local function panelMarkable()
    local marks = {}
    for _, entry in ipairs(lastSnapshot and lastSnapshot.entities or {}) do
        local mapEntity = entry.mapEntity
        local metadata = entry.metadata or {}
        marks[#marks + 1] = {
            mapId = mapEntity.mapId,
            entityId = mapEntity.entityId,
            radius = tonumber(metadata.radius) or 3,
            showCorona = metadata.showCorona == true,
            coronaColour = metadata.coronaColour or false,
            coronaOpacity = tonumber(metadata.coronaOpacity) or false,
        }
    end
    return marks
end

ANKIGTA.Panel = {
    isOpen = isPanelOpen,
    close = closePanel,
    rows = entityRows,
    matching = panelMatching,
    selection = panelSelection,
    markable = panelMarkable,
    runtimeElements = runtimeElementsFor,
}

local PICK_ENTITY_START_EVENT = "ankigta:pickEntityStart"
local PICK_ENTITY_REQUEST_EVENT = "ankigta:pickEntity"
local PICK_ENTITY_RESULT_EVENT = "ankigta:pickEntityResult"
local PICK_ENTITY_FINISHED_EVENT = "ankigta:pickEntityFinished"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"

local SUPPORTED_ENTITY_TYPES = {
    ["object"] = true,
    ["vehicle"] = true,
    ["ped"] = true,
    -- Placed to mean "here", which is what a card wants to hang on.
    ["marker"] = true,
}

local MOVEMENT_AND_LOOK_CONTROLS = {
    "forwards",
    "backwards",
    "left",
    "right",
    "jump",
    "sprint",
    "crouch",
    "walk",
    "aim_weapon",
    "look_behind",
    "vehicle_look_left",
    "vehicle_look_right",
}

local BLOCKED_CONTROLS = {
    "fire",
    "vehicle_fire",
    "vehicle_secondary_fire",
    "enter_exit",
    "action",
    "next_weapon",
    "previous_weapon",
}

local active = false
local awaitingResponse = false
local purpose = "pick"
local previousControls = {}

local function captureInputState()
    previousControls = {}
    for _, control in ipairs(MOVEMENT_AND_LOOK_CONTROLS) do
        previousControls[control] = isControlEnabled(control)
        toggleControl(control, true)
    end
    for _, control in ipairs(BLOCKED_CONTROLS) do
        previousControls[control] = isControlEnabled(control)
        toggleControl(control, false)
    end
    -- The cursor *is* the aim. `onClientClick` raycasts from the camera
    -- through the cursor and hands back what it hit, so the player points at
    -- the object rather than turning the whole camera onto it -- which is the
    -- only way this is usable outside the Map Editor, in freeroam.
    --
    -- It is also load-bearing: MTA raises `onClientClick` from the cursor
    -- position, so with the cursor hidden the click never arrived at all.
    -- Asked for, not remembered. MTA counts cursor requests across resources,
    -- so `isCursorShowing()` answers for everyone and giving that answer back
    -- would leave this resource still asking forever.
    showCursor(true)
end

local function restoreInputState()
    for control, enabled in pairs(previousControls) do
        toggleControl(control, enabled == true)
    end
    previousControls = {}
    showCursor(false)
end

local function nonEmptyData(element, key)
    local value = getElementData(element, key)
    return type(value) == "string" and value ~= ""
end

--- May the player point at this, and is it already ours?
--
-- The gate is a durable name, and there are two kinds of one. `me:ID` is what
-- the stock Map Editor writes, but only while the map is open in it. The `id`
-- attribute of a `.map` file -- `getElementID` -- is there whenever the map is
-- loaded at all, which is the case for a player merely spawned in freeroam.
-- Requiring the editor's one was what made a map full of objects offer none.
--
-- An `ankigtaEntityId` on top means we have already adopted it; without one
-- the object is merely *adoptable*, and saying so is the point.
--
-- An object a script spawned has neither name and stays out: nothing would
-- find the same object again after a restart for the card to still mean.
local function isEligibleTarget(element)
    if not isElement(element) then
        return false, "target_not_an_element"
    end
    if not isElementStreamedIn(element) then
        return false, "target_not_streamed"
    end
    local entityType = getElementType(element)
    if not SUPPORTED_ENTITY_TYPES[entityType] then
        return false, "target_type_not_supported"
    end
    -- Every element of a supported type can be named: by its `.map` id where
    -- it has one, and by where it stands where it has not. So the question is
    -- no longer whether it may be taken but whether it already has been.
    return true, nonEmptyData(element, "ankigtaEntityId") and "adopted"
        or "adoptable"
end

function isPickEntityActive()
    return active
end

--- What the player clicked on, or why nothing was taken.
--
-- MTA has already done the work: it casts from the camera through the cursor
-- and hands the hit element to `onClientClick`. Casting again from our own
-- guess at the aim would be a second answer to a question already answered,
-- and the two would disagree the moment the cursor left the screen centre.
local function targetUnderCursor(clickedElement)
    if not isElement(clickedElement) then
        return false, "target_not_visible"
    end
    local eligible, kind = isEligibleTarget(clickedElement)
    if not eligible then
        return false, kind
    end
    return clickedElement, kind
end

local function finishPickEntity(success, reason, mapId, entityId, element)
    if not active then
        return
    end
    active = false
    awaitingResponse = false
    unbindKey("escape", "down", cancelPickEntity)
    restoreInputState()
    triggerEvent(
        PICK_ENTITY_FINISHED_EVENT,
        resourceRoot,
        success == true,
        reason,
        mapId,
        entityId,
        purpose,
        -- Only an object nobody has adopted yet travels as an element: it has
        -- no identity to be named by until a card gives it one.
        element or false
    )
end

function cancelPickEntity()
    finishPickEntity(false, "cancelled")
end

function handlePickEntityError(reason)
    finishPickEntity(false, reason or "pick_failed")
end

local function submitPickEntity(clickedElement)
    if not active or awaitingResponse then
        return
    end
    local target, reason = targetUnderCursor(clickedElement)
    if not target then
        handlePickEntityError(reason)
        return
    end
    awaitingResponse = true
    triggerServerEvent(
        PICK_ENTITY_REQUEST_EVENT,
        resourceRoot,
        target,
        purpose
    )
end

-- `onClientClick(button, state, screenX, screenY, worldX, worldY, worldZ,
-- clickedElement)`. The last one is what the cursor was over, or `false`.
local function clickPickEntity(
    button, state, _screenX, _screenY, _worldX, _worldY, _worldZ, clickedElement
)
    if not active or button ~= "left" or state ~= "down" then
        return
    end
    cancelEvent()
    submitPickEntity(clickedElement)
end

function startPickEntity(mode)
    if active then
        return false, "pick_entity_active"
    end
    purpose = mode == "relink" and "relink" or "pick"
    active = true
    awaitingResponse = false
    captureInputState()
    bindKey("escape", "down", cancelPickEntity)
    return true
end

-- Local only: the panel asks for this on the same side. Registered rather than
-- merely handled, because `triggerEvent` on a name MTA does not know returns
-- false and calls nothing -- silently. Without this the panel closed itself to
-- get out of the way and then nothing happened at all.
addEvent(PICK_ENTITY_START_EVENT, false)
addEventHandler(PICK_ENTITY_START_EVENT, resourceRoot, function(mode)
    startPickEntity(mode)
end)

addEvent(PICK_ENTITY_RESULT_EVENT, true)
addEventHandler(PICK_ENTITY_RESULT_EVENT, resourceRoot, function(
    success,
    reason,
    mapId,
    entityId,
    _purpose,
    element
)
    if success == true then
        finishPickEntity(true, reason, mapId, entityId, element)
    else
        handlePickEntityError(reason)
    end
end)

addEvent(AUTHORIZATION_EVENT, true)
addEventHandler(AUTHORIZATION_EVENT, resourceRoot, function(authorized)
    if authorized ~= true and active then
        finishPickEntity(false, "authorization_revoked")
    end
end)

addEventHandler("onClientClick", root, clickPickEntity)
addEventHandler("onClientResourceStop", resourceRoot, function()
    if active then
        finishPickEntity(false, "resource_stop")
    end
end)

local PICK_ENTITY_START_EVENT = "ankigta:pickEntityStart"
local PICK_ENTITY_REQUEST_EVENT = "ankigta:pickEntity"
local PICK_ENTITY_RESULT_EVENT = "ankigta:pickEntityResult"
local PICK_ENTITY_FINISHED_EVENT = "ankigta:pickEntityFinished"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"

local SUPPORTED_ENTITY_TYPES = {
    ["object"] = true,
    ["vehicle"] = true,
    ["ped"] = true,
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
local previousCursor = false

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
    previousCursor = isCursorShowing()
    showCursor(false)
end

local function restoreInputState()
    for control, enabled in pairs(previousControls) do
        toggleControl(control, enabled == true)
    end
    previousControls = {}
    showCursor(previousCursor)
end

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
    if not getElementData(element, "ankigtaEntityId")
        or getElementData(element, "ankigtaEntityId") == ""
    then
        return false, "target_not_managed"
    end
    if not getElementData(element, "me:ID")
        or getElementData(element, "me:ID") == ""
    then
        return false, "target_not_managed"
    end
    return true
end

function isPickEntityActive()
    return active
end

local function pickRaycastTarget()
    local cameraX, cameraY, cameraZ, targetX, targetY, targetZ =
        getCameraMatrix()
    if not cameraX or not targetX then
        return false, "camera_unavailable"
    end

    local hit, _, _, _, hitElement = processLineOfSight(
        cameraX,
        cameraY,
        cameraZ,
        targetX,
        targetY,
        targetZ,
        true,
        true,
        true,
        true,
        true,
        false,
        false,
        false,
        localPlayer
    )
    if not hit or not isElement(hitElement) then
        return false, "target_not_visible"
    end
    local eligible, reason = isEligibleTarget(hitElement)
    if not eligible then
        return false, reason
    end
    return hitElement
end

local function finishPickEntity(success, reason, mapId, entityId)
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
        purpose
    )
end

function cancelPickEntity()
    finishPickEntity(false, "cancelled")
end

function handlePickEntityError(reason)
    finishPickEntity(false, reason or "pick_failed")
end

local function submitPickEntity()
    if not active or awaitingResponse then
        return
    end
    local target, reason = pickRaycastTarget()
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

local function clickPickEntity(button, state)
    if not active or button ~= "left" or state ~= "down" then
        return
    end
    cancelEvent()
    submitPickEntity()
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
    entityId
)
    if success == true then
        finishPickEntity(true, reason, mapId, entityId)
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

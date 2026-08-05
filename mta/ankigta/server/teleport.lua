ANKIGTA = ANKIGTA or {}

-- Teleport and Runtime Instance lifecycle.
--
-- ANKIGTA observes a Runtime Instance; it never owns one. Respawn belongs to
-- the map or the resource that created the entity (ADR 0004), so nothing here
-- recreates an object, vehicle, ped or marker. When one reappears with the same
-- persistent identity, its Spatial Link simply becomes usable again.
--
-- Teleport goes straight to the target (ADR 0005): no safe-landing search, and
-- no refusal over water, empty space, collision or a vehicle interior. Those
-- are places a player may legitimately want to stand.

local Teleport = {}

--- Is this Runtime Instance usable as a teleport target right now?
function Teleport.runtimeAvailable(element)
    return isElement(element) == true
end

--- Find the live instance carrying a Map Entity's persistent identity.
--
-- This is what makes ADR 0004 work: ANKIGTA never recreates anything, so a
-- destroyed entity simply has no instance until the map or the owning resource
-- brings one back. Because the lookup is by persistent ID rather than by a
-- remembered element, the replacement is recognised as the same Map Entity and
-- its Spatial Link becomes usable again.
--
-- The player is who the answer is for. The stock Map Editor works in a
-- dimension of its own while the same map may be play-testing in the ordinary
-- world, so one authored entity is standing in two places; teleport has to
-- land next to the copy actually in front of the player, not next to whichever
-- copy the walk reached first.
function Teleport.findRuntimeInstance(mapId, entityId, player)
    return ANKIGTA.World.runtimeInstance(mapId, entityId, player)
end

local function authoredTarget(record)
    return {
        x = tonumber(record.authoredX),
        y = tonumber(record.authoredY),
        z = tonumber(record.authoredZ),
        interior = tonumber(record.interior) or 0,
        dimension = tonumber(record.dimension) or 0,
        source = "authored",
    }
end

--- Resolve one consistent teleport snapshot.
--
-- Position, interior and dimension are taken from a single source. Mixing a
-- live position with an authored interior would put the player somewhere that
-- exists in neither, which is why any doubt about the instance discards the
-- whole live reading rather than part of it.
function Teleport.resolveTarget(record, element)
    if type(record) ~= "table" then
        return false, "invalid_map_entity"
    end

    if not Teleport.runtimeAvailable(element) then
        return authoredTarget(record)
    end

    local x, y, z = getElementPosition(element)
    local interior = getElementInterior(element)
    local dimension = getElementDimension(element)

    -- Re-check afterwards: the instance may have been destroyed between the
    -- reads above, which would leave us holding half a snapshot.
    if not Teleport.runtimeAvailable(element)
        or type(x) ~= "number"
        or type(y) ~= "number"
        or type(z) ~= "number"
        or type(interior) ~= "number"
        or type(dimension) ~= "number"
    then
        return authoredTarget(record)
    end

    return {
        x = x,
        y = y,
        z = z,
        interior = interior,
        dimension = dimension,
        source = "runtime",
    }
end

local function placeElement(element, target)
    if not isElement(element) then
        return false
    end
    setElementInterior(element, target.interior)
    setElementDimension(element, target.dimension)
    setElementPosition(element, target.x, target.y, target.z)
    return true
end

--- Move the player, or their whole vehicle, to a resolved target.
function Teleport.moveTo(player, target)
    if not isElement(player) then
        return false, "invalid_player"
    end
    if type(target) ~= "table"
        or type(target.x) ~= "number"
        or type(target.y) ~= "number"
        or type(target.z) ~= "number"
    then
        return false, "invalid_target"
    end

    local vehicle = getPedOccupiedVehicle(player)
    if not isElement(vehicle) then
        return placeElement(player, target)
    end

    placeElement(vehicle, target)

    -- MTA is asymmetric here, and the asymmetry is a trap.
    -- `CStaticFunctionDefinitions::SetElementDimension` loops the vehicle's
    -- seats and sets each occupant's dimension; `SetElementInterior` does not.
    -- So a passenger carried into interior 3 would otherwise stay in interior
    -- 0 and drop out of the world. Dimension is set again here only so this
    -- does not silently depend on that propagation continuing to exist.
    -- `pairs`, not `ipairs`: MTA keys occupants by seat starting at 0 and
    -- omits empty seats (CLuaVehicleDefs::GetVehicleOccupants). `ipairs` would
    -- begin at 1 -- skipping the driver, who is the teleporting player -- and
    -- stop at the first empty seat.
    local occupants = getVehicleOccupants(vehicle)
    if type(occupants) == "table" then
        for _, occupant in pairs(occupants) do
            if isElement(occupant) and occupant ~= vehicle then
                setElementInterior(occupant, target.interior)
                setElementDimension(occupant, target.dimension)
            end
        end
    end
    return true
end

--- Teleport the player to a Map Entity, resolving its instance first.
function Teleport.toMapEntity(player, record)
    if type(record) ~= "table" then
        return false, "invalid_map_entity"
    end
    local element = Teleport.findRuntimeInstance(
        record.mapId,
        record.entityId,
        player
    )
    local target = Teleport.resolveTarget(record, element)
    if not target then
        return false, "invalid_map_entity"
    end
    local moved, reason = Teleport.moveTo(player, target)
    if not moved then
        return false, reason
    end
    -- The target travels back with the answer. Inside the stock Map Editor the
    -- camera owns where the player is -- `editor_main/client/attachplayer.lua`
    -- does `setElementPosition(localPlayer, getCameraMatrix())` on every frame
    -- -- so moving the player alone is undone before it is ever drawn. Only
    -- the client can move that camera, and it needs somewhere to move it to.
    return true, target.source, target
end

ANKIGTA.Teleport = Teleport

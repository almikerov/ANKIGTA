ANKIGTA = ANKIGTA or {}

-- Which candidate is "the nearest one".
--
-- Distance alone is a partial order: two Map Entity at exactly the same
-- distance leave the answer to whichever of them the server's snapshot happened
-- to put first. On a reference-sized world that is an ordinary occurrence, not a
-- corner case, and it turns "why did that one open" into a report nobody can
-- reproduce.
--
-- So the order is completed with the Map Entity's own identity -- map id first,
-- then entity id. Both are persistent (ADR 0011), so the same world produces the
-- same choice on every run, on every machine, whatever order the rows arrive in.

local Nearest = {}

local function distanceSquared(a, b)
    local dx = a.x - b.x
    local dy = a.y - b.y
    local dz = a.z - b.z
    return dx * dx + dy * dy + dz * dz
end

Nearest.distanceSquared = distanceSquared

--- The pair the tie is broken on, as strings, so `<` means the same thing for
--- a numeric editor id and a generated one.
local function identity(candidate)
    return tostring(candidate.mapId), tostring(candidate.entityId)
end

--- Does `candidate` at `distance` beat the running best?
--
-- Exposed because the answer is the specification: a test can ask it directly
-- rather than inferring it from whatever the caller did with the winner.
function Nearest.beats(candidate, distance, best, bestDistance)
    if best == nil or best == false or bestDistance == nil then
        return true
    end
    if distance ~= bestDistance then
        return distance < bestDistance
    end
    local mapId, entityId = identity(candidate)
    local bestMapId, bestEntityId = identity(best)
    if mapId ~= bestMapId then
        return mapId < bestMapId
    end
    return entityId < bestEntityId
end

--- The nearest accepted candidate, and its squared distance.
--
-- `accept` decides eligibility; it is the caller's, because an Activation Zone
-- and a Next Card Indicator admit different things. The ordering is not the
-- caller's, because two modules disagreeing about which entity is nearest is
-- exactly the drift this module exists to prevent.
function Nearest.select(origin, candidates, accept)
    local best, bestDistance = false, nil
    for _, candidate in ipairs(candidates or {}) do
        if accept == nil or accept(candidate) then
            local distance = distanceSquared(origin, candidate)
            if Nearest.beats(candidate, distance, best, bestDistance) then
                best, bestDistance = candidate, distance
            end
        end
    end
    return best, bestDistance
end

ANKIGTA.Nearest = Nearest

ANKIGTA = ANKIGTA or {}

-- The Map Entity types every runtime module may persist and resolve.
-- The database keeps its own CHECK constraint, verified by migration tests;
-- client and server modules share this table so their scans cannot drift.
local order = {"object", "vehicle", "ped", "marker"}
local supported = {}
for _, kind in ipairs(order) do
    supported[kind] = true
end

ANKIGTA.EntityTypes = {
    order = order,
    supported = supported,
}

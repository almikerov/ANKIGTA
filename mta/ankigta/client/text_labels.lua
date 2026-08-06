ANKIGTA = ANKIGTA or {}

-- Drawing the Text Labels the server resolved (ADR 0029).
--
-- This side decides nothing about what a label says. The server owns the
-- Spatial Links, the cached words and the settings, and sends finished lines;
-- what only this side can know is where each Map Entity is standing right now
-- and which of them are near enough to read. So this module answers exactly
-- two questions -- which labels are in range, and which of those are drawn
-- when there are too many -- and hands the answer to the one door everything
-- ANKIGTA draws goes through.
--
-- ## Not a second answer about distance
--
-- `client/world_marks.lua` stops everything ANKIGTA draws at 150 metres from
-- the camera. `Show text` has a distance of its own, which is a smaller number
-- chosen *under* that one rather than instead of it: this module drops what is
-- beyond the setting, and the door drops what is beyond the ceiling. A setting
-- raised past the ceiling would change nothing, which is why the schema will
-- not accept one.
--
-- ## No speed gate
--
-- The Activation Zone has one because opening a card while driving is a card
-- you cannot read and did not ask for. A label covers nothing and demands
-- nothing, and reading one while driving past is the point (ADR 0029).

local TEXT_LABELS_EVENT = "ankigta:textLabels"

--- How large the text is drawn at the near and far ends of the distance
--- setting, before the size setting multiplies it.
--
-- Perspective rather than a constant: a label the same size at forty metres as
-- at two reads as a HUD element pasted over the world rather than as something
-- hanging on that object over there.
local NEAR_SCALE = 1.5
local FAR_SCALE = 0.55

local Display = {
    --- What the server last said the world is showing.
    labels = {},
    --- The same, by Map Entity, so the key prompt can ask about one.
    byEntity = {},
    --- How far a label carries, from the global setting.
    distance = false,
    --- What the last frame drew, and how many it had to leave out, so a report
    --- can be read without looking at a screen.
    drawn = {},
    dropped = 0,
}

local function schema()
    return ANKIGTA.Settings
end

local function marks()
    return ANKIGTA.WorldMarks
end

--- How far a label carries right now.
--
-- The stored setting, or the shipped default until the first one arrives: a
-- client that heard no setting yet must not draw every label in the world.
function Display.maxDistance()
    return tonumber(Display.distance)
        or tonumber(schema() and schema().default("textLabelDistance"))
        or 25
end

--- How many labels are drawn at once.
--
-- The number is the shared module's, so the side that applies the cap and the
-- side that describes it cannot disagree; applying it is this side's, because
-- only this side knows which labels are near.
local function maximumDrawn()
    return ANKIGTA.TextLabel.MAX_DRAWN
end

local function entityKey(mapId, entityId)
    return tostring(mapId) .. "/" .. tostring(entityId)
end

--- Where the reading is being done from.
--
-- The camera, not the player, for the reason the draw-distance rule measures
-- from there: the panel flies the camera to a row while the player stays where
-- they were, and it does that *in order to look at* what is drawn on it.
local function viewpoint()
    local x, y, z = getCameraMatrix()
    if type(x) ~= "number" then
        return false
    end
    return {
        x = x,
        y = y,
        z = z,
        interior = getCameraInterior() or 0,
        -- No camera dimension exists; a dimension is a partition of the world
        -- the player is in, and the camera is always in theirs.
        dimension = getElementDimension(localPlayer) or 0,
    }
end

--- Which labels are near enough to read, nearest first, and how many are not.
--
-- Pure, given a viewpoint and a way to find each entity: what it decides is
-- the interesting part, and it is decided without a frame being drawn.
--
-- The order is `shared/nearest.lua`'s, the same one the Activation Zone and
-- the Next Card Indicator use: two labels at the same distance resolve on
-- their Map Entity identity rather than on the order the server's snapshot
-- happened to put them in, so the same world drops the same ones every time.
function Display.plan(observer, labels, maxDistance, positionOf)
    local nearest = ANKIGTA.Nearest
    local inRange = {}
    if type(observer) ~= "table" then
        return inRange, 0
    end
    for _, label in ipairs(type(labels) == "table" and labels or {}) do
        local spot = positionOf(label)
        if spot
            and spot.interior == observer.interior
            and spot.dimension == observer.dimension
        then
            local squared = nearest.withinRadius(observer, spot, maxDistance)
            if squared ~= nil then
                inRange[#inRange + 1] = {
                    label = label,
                    mapId = label.mapId,
                    entityId = label.entityId,
                    x = spot.x,
                    y = spot.y,
                    z = spot.z,
                    distance = math.sqrt(squared),
                    distanceSquared = squared,
                }
            end
        end
    end

    table.sort(inRange, function(left, right)
        return nearest.beats(
            left,
            left.distanceSquared,
            right,
            right.distanceSquared
        )
    end)

    local limit = maximumDrawn()
    local dropped = 0
    if #inRange > limit then
        dropped = #inRange - limit
        for index = #inRange, limit + 1, -1 do
            inRange[index] = nil
        end
    end
    return inRange, dropped
end

--- The size one label is drawn at, from its own setting and how far away it is.
function Display.scaleFor(entry, maxDistance)
    local size = tonumber(entry.label.size) or 1
    local reach = math.max(tonumber(maxDistance) or 1, 1)
    local nearness = 1 - math.min(1, entry.distance / reach)
    return size * (FAR_SCALE + (NEAR_SCALE - FAR_SCALE) * nearness)
end

--- Where the Map Entity carrying this label is standing right now.
--
-- Off the live element, found by the module that already walked the world for
-- it. A position sent from the server would be the authored one wearing the
-- current one's name, and a second walk here would be the world twice.
local function positionOf(label)
    local element = marks() and marks().elementFor(label.mapId, label.entityId)
    if not element then
        return false
    end
    local x, y, z = getElementPosition(element)
    if type(x) ~= "number" then
        return false
    end
    return {
        x = x,
        y = y,
        z = z,
        interior = getElementInterior(element) or 0,
        dimension = getElementDimension(element) or 0,
    }
end

--- Say how many labels were left undrawn, where the counters already are.
--
-- A cap applied quietly reads as "that is all there is", and a player standing
-- in a room they filled with cards would conclude the rest never got linked.
function Display.renderDroppedNotice(dropped)
    if dropped <= 0 or not ANKIGTA.Layout or not ANKIGTA.Locale then
        return false
    end
    local x, y, width, height, scale = ANKIGTA.Layout.rect("hud")
    dxDrawText(
        ANKIGTA.Locale.format("textLabel.capped", dropped),
        x,
        y + height,
        x + width,
        y + height * 2,
        tocolor(235, 200, 120, 220),
        scale,
        "default-bold",
        "right"
    )
    return true
end

function Display.render()
    if #Display.labels == 0 or not marks() then
        -- An incremental reload can hand this client one script ahead of
        -- another, and a frame drawn in that window has no door to draw
        -- through. Nothing rather than an error every frame until it does.
        return false
    end
    local observer = viewpoint()
    local maxDistance = Display.maxDistance()
    local entries, dropped = Display.plan(
        observer,
        Display.labels,
        maxDistance,
        positionOf
    )
    Display.drawn = entries
    Display.dropped = dropped

    for _, entry in ipairs(entries) do
        marks().label(
            entry.x,
            entry.y,
            entry.z,
            entry.label.lines,
            entry.label.color,
            Display.scaleFor(entry, maxDistance)
        )
    end

    Display.renderDroppedNotice(dropped)
    return true
end

--- Does this Map Entity carry a Text Label?
--
-- Asked by `client/world_marks.lua` before it draws ticket 05's `<KEY> to
-- view`: one entity shows one thing, and an object that says what its card
-- says is not also offering to open it.
--
-- Membership in the set the server sent, not "is one on screen this frame".
-- The prompt is decided at the polling cadence and labels are drawn per frame,
-- so a frame-by-frame answer would let both appear for a quarter of a second
-- at a time. The entity that has a label is the one that shows text.
function Display.showsLabel(mapId, entityId)
    return Display.byEntity[entityKey(mapId, entityId)] ~= nil
end

--- Every Map Entity carrying a label, for whoever has to find the object.
function Display.labelled()
    local wanted = {}
    for _, label in ipairs(Display.labels) do
        wanted[#wanted + 1] = {
            mapId = label.mapId,
            entityId = label.entityId,
        }
    end
    return wanted
end

--- What is being shown right now, for a report that cannot look at the screen.
function Display.diagnostics()
    return {
        labels = #Display.labels,
        drawn = #Display.drawn,
        dropped = Display.dropped,
        distance = Display.maxDistance(),
    }
end

--- Adopt a label set the server sent.
--
-- An empty set is not nothing happening: it is how the labels go away on the
-- way out of `Show text`, so it is adopted like any other.
function Display.setLabels(labels, distance)
    local accepted, byEntity = {}, {}
    for _, label in ipairs(type(labels) == "table" and labels or {}) do
        if type(label) == "table"
            and type(label.mapId) == "string"
            and type(label.entityId) == "string"
            and type(label.lines) == "table"
            and #label.lines > 0
        then
            accepted[#accepted + 1] = label
            byEntity[entityKey(label.mapId, label.entityId)] = label
        end
    end
    Display.labels = accepted
    Display.byEntity = byEntity
    if distance ~= nil then
        Display.distance = tonumber(distance) or Display.distance
    end
    if #accepted == 0 then
        Display.drawn = {}
        Display.dropped = 0
    end
    return #accepted
end

addEvent(TEXT_LABELS_EVENT, true)
addEventHandler(TEXT_LABELS_EVENT, resourceRoot, function(labels, distance)
    Display.setLabels(labels, distance)
end)

addEventHandler("onClientRender", root, function()
    Display.render()
end)

if ANKIGTA.WorldMarks then
    -- Two registrations, both of them the whole of what this module asks of
    -- the drawing module: find these objects for me, and hold the offer back
    -- on the ones I have taken.
    ANKIGTA.WorldMarks.alsoDrawOn(Display.labelled)
    ANKIGTA.WorldMarks.holdPromptBackWhen(Display.showsLabel)
end

-- Named for what it does rather than for what it draws. `ANKIGTA.TextLabels`
-- is the server module that decides what each label says; this one only puts
-- the answer on the screen, and two modules under one name would read as one.
ANKIGTA.TextLabelDisplay = Display

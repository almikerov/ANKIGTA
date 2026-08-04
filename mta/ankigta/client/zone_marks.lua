ANKIGTA = ANKIGTA or {}

-- What ANKIGTA draws onto the world, so a row in the panel can be found in it.
--
-- Three marks, and they answer three different questions:
--
-- - The **outline** answers "which thing is this row?". It is drawn around the
--   selected row's Runtime Instance for as long as F7 is open, and is not
--   something to switch on: a row you cannot find is a row you cannot judge,
--   and this is the cheapest form of the answer that works while the player is
--   still deciding. Teleport and camera focus answer the same question by
--   taking the player there, which is no help while they are choosing.
--
-- - The **zone** answers "how close would I have to stand?". `Draw radius` is
--   a way of looking rather than a property of anything looked at, so it is a
--   client setting and it draws the *selected* row's Activation Zone. It
--   outlives the panel closing, which is the point: the player sizes a zone,
--   closes F7 and walks the edge of it.
--
-- - A **corona** answers "where are the things I have set up?", from across a
--   street and with nothing open. `Show corona` is a property of the entity,
--   so it is stored on the entity and every player sees it; its colour and
--   opacity follow Settings unless the entity says otherwise.
--
-- The first two are drawn, the third is a marker element. That is not an
-- inconsistency: a drawn thing exists while something is drawing it, which is
-- exactly right for a mark that follows the selection, and exactly wrong for
-- one that has to be there whether or not this module is doing anything.
--
-- Nothing here decides anything about study. A mark is a mark; the Activation
-- Zone it depicts is `client/activation.lua`'s, and drawing one neither
-- creates nor resizes it.

local POLL_INTERVAL_MS = 250

--- How many segments a drawn circle is made of.
--
-- A zone sphere is three of them. Sixteen is the point where the corners stop
-- reading as corners at the radii a zone actually has -- the default is three
-- metres and the largest allowed is fifty.
local CIRCLE_SEGMENTS = 16

--- `dxDrawLine3D` rather than `dxDrawWiredSphere`, which would be one call.
--
-- The resource declares a minimum MTA of 1.6.0-9.24124.0 and the wired-sphere
-- primitive is newer than the source tree that could be read to date it. A
-- primitive that has been there since 1.0 draws the same sphere; what it costs
-- is arithmetic this file can afford, and what it saves is a client that
-- silently draws nothing on the version the resource says it supports.
local ZONE_ALPHA = 90
local OUTLINE_ALPHA = 220
local OUTLINE_COLOUR = {120, 200, 255}

--- What a Map Entity's outline surrounds when its model will not say.
local FALLBACK_EXTENT = 1

local ZoneMarks = {
    --- The client's way of looking, and the world's default corona.
    settings = {
        drawRadius = false,
        coronaColour = false,
        coronaOpacity = false,
    },
    --- Runtime Instances as of the last look at the world, by Map Entity.
    resolved = {},
    --- The corona each Map Entity is wearing, and what it was made to look
    --- like, so an unchanged one is left alone rather than rebuilt.
    coronas = {},
    --- Every marker this module created, so the panel can tell ANKIGTA's own
    --- drawing apart from the world changing under it.
    owned = {},
    timer = false,
}

local function schema()
    return ANKIGTA.Settings
end

local function settingsDefault(key)
    return schema() and schema().default(key) or nil
end

ZoneMarks.settings.coronaColour = settingsDefault("coronaColour")
ZoneMarks.settings.coronaOpacity = settingsDefault("coronaOpacity")

local function markKey(mapId, entityId)
    return tostring(mapId) .. "/" .. tostring(entityId)
end

-- --- what to draw --------------------------------------------------------

--- What the marks should be right now.
--
-- Pure: what is standing in the world arrives in `marks` with `present`
-- already answered, and what the player has chosen arrives in `view`. Nothing
-- here reads an element, a setting or a clock, which is what makes the rules
-- checkable without a game running -- and the rules are the interesting part.
--
-- `view` is `{panelOpen, selectedMapId, selectedEntityId, drawRadius,
-- coronaColour, coronaOpacity}`; each entry of `marks` is `{mapId, entityId,
-- radius, showCorona, coronaColour, coronaOpacity, present}`.
function ZoneMarks.plan(view, marks)
    view = type(view) == "table" and view or {}
    local plan = {outline = false, zone = false, coronas = {}}
    local selectedMapId = view.selectedMapId
    local selectedEntityId = view.selectedEntityId

    for _, mark in ipairs(marks or {}) do
        -- A mark is drawn on a thing that is here. A Map Entity whose Runtime
        -- Instance is unstreamed or destroyed has nothing to draw one on --
        -- its record and its Spatial Link are untouched either way.
        if mark.present == true then
            local selected = selectedMapId ~= false
                and selectedMapId ~= nil
                and mark.mapId == selectedMapId
                and mark.entityId == selectedEntityId
            if selected and view.panelOpen == true then
                plan.outline = {mapId = mark.mapId, entityId = mark.entityId}
            end
            if selected and view.drawRadius == true then
                plan.zone = {
                    mapId = mark.mapId,
                    entityId = mark.entityId,
                    radius = tonumber(mark.radius) or 3,
                }
            end
            if mark.showCorona == true then
                -- One corona per entity, whatever else is true of it: this
                -- loop visits each Map Entity once, so being selected as well
                -- cannot produce a second.
                plan.coronas[#plan.coronas + 1] = {
                    mapId = mark.mapId,
                    entityId = mark.entityId,
                    radius = tonumber(mark.radius) or 3,
                    -- What the entity says, or what Settings says where the
                    -- entity says nothing. Resolved here rather than at the
                    -- marker, so "follows Settings" is one rule with one
                    -- reader instead of a fallback repeated per channel.
                    colour = mark.coronaColour or view.coronaColour,
                    opacity = mark.coronaOpacity ~= false
                        and mark.coronaOpacity ~= nil
                        and mark.coronaOpacity
                        or view.coronaOpacity,
                }
            end
        end
    end
    return plan
end

--- Is a corona being shown on this Map Entity right now?
--
-- The Next Card Indicator asks, so that where a corona already marks a spot it
-- emphasizes that instead of putting a second mark on top of it.
function ZoneMarks.showsCorona(mapId, entityId)
    return ZoneMarks.coronas[markKey(mapId, entityId)] ~= nil
end

--- True while this module is in the middle of creating a marker.
--
-- MTA raises `onClientElementCreate` from inside `createMarker`, so the panel
-- asks whether the new element is ours *before* `createMarker` has returned the
-- element there is to write down. Recording ownership afterwards is therefore
-- always too late, and the flag is what answers during that one window. It is
-- honest to answer yes to anything then: nothing else in this client creates an
-- element between those two statements.
local creating = false

--- Is this element one of ours?
--
-- A corona is a marker, and a marker is one of the types a card can hang on,
-- so without this the panel would treat every corona appearing as a Map Entity
-- appearing and re-read the whole list because of its own drawing -- which
-- produces the next snapshot, which is what decides where the coronas go.
function ZoneMarks.owns(element)
    if creating then
        return true
    end
    return element ~= nil and ZoneMarks.owned[element] == true
end

-- --- the client's way of looking -----------------------------------------

--- Take the settings that decide what is drawn.
--
-- Called by the client settings store the way the Next Card Indicator's mode
-- is, so a stored value is in force from the moment it is loaded rather than
-- from the next time something happens to ask.
function ZoneMarks.applySettings(values)
    if type(values) ~= "table" then
        return false, "invalid_settings"
    end
    if values.drawRadius ~= nil then
        ZoneMarks.settings.drawRadius = values.drawRadius == true
    end
    if values.coronaColour ~= nil then
        ZoneMarks.settings.coronaColour = values.coronaColour
    end
    if values.coronaOpacity ~= nil then
        ZoneMarks.settings.coronaOpacity = tonumber(values.coronaOpacity)
    end
    return true
end

-- --- reading the world ---------------------------------------------------

local function panel()
    return ANKIGTA.Panel
end

--- Every Map Entity that could be wearing a mark, and whether it is here.
--
-- The world is walked for the whole set at once and only every
-- `POLL_INTERVAL_MS`: the marks that follow a moving object do so by being
-- attached to it or by reading its position per frame, neither of which needs
-- the world searched again.
local function look()
    local marks = panel().markable()
    local selectedMapId, selectedEntityId = panel().selection()
    local wanted = {}
    for _, mark in ipairs(marks) do
        if mark.showCorona
            or (mark.mapId == selectedMapId
                and mark.entityId == selectedEntityId)
        then
            wanted[#wanted + 1] = {
                mapId = mark.mapId,
                entityId = mark.entityId,
            }
        end
    end
    -- Keyed by the pair the server knows a Map Entity by, which is the key the
    -- resolver answers in. Two loaded maps collide on entity id alone -- the
    -- stock Map Editor counts `object (1)` upwards per map -- so an id on its
    -- own would hang one map's corona on the other map's element.
    local elements = panel().runtimeElements(wanted)
    local resolved = {}
    for _, mark in ipairs(marks) do
        local key = markKey(mark.mapId, mark.entityId)
        local element = elements[key]
        if element ~= nil and isElement(element) then
            resolved[key] = element
            mark.present = true
        else
            mark.present = false
        end
    end
    ZoneMarks.resolved = resolved
    return marks
end

--- What the player has chosen, as the planner takes it.
local function view()
    local selectedMapId, selectedEntityId = panel().selection()
    return {
        panelOpen = panel().isOpen() == true,
        selectedMapId = selectedMapId,
        selectedEntityId = selectedEntityId,
        drawRadius = ZoneMarks.settings.drawRadius == true,
        coronaColour = ZoneMarks.settings.coronaColour,
        coronaOpacity = ZoneMarks.settings.coronaOpacity,
    }
end

local function elementFor(mark)
    if not mark then
        return false
    end
    local element = ZoneMarks.resolved[markKey(mark.mapId, mark.entityId)]
    if element == nil or not isElement(element) then
        return false
    end
    return element
end

-- --- coronas -------------------------------------------------------------

local function channels(colour, opacity)
    local red, green, blue = schema().colourChannels(colour)
    if red == nil then
        -- A stored colour the rule would have refused. Falling back to the
        -- shipped default rather than to black, which is a colour somebody
        -- could have meant and this never is.
        red, green, blue = schema().colourChannels(settingsDefault("coronaColour"))
    end
    local alpha = tonumber(opacity)
    if alpha == nil or alpha < 0 or alpha > 1 then
        alpha = tonumber(settingsDefault("coronaOpacity")) or 0.5
    end
    return red or 0, green or 0, blue or 0, math.floor(alpha * 255 + 0.5)
end

--- Is this corona already the one the plan asks for, and still in the world?
--
-- `isElement` first, because everything after it is about a marker that exists.
-- A marker destroyed by something other than this module still leaves its
-- record here, and a record that matches the plan is one this never replaces --
-- so the entity would go unmarked for as long as nothing about it changed.
local function unchanged(existing, wanted)
    return isElement(existing.marker)
        and existing.radius == wanted.radius
        and existing.colour == wanted.colour
        and existing.opacity == wanted.opacity
        and existing.element == wanted.element
end

local function destroyCorona(key)
    local existing = ZoneMarks.coronas[key]
    if not existing then
        return
    end
    -- Out of the plan first, so the `onClientElementDestroy` this raises finds
    -- nothing left to destroy and cannot recurse.
    ZoneMarks.coronas[key] = nil
    if isElement(existing.marker) then
        destroyElement(existing.marker)
    end
    -- Disowned last, for the same reason `creating` exists: the panel asks
    -- whether the vanishing element was ours from inside `destroyElement`, and
    -- a marker forgotten a statement earlier reads to it as a Map Entity
    -- leaving the world.
    ZoneMarks.owned[existing.marker] = nil
end

--- Bring the coronas in the world into line with the plan.
--
-- Reconciled rather than rebuilt: a corona that already looks right is left
-- exactly as it is. Destroying and recreating every marker four times a second
-- would flicker, and would also churn `onClientElementCreate` for a list that
-- has not changed.
local function reconcileCoronas(planned)
    local keep = {}
    for _, corona in ipairs(planned) do
        local key = markKey(corona.mapId, corona.entityId)
        local element = elementFor(corona)
        if element then
            keep[key] = true
            local wanted = {
                radius = corona.radius,
                colour = corona.colour,
                opacity = corona.opacity,
                element = element,
            }
            local existing = ZoneMarks.coronas[key]
            if existing and unchanged(existing, wanted) then
                -- Nothing to rebuild.
                -- Attached, so it is already wherever the thing has got to.
                -- Which world it is in does not come with the attachment
                -- though: an entity moved into another interior or dimension
                -- would leave its corona glowing in the one it left.
                if isElement(existing.marker) then
                    setElementInterior(
                        existing.marker, getElementInterior(element) or 0
                    )
                    setElementDimension(
                        existing.marker, getElementDimension(element) or 0
                    )
                end
            else
                destroyCorona(key)
                local x, y, z = getElementPosition(element)
                local red, green, blue, alpha =
                    channels(corona.colour, corona.opacity)
                -- Sized by the zone it stands for, so a corona is a thing the
                -- player can judge the radius by rather than a fixed dot.
                creating = true
                local marker = createMarker(
                    x, y, z, "corona", corona.radius, red, green, blue, alpha
                )
                creating = false
                if isElement(marker) then
                    setElementInterior(marker, getElementInterior(element) or 0)
                    setElementDimension(marker, getElementDimension(element) or 0)
                    -- Attached rather than moved: a corona on a vehicle has to
                    -- keep up with it, and following it in Lua would be this
                    -- module's own polling loop over the same elements MTA is
                    -- already moving.
                    attachElements(marker, element, 0, 0, 0)
                    wanted.marker = marker
                    ZoneMarks.coronas[key] = wanted
                    ZoneMarks.owned[marker] = true
                end
            end
        end
    end
    for key in pairs(ZoneMarks.coronas) do
        if not keep[key] then
            destroyCorona(key)
        end
    end
end

--- Take every corona out of the world.
function ZoneMarks.clear()
    for key in pairs(ZoneMarks.coronas) do
        destroyCorona(key)
    end
    ZoneMarks.resolved = {}
end

-- --- drawing -------------------------------------------------------------

--- One circle, in the plane two of the three axes span.
local function circle(x, y, z, radius, plane, red, green, blue, alpha)
    local colour = tocolor(red, green, blue, alpha)
    local previousA, previousB
    for step = 0, CIRCLE_SEGMENTS do
        local angle = step * 2 * math.pi / CIRCLE_SEGMENTS
        local a, b = math.cos(angle) * radius, math.sin(angle) * radius
        if previousA ~= nil then
            if plane == "xy" then
                dxDrawLine3D(
                    x + previousA, y + previousB, z,
                    x + a, y + b, z,
                    colour
                )
            elseif plane == "xz" then
                dxDrawLine3D(
                    x + previousA, y, z + previousB,
                    x + a, y, z + b,
                    colour
                )
            else
                dxDrawLine3D(
                    x, y + previousA, z + previousB,
                    x, y + a, z + b,
                    colour
                )
            end
        end
        previousA, previousB = a, b
    end
end

--- The Activation Zone, as the sphere it is.
--
-- Three great circles rather than a ring on the ground: the zone is a distance
-- in three dimensions, and a ring says nothing about the entity two storeys
-- above the one being set up.
-- Deliberately not the corona's colour. The two are separate ways of looking
-- and are on screen together; driving the wireframe from `Corona colour` would
-- make one setting quietly govern the other mark as well, and a player tuning
-- their coronas would find the zone they were sizing had changed with them.
local ZONE_COLOUR = OUTLINE_COLOUR

local function drawZone(element, radius)
    local x, y, z = getElementPosition(element)
    if type(x) ~= "number" then
        return
    end
    for _, plane in ipairs({"xy", "xz", "yz"}) do
        circle(
            x,
            y,
            z,
            radius,
            plane,
            ZONE_COLOUR[1],
            ZONE_COLOUR[2],
            ZONE_COLOUR[3],
            ZONE_ALPHA
        )
    end
end

--- The box a Map Entity stands in.
--
-- Axis-aligned, from the model's own bounding box. The entity's rotation is
-- deliberately not applied: turning the box needs the element matrix, and what
-- this has to answer is "which thing", which a box that contains the thing
-- answers whichever way the thing is facing.
local function drawOutline(element)
    local x, y, z = getElementPosition(element)
    if type(x) ~= "number" then
        return
    end
    local minX, minY, minZ, maxX, maxY, maxZ = getElementBoundingBox(element)
    if type(minX) ~= "number" then
        minX, minY, minZ = -FALLBACK_EXTENT, -FALLBACK_EXTENT, -FALLBACK_EXTENT
        maxX, maxY, maxZ = FALLBACK_EXTENT, FALLBACK_EXTENT, FALLBACK_EXTENT
    end
    local lowX, lowY, lowZ = x + minX, y + minY, z + minZ
    local highX, highY, highZ = x + maxX, y + maxY, z + maxZ
    local colour = tocolor(
        OUTLINE_COLOUR[1], OUTLINE_COLOUR[2], OUTLINE_COLOUR[3], OUTLINE_ALPHA
    )
    local corners = {
        {lowX, lowY, lowZ}, {highX, lowY, lowZ},
        {highX, highY, lowZ}, {lowX, highY, lowZ},
        {lowX, lowY, highZ}, {highX, lowY, highZ},
        {highX, highY, highZ}, {lowX, highY, highZ},
    }
    -- The twelve edges of a box, named by the corners above: the bottom face,
    -- the top face, and the four uprights between them.
    local edges = {
        {1, 2}, {2, 3}, {3, 4}, {4, 1},
        {5, 6}, {6, 7}, {7, 8}, {8, 5},
        {1, 5}, {2, 6}, {3, 7}, {4, 8},
    }
    for _, edge in ipairs(edges) do
        local from, to = corners[edge[1]], corners[edge[2]]
        dxDrawLine3D(from[1], from[2], from[3], to[1], to[2], to[3], colour)
    end
end

--- The last plan, kept so the per-frame draw does not replan.
--
-- Planning walks every Map Entity the snapshot holds. What changes between one
-- frame and the next is where things are, not which of them are marked, so the
-- decision is made at the polling cadence and the drawing follows the elements.
local lastPlan = {outline = false, zone = false, coronas = {}}

function ZoneMarks.render()
    local outline = elementFor(lastPlan.outline)
    if outline then
        drawOutline(outline)
    end
    local zone = elementFor(lastPlan.zone)
    if zone then
        drawZone(zone, lastPlan.zone.radius)
    end
end

--- Look at the world, decide, and put the coronas where the decision says.
function ZoneMarks.refresh()
    if not panel() then
        return false
    end
    lastPlan = ZoneMarks.plan(view(), look())
    reconcileCoronas(lastPlan.coronas)
    return lastPlan
end

addEventHandler("onClientRender", root, ZoneMarks.render)

addEventHandler("onClientResourceStart", resourceRoot, function()
    ZoneMarks.timer = setTimer(ZoneMarks.refresh, POLL_INTERVAL_MS, 0)
end)

addEventHandler("onClientResourceStop", resourceRoot, function()
    if ZoneMarks.timer and isTimer(ZoneMarks.timer) then
        killTimer(ZoneMarks.timer)
    end
    ZoneMarks.timer = false
    ZoneMarks.clear()
end)

-- A Runtime Instance being destroyed takes its corona with it. MTA breaks the
-- attachment rather than destroying what was attached, so without this the
-- corona would be left hanging in the air where the object used to be until
-- the next look at the world noticed.
addEventHandler("onClientElementDestroy", root, function()
    for key, corona in pairs(ZoneMarks.coronas) do
        if corona.element == source then
            destroyCorona(key)
        end
    end
end)

ANKIGTA.ZoneMarks = ZoneMarks

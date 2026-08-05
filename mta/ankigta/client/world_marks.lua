ANKIGTA = ANKIGTA or {}

-- What ANKIGTA draws into the world, so a row in the panel can be found in it.
--
-- Two marks, and they answer two different questions:
--
-- - The **zone** answers "how close would I have to stand?". `Draw radius` is
--   a way of *looking* rather than a property of anything looked at, so it is a
--   client setting and it draws the *selected* row's Activation Zone. It
--   outlives the panel closing, which is the point: the player sizes a zone,
--   closes F7 and walks the edge of it.
--
-- - A **corona** answers "where are the things I have set up?", from across a
--   street and with nothing open. `Show corona` is a property of the entity, so
--   it is stored on the entity and every player sees it; its colour and opacity
--   follow Settings unless the entity says otherwise.
--
-- The first is drawn, the second is a marker element. That is not an
-- inconsistency: a drawn thing exists while something is drawing it, which is
-- exactly right for a mark that follows the selection, and exactly wrong for
-- one that has to be there whether or not this module is doing anything.
--
-- Both follow the thing they mark, and neither waits for F7. A corona is
-- attached to its Runtime Instance, so MTA moves it; the zone reads the
-- element's position on the frame it is drawn. The panel asks the server for
-- its snapshot as soon as the player is authorized, so what is marked is known
-- before any window has been opened.
--
-- Nothing here decides anything about study. A mark is a mark; the Activation
-- Zone it depicts is `client/activation.lua`'s, and drawing one neither creates
-- nor resizes one.

local POLL_INTERVAL_MS = 250

--- How far from the camera anything ANKIGTA draws stops being drawn.
--
-- A stated number, because the complaint this answers is that there was none:
-- a mark with no far edge hangs in the air long after the object it marks has
-- dropped its LOD and gone, and reads as a bug in the world rather than as a
-- mark on something.
--
-- 150 metres. A GTA San Andreas city block is on the order of a hundred, so a
-- corona is still visible from across a street or a plaza -- which is what it
-- is for -- and is gone well before it is a light with nothing under it. It
-- sits inside MTA's own streaming, so the rule is ANKIGTA's rather than a race
-- with the streamer: markers stream within 600 units and objects within 500
-- (`CClientManager.cpp`, `CClientManager::CClientManager`), and a corona is
-- only ever put on a Runtime Instance that is streamed in.
local DRAW_DISTANCE = 150

--- How many segments a drawn circle is made of.
--
-- A zone sphere is three of them. Sixteen is the point where the corners stop
-- reading as corners at the radii a zone actually has -- the shipped default is
-- three metres and the largest allowed is fifty.
local CIRCLE_SEGMENTS = 16

local ZONE_ALPHA = 150
local ZONE_COLOR = {90, 200, 255}
local ZONE_WIDTH = 2

--- What a zone is drawn at when nothing says otherwise.
--
-- Only reached before the first settings have arrived; after that the schema's
-- own default is what `applySettings` was handed.
local FALLBACK_RADIUS = 3

local WorldMarks = {
    --- The client's way of looking, and the world's defaults behind an entity.
    settings = {
        drawRadius = false,
        coronaColor = false,
        coronaOpacity = false,
        activationRadius = false,
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

WorldMarks.settings.coronaColor = settingsDefault("coronaColor")
WorldMarks.settings.coronaOpacity = settingsDefault("coronaOpacity")
WorldMarks.settings.activationRadius = settingsDefault("activationRadius")

--- What one Map Entity is filed under here.
--
-- The panel's, not a second spelling of it: `runtimeElements` answers in this
-- key and `look` reads that answer, so a key defined twice is a corona that
-- stops resolving the day one of the two changes. Before the panel exists --
-- an incremental reload can hand this client one script ahead of another --
-- the same shape, so a mark made in that window is filed where the panel would
-- have filed it.
local function markKey(mapId, entityId)
    if ANKIGTA.Panel and ANKIGTA.Panel.entityKey then
        return ANKIGTA.Panel.entityKey(mapId, entityId)
    end
    return tostring(mapId) .. "/" .. tostring(entityId)
end

--- The Activation Zone radius in force for a mark.
--
-- `false` on the mark is the entity saying nothing of its own, which means the
-- global -- so a corona on an entity that follows Settings is the size the card
-- will really open at, not the size the shipped default happens to be.
function WorldMarks.radiusInForce(own)
    return tonumber(own)
        or tonumber(WorldMarks.settings.activationRadius)
        or tonumber(settingsDefault("activationRadius"))
        or FALLBACK_RADIUS
end

-- --- the one rule about distance -----------------------------------------

--- How far ANKIGTA draws, for whoever wants to say so.
function WorldMarks.drawDistance()
    return DRAW_DISTANCE
end

--- Where the drawing is being watched from.
--
-- The camera, not the player. The panel flies the camera to a row while the
-- player stays where they were, and that is done *in order to* look at the
-- mark; measuring from the player would put out the mark the player is
-- currently looking at.
local function cameraPosition()
    local x, y, z = getCameraMatrix()
    if type(x) ~= "number" then
        return false
    end
    return x, y, z
end

--- Is this spot near enough to draw on?
--
-- The one rule, and the only place the distance is compared. Everything below
-- goes through it, and so does anything added later that draws through this
-- module rather than reaching for `dxDrawLine3D` itself.
function WorldMarks.visible(x, y, z)
    if type(x) ~= "number" or type(y) ~= "number" or type(z) ~= "number" then
        return false
    end
    local cameraX, cameraY, cameraZ = cameraPosition()
    if cameraX == false then
        return false
    end
    return getDistanceBetweenPoints3D(cameraX, cameraY, cameraZ, x, y, z)
        <= DRAW_DISTANCE
end

-- --- everything ANKIGTA draws into the world ------------------------------
--
-- One door per mark, and each one asks the rule above about the spot the mark
-- stands on before drawing any of it. A mark added later inherits the distance
-- by being drawn through a door of its own rather than by remembering to ask.
--
-- Asked once per mark rather than once per line: a sphere is forty-eight
-- segments, and testing each of them would draw the near half of a mark whose
-- centre is out of range -- an arc hanging in the air, which is a worse answer
-- than either drawing it or not.
--
-- The minimap blip is deliberately not one of these: it is not in the world,
-- and a minimap that only showed what is already within sight would be a
-- minimap with nothing to say.

--- One circle, in the plane two of the three axes span.
local function circle(x, y, z, radius, plane, color)
    local previousA, previousB
    for step = 0, CIRCLE_SEGMENTS do
        local angle = step * 2 * math.pi / CIRCLE_SEGMENTS
        local a, b = math.cos(angle) * radius, math.sin(angle) * radius
        if previousA ~= nil then
            if plane == "xy" then
                dxDrawLine3D(
                    x + previousA, y + previousB, z,
                    x + a, y + b, z,
                    color, ZONE_WIDTH
                )
            elseif plane == "xz" then
                dxDrawLine3D(
                    x + previousA, y, z + previousB,
                    x + a, y, z + b,
                    color, ZONE_WIDTH
                )
            else
                dxDrawLine3D(
                    x, y + previousA, z + previousB,
                    x, y + a, z + b,
                    color, ZONE_WIDTH
                )
            end
        end
        previousA, previousB = a, b
    end
end

--- An Activation Zone, as the sphere it is.
--
-- Three great circles rather than a ring on the ground: the zone is a distance
-- in three dimensions, and a ring says nothing about the entity two storeys
-- above the one being set up.
--
-- Deliberately not the corona's colour. The two are separate ways of looking
-- and are on screen together; driving the wireframe from `Corona colour` would
-- make one setting quietly govern the other mark as well, and a player tuning
-- their coronas would find the zone they were sizing had changed with them.
function WorldMarks.sphere(x, y, z, radius)
    if not WorldMarks.visible(x, y, z) then
        return false
    end
    local color = tocolor(ZONE_COLOR[1], ZONE_COLOR[2], ZONE_COLOR[3], ZONE_ALPHA)
    for _, plane in ipairs({"xy", "xz", "yz"}) do
        circle(x, y, z, radius, plane, color)
    end
    return true
end

--- A standing beam, as wide as the thing it stands for.
--
-- The Next Card Indicator's mark. It is here rather than in that module for
-- the reason this section exists: it is drawn into the world, so it stops
-- where everything else ANKIGTA draws stops.
function WorldMarks.beam(x, y, z, width, color)
    if not WorldMarks.visible(x, y, z) then
        return false
    end
    dxDrawMaterialLine3D(x, y, z - 1, x, y, z + 2, nil, width, color)
    return true
end

-- --- what to draw --------------------------------------------------------

--- What the marks should be right now.
--
-- Pure: what is standing in the world arrives in `marks` with `present`
-- already answered, and what the player has chosen arrives in `view`. Nothing
-- here reads an element, a setting or a clock, which is what makes the rules
-- checkable without a game running -- and the rules are the interesting part.
--
-- `view` is `{selectedMapId, selectedEntityId, drawRadius, coronaColor,
-- coronaOpacity}`; each entry of `marks` is `{mapId, entityId, radius,
-- showCorona, coronaColor, coronaOpacity, present}`.
function WorldMarks.plan(view, marks)
    view = type(view) == "table" and view or {}
    local plan = {zone = false, coronas = {}}
    local selectedMapId = view.selectedMapId
    local selectedEntityId = view.selectedEntityId

    for _, mark in ipairs(marks or {}) do
        -- A mark is drawn on a thing that is here. A Map Entity whose Runtime
        -- Instance is unstreamed or destroyed has nothing to draw one on --
        -- its record and its Spatial Link are untouched either way.
        if mark.present == true then
            local radius = WorldMarks.radiusInForce(mark.radius)
            local selected = selectedMapId ~= false
                and selectedMapId ~= nil
                and mark.mapId == selectedMapId
                and mark.entityId == selectedEntityId
            if selected and view.drawRadius == true then
                plan.zone = {
                    mapId = mark.mapId,
                    entityId = mark.entityId,
                    radius = radius,
                }
            end
            if mark.showCorona == true then
                -- One corona per entity, whatever else is true of it: this
                -- loop visits each Map Entity once, so being selected as well
                -- cannot produce a second.
                plan.coronas[#plan.coronas + 1] = {
                    mapId = mark.mapId,
                    entityId = mark.entityId,
                    -- Sized by the Activation Zone it stands for, so the
                    -- corona is a thing the radius can be judged by rather
                    -- than a fixed dot.
                    radius = radius,
                    -- What the entity says, or what Settings says where the
                    -- entity says nothing. Resolved here rather than at the
                    -- marker, so "follows Settings" is one rule with one
                    -- reader instead of a fallback repeated per channel.
                    color = mark.coronaColor or view.coronaColor,
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
function WorldMarks.showsCorona(mapId, entityId)
    return WorldMarks.coronas[markKey(mapId, entityId)] ~= nil
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
function WorldMarks.owns(element)
    if creating then
        return true
    end
    return element ~= nil and WorldMarks.owned[element] == true
end

-- --- the settings behind the marks ---------------------------------------

--- Take the settings that decide what is drawn.
--
-- Called by both settings stores the way the Next Card Indicator's mode is, so
-- a stored value is in force from the moment it is loaded rather than from the
-- next time something happens to ask. Each key is taken only when it is there:
-- the client store knows `drawRadius` and the server store knows the other
-- three, and neither may blank out what the other holds.
function WorldMarks.applySettings(values)
    if type(values) ~= "table" then
        return false, "invalid_settings"
    end
    if values.drawRadius ~= nil then
        WorldMarks.settings.drawRadius = values.drawRadius == true
    end
    if values.coronaColor ~= nil then
        WorldMarks.settings.coronaColor = values.coronaColor
    end
    if values.coronaOpacity ~= nil then
        WorldMarks.settings.coronaOpacity = tonumber(values.coronaOpacity)
    end
    if values.activationRadius ~= nil then
        WorldMarks.settings.activationRadius = tonumber(values.activationRadius)
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
    WorldMarks.resolved = resolved
    return marks
end

--- What the player has chosen, as the planner takes it.
local function view()
    local selectedMapId, selectedEntityId = panel().selection()
    return {
        selectedMapId = selectedMapId,
        selectedEntityId = selectedEntityId,
        drawRadius = WorldMarks.settings.drawRadius == true,
        coronaColor = WorldMarks.settings.coronaColor,
        coronaOpacity = WorldMarks.settings.coronaOpacity,
    }
end

local function elementFor(mark)
    if not mark then
        return false
    end
    local element = WorldMarks.resolved[markKey(mark.mapId, mark.entityId)]
    if element == nil or not isElement(element) then
        return false
    end
    return element
end

-- --- coronas -------------------------------------------------------------

local function channels(color, opacity)
    local red, green, blue = schema().colorChannels(color)
    if red == nil then
        -- A stored colour the rule would have refused. Falling back to the
        -- shipped default rather than to black, which is a colour somebody
        -- could have meant and this never is.
        red, green, blue = schema().colorChannels(settingsDefault("coronaColor"))
    end
    local alpha = tonumber(opacity)
    if alpha == nil or alpha < 0 or alpha > 1 then
        alpha = tonumber(settingsDefault("coronaOpacity")) or 0.6
    end
    return red or 0, green or 0, blue or 0, math.floor(alpha * 255 + 0.5)
end

--- Where a corona has to be for anyone to see it.
local function withinDrawDistance(element)
    local x, y, z = getElementPosition(element)
    return WorldMarks.visible(x, y, z)
end

local function destroyCorona(key)
    local existing = WorldMarks.coronas[key]
    if not existing then
        return
    end
    -- Out of the plan first, so the `onClientElementDestroy` this raises finds
    -- nothing left to destroy and cannot recurse.
    WorldMarks.coronas[key] = nil
    if isElement(existing.marker) then
        destroyElement(existing.marker)
    end
    -- Disowned last, for the same reason `creating` exists: the panel asks
    -- whether the vanishing element was ours from inside `destroyElement`, and
    -- a marker forgotten a statement earlier reads to it as a Map Entity
    -- leaving the world.
    WorldMarks.owned[existing.marker] = nil
end

--- Put a corona on this element, and remember what it was made to look like.
local function createCorona(key, element, wanted)
    local x, y, z = getElementPosition(element)
    local red, green, blue, alpha = channels(wanted.color, wanted.opacity)
    creating = true
    local marker = createMarker(
        x, y, z, "corona", wanted.radius, red, green, blue, alpha
    )
    creating = false
    if not isElement(marker) then
        return
    end
    setElementInterior(marker, getElementInterior(element) or 0)
    setElementDimension(marker, getElementDimension(element) or 0)
    -- Attached rather than moved: a corona on a vehicle has to keep up with
    -- it, and following it in Lua would be this module's own polling loop over
    -- the same elements MTA is already moving.
    attachElements(marker, element, 0, 0, 0)
    wanted.marker = marker
    WorldMarks.coronas[key] = wanted
    WorldMarks.owned[marker] = true
end

--- Make an existing corona look the way the plan says.
--
-- Resized and recoloured in place. Destroying and recreating a marker to
-- change its size would break the attachment and flicker, and MTA has both
-- setters: `setMarkerSize` and `setMarkerColor`
-- (`CLuaMarkerDefs.cpp`, `CStaticFunctionDefinitions::SetMarkerSize`).
local function restyleCorona(existing, wanted)
    if existing.radius ~= wanted.radius then
        setMarkerSize(existing.marker, wanted.radius)
        existing.radius = wanted.radius
    end
    if existing.color ~= wanted.color or existing.opacity ~= wanted.opacity then
        local red, green, blue, alpha = channels(wanted.color, wanted.opacity)
        setMarkerColor(existing.marker, red, green, blue, alpha)
        existing.color = wanted.color
        existing.opacity = wanted.opacity
    end
    -- Attached, so it is already wherever the thing has got to. Which world it
    -- is in does not come with the attachment though: an entity moved into
    -- another interior or dimension would leave its corona glowing in the one
    -- it left.
    setElementInterior(existing.marker, getElementInterior(existing.element) or 0)
    setElementDimension(existing.marker, getElementDimension(existing.element) or 0)
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
        -- The distance rule, for the one mark that is an element rather than
        -- something drawn per frame: past it, the corona is not in the world
        -- at all.
        if element and withinDrawDistance(element) then
            keep[key] = true
            local wanted = {
                radius = corona.radius,
                color = corona.color,
                opacity = corona.opacity,
                element = element,
            }
            local existing = WorldMarks.coronas[key]
            -- `isElement` first, because everything after it is about a marker
            -- that exists. A marker destroyed by something other than this
            -- module still leaves its record here, and a record that matched
            -- the plan would never be replaced -- so the entity would go
            -- unmarked for as long as nothing about it changed.
            if existing
                and isElement(existing.marker)
                and existing.element == element
            then
                restyleCorona(existing, wanted)
            else
                destroyCorona(key)
                createCorona(key, element, wanted)
            end
        end
    end
    for key in pairs(WorldMarks.coronas) do
        if not keep[key] then
            destroyCorona(key)
        end
    end
end

--- Take every corona out of the world.
function WorldMarks.clear()
    for key in pairs(WorldMarks.coronas) do
        destroyCorona(key)
    end
    WorldMarks.resolved = {}
end

-- --- drawing -------------------------------------------------------------

--- The last plan, kept so the per-frame draw does not replan.
--
-- Planning walks every Map Entity the snapshot holds. What changes between one
-- frame and the next is where things are, not which of them are marked, so the
-- decision is made at the polling cadence and the drawing follows the element.
local lastPlan = {zone = false, coronas = {}}

function WorldMarks.render()
    local zone = elementFor(lastPlan.zone)
    if not zone then
        return
    end
    local x, y, z = getElementPosition(zone)
    if type(x) ~= "number" then
        return
    end
    WorldMarks.sphere(x, y, z, lastPlan.zone.radius)
end

--- Look at the world, decide, and put the coronas where the decision says.
function WorldMarks.refresh()
    if not panel() then
        return false
    end
    lastPlan = WorldMarks.plan(view(), look())
    reconcileCoronas(lastPlan.coronas)
    return lastPlan
end

addEventHandler("onClientRender", root, WorldMarks.render)

addEventHandler("onClientResourceStart", resourceRoot, function()
    WorldMarks.timer = setTimer(WorldMarks.refresh, POLL_INTERVAL_MS, 0)
end)

addEventHandler("onClientResourceStop", resourceRoot, function()
    if WorldMarks.timer and isTimer(WorldMarks.timer) then
        killTimer(WorldMarks.timer)
    end
    WorldMarks.timer = false
    WorldMarks.clear()
end)

-- A Runtime Instance being destroyed takes its corona with it. MTA breaks the
-- attachment rather than destroying what was attached, so without this the
-- corona would be left hanging in the air where the object used to be until
-- the next look at the world noticed.
addEventHandler("onClientElementDestroy", root, function()
    for key, corona in pairs(WorldMarks.coronas) do
        if corona.element == source then
            destroyCorona(key)
        end
    end
end)

ANKIGTA.WorldMarks = WorldMarks

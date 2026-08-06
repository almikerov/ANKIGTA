ANKIGTA = ANKIGTA or {}

-- What ANKIGTA is doing right now, in one place.
--
-- Two things needed this. A benchmark cannot assert on a surface that reports
-- only its final answer: F7 opening, a search returning and a session
-- rebuilding are all "it happened" and nothing else, so there is no number to
-- hold against a threshold. And a player writing a bug report has nothing to
-- paste: "the card did not open" carries none of what would explain it.
--
-- So each surface leaves its last outcome here as plain values, and the spatial
-- state is read from the module that owns it rather than copied into a second
-- place that could disagree with it.
--
-- Nothing here is a sentence. The heading is the only string that comes from
-- the table; every value is a stable technical name or a number, which is what
-- makes a pasted report mean the same thing to whoever reads the report.

local Diagnostics = {
    sections = {},
    order = {},
}

local function text(key)
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.text(key)
    end
    return key
end

--- Leave the last outcome of one surface.
-- Replaces rather than merges: a stale field kept alive next to a fresh one is
-- how a report starts lying.
function Diagnostics.record(section, values)
    if type(section) ~= "string" or type(values) ~= "table" then
        return false
    end
    if Diagnostics.sections[section] == nil then
        table.insert(Diagnostics.order, section)
    end
    Diagnostics.sections[section] = values
    return true
end

--- Everything, including the state pulled from whoever owns it.
function Diagnostics.snapshot()
    local report = {}
    for section, values in pairs(Diagnostics.sections) do
        report[section] = values
    end
    if ANKIGTA.Activation and ANKIGTA.Activation.diagnostics then
        report.spatial = ANKIGTA.Activation.diagnostics()
    end
    if ANKIGTA.Spatial and ANKIGTA.Spatial.diagnostics then
        -- The other half of "why did the card not open": whether the world is
        -- being polled at all, and whether the entity is here to be polled
        -- for. The decision's own report cannot say either.
        report.polling = ANKIGTA.Spatial.diagnostics()
    end
    if ANKIGTA.TextLabelDisplay and ANKIGTA.TextLabelDisplay.diagnostics then
        -- How many Text Labels the world holds, how many the last frame drew
        -- and how many the cap left out. The cap is why it is here: the notice
        -- on screen goes with the frame, and "the rest never got linked" is
        -- what a player concludes without a number they can paste.
        report.textLabels = ANKIGTA.TextLabelDisplay.diagnostics()
    end
    return report
end

local function formatValue(value)
    if value == nil then
        return "nil"
    end
    if type(value) == "number" then
        -- Whole numbers as whole numbers: `tracked=5000.0` reads as a
        -- measurement rather than a count.
        if value == math.floor(value) then
            return string.format("%d", value)
        end
        return string.format("%.3f", value)
    end
    return tostring(value)
end

--- The report as one line per section, `section key=value key=value`.
function Diagnostics.lines()
    local report = Diagnostics.snapshot()
    local sections = {}
    for _, section in ipairs(Diagnostics.order) do
        if report[section] ~= nil then
            table.insert(sections, section)
        end
    end
    if report.spatial ~= nil and Diagnostics.sections.spatial == nil then
        table.insert(sections, "spatial")
    end

    local lines = {}
    for _, section in ipairs(sections) do
        local keys = {}
        for key in pairs(report[section]) do
            table.insert(keys, key)
        end
        -- Sorted, so two reports of the same state read as the same text.
        table.sort(keys)
        local parts = {section}
        for _, key in ipairs(keys) do
            table.insert(
                parts,
                key .. "=" .. formatValue(report[section][key])
            )
        end
        table.insert(lines, table.concat(parts, " "))
    end
    return lines
end

local function announce()
    outputChatBox(text("diagnostics.title"), 160, 200, 255)
    for _, line in ipairs(Diagnostics.lines()) do
        outputChatBox(line, 200, 200, 200)
        -- Also to the debug log, so a report can be recovered from the log of a
        -- session whose chat has already scrolled away.
        outputDebugString("[ANKIGTA] diagnostics " .. line, 3)
    end
end

addCommandHandler("ankigta-diagnostics", announce)

ANKIGTA.Diagnostics = Diagnostics

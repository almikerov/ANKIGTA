ANKIGTA = ANKIGTA or {}

-- What a Text Label says: the three decisions between a note field and a line
-- drawn in the world (ADR 0029).
--
-- Kept apart from the world and from the store, because none of the three
-- needs either. Which field is shown when the chosen one cannot be, what is
-- left of a field once Anki's markup is gone, and where a long answer stops
-- are all answerable from a note and two numbers -- so they are answered here,
-- once, and both sides read the same answer.
--
-- Characters, not bytes. Lua 5.1 has no notion of an encoding and `#` counts
-- bytes, so a line limit measured with it wraps a two-byte letter in the
-- middle and hands the renderer half a character. Every length and every cut
-- in this file goes through the UTF-8 walk below.
--
-- And no character class either. Lua 5.1's `%s`, `%a` and `%d` are `isspace`,
-- `isalpha` and `isdigit`, which answer about the C locale the process happens
-- to be in -- and in a Windows-1252 one, `isspace(0xA0)` is true. 0xA0 is the
-- last byte of U+4F60, so `%s+` collapsing whitespace turned a Chinese
-- character into two bytes and half of one. Measured here, in the harness, on
-- the first note that was not ASCII. Every class below is written out, so what
-- a byte means does not depend on where the server was started.

local TextLabel = {}

--- The whitespace this file recognises: space, tab, CR, LF, VT, FF.
--
-- ASCII only, which is the point -- every byte of a multi-byte character is
-- 0x80 or above and so cannot be one of these whatever the locale says.
local SPACE = " \t\r\n\11\12"
local SPACE_RUN = "[" .. SPACE .. "]+"
local NON_SPACE_RUN = "[^" .. SPACE .. "]+"

--- How wide a drawn line gets, and how many of them there are.
--
-- Both are here rather than in the renderer: "wrapped to the line limit" is a
-- property of the label, and a second copy of the number in the module that
-- draws it is a second answer waiting to disagree.
TextLabel.LINE_LENGTH = 28
TextLabel.MAX_LINES = 3

--- How many labels are drawn at once, nearest first.
--
-- A world can hold thousands of Spatial Links, and a screen showing thousands
-- of labels shows none of them. Applying the cap is the client's, because only
-- the client knows which labels are near; the number is here so the side that
-- reports what it dropped and the side that dropped it cannot disagree.
TextLabel.MAX_DRAWN = 24

--- What a truncated line ends in.
--
-- Said rather than implied. A line that simply stops reads as the whole
-- answer, and a player who read half an answer and thought they read all of it
-- has been told something false.
TextLabel.ELLIPSIS = "\226\128\166"

-- UTF-8 ----------------------------------------------------------------------

--- Where each character of `text` starts, plus one past the end.
--
-- A continuation byte is `10xxxxxx`; anything else begins a character. That is
-- the whole of what this needs to know about the encoding, and it is enough to
-- count characters and to cut between them.
local function characterStarts(text)
    local starts = {}
    local length = #text
    local index = 1
    while index <= length do
        starts[#starts + 1] = index
        local byte = string.byte(text, index)
        local size = 1
        if byte >= 0xF0 then
            size = 4
        elseif byte >= 0xE0 then
            size = 3
        elseif byte >= 0xC0 then
            size = 2
        end
        index = index + size
    end
    starts[#starts + 1] = length + 1
    return starts
end

--- How many characters `text` has, whatever they are encoded as.
function TextLabel.characterCount(text)
    if type(text) ~= "string" then
        return 0
    end
    return #characterStarts(text) - 1
end

--- The first `count` characters of `text`, cut between characters.
function TextLabel.firstCharacters(text, count)
    if type(text) ~= "string" then
        return ""
    end
    local starts = characterStarts(text)
    local available = #starts - 1
    if count >= available then
        return text
    end
    if count <= 0 then
        return ""
    end
    return string.sub(text, 1, starts[count + 1] - 1)
end

--- One code point as UTF-8, so a numeric entity survives being decoded.
local function utf8Encode(codepoint)
    if codepoint < 0x80 then
        return string.char(codepoint)
    end
    if codepoint < 0x800 then
        return string.char(
            0xC0 + math.floor(codepoint / 0x40),
            0x80 + codepoint % 0x40
        )
    end
    if codepoint < 0x10000 then
        return string.char(
            0xE0 + math.floor(codepoint / 0x1000),
            0x80 + math.floor(codepoint / 0x40) % 0x40,
            0x80 + codepoint % 0x40
        )
    end
    return string.char(
        0xF0 + math.floor(codepoint / 0x40000),
        0x80 + math.floor(codepoint / 0x1000) % 0x40,
        0x80 + math.floor(codepoint / 0x40) % 0x40,
        0x80 + codepoint % 0x40
    )
end

-- Markup ---------------------------------------------------------------------

--- The named entities Anki's editor actually writes.
--
-- `&nbsp;` becomes an ordinary space rather than a no-break one: it is here to
-- be collapsed away with the rest of the whitespace, and a field holding only
-- non-breaking spaces is as wordless as a field holding only spaces.
local NAMED_ENTITIES = {
    nbsp = " ",
    amp = "&",
    lt = "<",
    gt = ">",
    quot = '"',
    apos = "'",
}

--- The words a field holds, with Anki's markup taken off.
--
-- A tag becomes a space rather than nothing: `one<br>two` is two words, and
-- deleting the tag outright would draw `onetwo`. A `[sound:]` reference and an
-- `<img>` leave nothing behind at all, which is what makes a field holding
-- only media wordless rather than merely short.
function TextLabel.plainText(value)
    if type(value) ~= "string" then
        return ""
    end
    local text = value
    -- Media first: a sound reference is not a tag, so the tag sweep below
    -- would leave `[sound:hello.mp3]` sitting there as words.
    text = string.gsub(text, "%[sound:[^%]]*%]", " ")
    text = string.gsub(text, "%[anki:[^%]]*%]", " ")
    text = string.gsub(text, "<[^>]*>", " ")
    text = string.gsub(text, "&#[xX]([0-9A-Fa-f]+);", function(hex)
        return utf8Encode(tonumber(hex, 16) or 63)
    end)
    text = string.gsub(text, "&#([0-9]+);", function(digits)
        return utf8Encode(tonumber(digits) or 63)
    end)
    text = string.gsub(text, "&([A-Za-z]+);", function(name)
        return NAMED_ENTITIES[string.lower(name)] or ("&" .. name .. ";")
    end)
    -- The no-break space a pasted field carries, as its two UTF-8 bytes. It is
    -- not whitespace to the class above -- deliberately, because that class is
    -- ASCII -- and a line that begins with one looks wrongly indented.
    text = string.gsub(text, "\194\160", " ")
    text = string.gsub(text, SPACE_RUN, " ")
    text = string.gsub(text, "^ ", "")
    text = string.gsub(text, " $", "")
    return text
end

--- Is there anything to read here at all?
function TextLabel.hasWords(value)
    return TextLabel.plainText(value) ~= ""
end

-- Which field -----------------------------------------------------------------

--- The field a Text Label shows, and whether that is the one that was asked for.
--
-- `fields` is the note's own fields in the order its note type declares them.
-- `requested` is the field name the link or the global setting names; empty
-- means "whichever comes first", which is the answer for a player who has not
-- chosen and for a note type nobody had in mind when they did.
--
-- A chosen field that this note type does not have, and one that holds only
-- media, both fall through to the first field that does have words -- and both
-- say so, because an object showing something other than what was asked for
-- has to read as such rather than as correct.
function TextLabel.choose(fields, requested)
    local wanted = type(requested) == "string" and requested or ""
    local result = {
        text = "",
        fieldName = "",
        requestedField = wanted,
        fallback = false,
        reason = false,
    }

    local first, firstText = false, ""
    local found = false
    for _, field in ipairs(type(fields) == "table" and fields or {}) do
        local name = type(field.name) == "string" and field.name or ""
        local text = TextLabel.plainText(field.value)
        if wanted ~= "" and name == wanted then
            found = true
            if text ~= "" then
                result.text = text
                result.fieldName = name
                return result
            end
        end
        if first == false and text ~= "" then
            first, firstText = name, text
        end
    end

    if first == false then
        result.reason = "no_words"
        return result
    end

    result.text = firstText
    result.fieldName = first
    if wanted ~= "" then
        result.fallback = true
        result.reason = found and "field_wordless" or "field_missing"
    end
    return result
end

-- Where it stops ---------------------------------------------------------------

local function appendEllipsis(line, lineLength)
    local ellipsisLength = TextLabel.characterCount(TextLabel.ELLIPSIS)
    local kept = TextLabel.firstCharacters(line, lineLength - ellipsisLength)
    kept = string.gsub(kept, " $", "")
    return kept .. TextLabel.ELLIPSIS
end

--- The drawn lines, wrapped between words, and whether anything was left out.
--
-- A word longer than the line is broken rather than allowed to run past it:
-- one unbroken word is a label that reaches off the side of the screen, and a
-- label nobody can read is not better than a wrapped one.
function TextLabel.wrap(text, lineLength, maxLines)
    local width = tonumber(lineLength) or TextLabel.LINE_LENGTH
    local limit = tonumber(maxLines) or TextLabel.MAX_LINES
    local lines = {}
    local plain = type(text) == "string" and text or ""
    if plain == "" or width < 1 or limit < 1 then
        return {lines = lines, truncated = false}
    end

    -- Every word, then every word too long for a line broken into pieces that
    -- fit. Wrapping and breaking are the same loop afterwards.
    local pieces = {}
    for word in string.gmatch(plain, NON_SPACE_RUN) do
        local remaining = word
        while TextLabel.characterCount(remaining) > width do
            local head = TextLabel.firstCharacters(remaining, width)
            pieces[#pieces + 1] = head
            remaining = string.sub(remaining, #head + 1)
        end
        if remaining ~= "" then
            pieces[#pieces + 1] = remaining
        end
    end

    local current = ""
    for index, piece in ipairs(pieces) do
        local candidate = current == "" and piece or (current .. " " .. piece)
        if TextLabel.characterCount(candidate) <= width then
            current = candidate
        else
            lines[#lines + 1] = current
            if #lines == limit then
                -- Everything from here on is what the label does not show, and
                -- the ellipsis is how it says so.
                lines[limit] = appendEllipsis(lines[limit], width)
                return {lines = lines, truncated = true}
            end
            current = piece
        end
        if index == #pieces and current ~= "" then
            lines[#lines + 1] = current
            current = ""
        end
    end
    return {lines = lines, truncated = false}
end

--- Everything a Text Label needs from one note, in one call.
--
-- The two halves are separately useful and separately tested; this is the
-- order they are always used in, written down once so no caller has to
-- remember it.
function TextLabel.build(fields, requested, lineLength, maxLines)
    local chosen = TextLabel.choose(fields, requested)
    local wrapped = TextLabel.wrap(chosen.text, lineLength, maxLines)
    chosen.lines = wrapped.lines
    chosen.truncated = wrapped.truncated
    return chosen
end

ANKIGTA.TextLabel = TextLabel

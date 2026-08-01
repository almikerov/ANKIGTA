ANKIGTA = ANKIGTA or {}

-- Session statistics.
--
-- These count *cards*, not Spatial Links. One card linked to five entities is
-- one card to study; reporting five would tell the player they have more work
-- than they do.
--
-- Nothing here decides what a card's state is. That comes from Anki's observed
-- state (ADR 0017): a card Anki has not reported on is simply not counted,
-- because the alternative is guessing, and guessing is a second scheduler.

local Statistics = {}

local COUNTED_STATES = {
    new = "new",
    learning = "learning",
    review = "due",
    not_due = "early",
}

--- Read a link row as the store actually emits it.
--
-- `Store` hands back raw SQLite rows, so the columns are snake_case. Reading
-- camelCase here would silently match nothing and report zero for everything,
-- which looks exactly like "no work to do".
local function readLink(link)
    if type(link) ~= "table" then
        return false
    end
    local collectionUuid = link.collection_uuid or link.collectionUuid
    local cardId = tonumber(link.card_id or link.cardId)
    if type(collectionUuid) ~= "string" or cardId == nil then
        return false
    end
    return {
        collectionUuid = collectionUuid,
        cardId = cardId,
        mapId = link.map_id or link.mapId,
        state = link.link_state or link.state,
    }
end

local function cardKey(link)
    return link.collectionUuid .. "/" .. tostring(link.cardId)
end

--- Is this link one that may contribute its card to the counts?
--
-- Anything other than an active link -- Card missing, Pending Map Save -- keeps
-- its record but offers nothing to study through.
local function linkContributes(link, includedMaps)
    if link.state ~= "active" then
        return false
    end
    if includedMaps and includedMaps[link.mapId] ~= true then
        return false
    end
    return true
end

--- Count unique cards by bucket.
--
-- `cardStates` is keyed `collectionUuid/cardId` and holds the state Anki
-- reported. `includedMaps` is the Active Map Set. `allowEarlyReview` decides
-- whether not-due cards are studied at all.
function Statistics.summarize(links, cardStates, includedMaps, allowEarlyReview)
    local counts = {new = 0, learning = 0, due = 0, early = 0, total = 0}
    local seen = {}

    for _, raw in ipairs(links or {}) do
        local link = readLink(raw)
        -- Excluded maps and non-active links are filtered before the card is
        -- considered at all, so a card reachable through several entities is
        -- judged on the ones that actually contribute.
        if link and linkContributes(link, includedMaps) then
            local key = cardKey(link)
            if not seen[key] then
                seen[key] = true
                local state = cardStates and cardStates[key] or nil
                local bucket = state and COUNTED_STATES[state] or nil
                if bucket == "early" and allowEarlyReview ~= true then
                    -- Preview only, so not part of the work to be done.
                    bucket = nil
                end
                if bucket then
                    counts[bucket] = counts[bucket] + 1
                    counts.total = counts.total + 1
                end
            end
        end
    end

    return counts
end

ANKIGTA.Statistics = Statistics

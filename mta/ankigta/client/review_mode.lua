ANKIGTA = ANKIGTA or {}

local REVIEW_OPEN_EVENT = "ankigta:openReviewMode"
local REVIEW_SIDE_EVENT = "ankigta:reviewSide"
local REVIEW_REVEAL_REQUEST_EVENT = "ankigta:revealAnswer"
local REVIEW_RATE_REQUEST_EVENT = "ankigta:submitRating"
local REVIEW_RESULT_EVENT = "ankigta:reviewResult"
local REVIEW_CLOSED_EVENT = "ankigta:reviewClosed"
local REVIEW_RETURN_REQUEST_EVENT = "ankigta:returnToCard"
local OPEN_SETTINGS_EVENT = "ankigta:openSettings"
local AUTHORIZATION_EVENT = "ankigta:setAuthorized"

local RATINGS = {"again", "hard", "good", "easy"}
local function label(key)
    -- Asked for at draw time, and the key stands in when the string table is
    -- not loaded: a hot-reloaded client can run this module without it.
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.text(key)
    end
    return key
end

local function formatted(key, ...)
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.format(key, ...)
    end
    return key
end

--- Resolve a stored warning or result into text.
-- What is stored is the key and its arguments, never finished text: what is
-- held is what happened, and the words for it are the drawing's business.
local function message(entry)
    if type(entry) == "table" then
        return formatted(entry.key, unpack(entry.args or {}))
    end
    if type(entry) == "string" then
        return label(entry)
    end
    return false
end

local RATING_KEYS = {
    again = "review.again",
    hard = "review.hard",
    good = "review.good",
    easy = "review.easy",
}

-- Game controls ANKIGTA must not act on while a card is open. Movement is left
-- alone deliberately: taking it away mid-review is more disorienting than a
-- player wandering off, and the review does not depend on standing still.
local BLOCKED_CONTROLS = {
    "fire",
    "vehicle_fire",
    "vehicle_secondary_fire",
    "enter_exit",
    "action",
    "next_weapon",
    "previous_weapon",
    "radio_next",
    "radio_previous",
}

-- Design pixels at UI Scale 1. The layout manager turns them into whatever the
-- current scale and resolution make of them.
local RATING_BAR_HEIGHT = 56
local SETTINGS_BUTTON_WIDTH = 150
local SETTINGS_BUTTON_HEIGHT = 26
local TITLE_BAR_HEIGHT = 26

-- Defaults come from the shared schema where it is loaded, so this module and
-- the settings store cannot drift into disagreeing about what "default" means.
local function schemaDefault(key, fallback)
    if ANKIGTA.Settings then
        local value = ANKIGTA.Settings.default(key)
        if value ~= nil then
            return value
        end
    end
    return fallback
end

local Review = {
    active = false,
    side = "question",
    submitted = false,
    awaitingResult = false,
    result = false,
    warning = false,
    focused = true,
    closeAfterRating = schemaDefault("closeAfterRating", true),
    -- Set when the card navigated its main frame somewhere else. Rating stays
    -- available: the player still knows which card they were answering.
    externalPage = false,
    cardAudioEnabled = schemaDefault("cardAudioEnabled", true),
    muteGameWorld = schemaDefault("muteGameWorld", false),
    -- Two independent settings, both on by default. Protection stops new harm;
    -- disabling controls stops the player acting. Wanting one without the
    -- other is reasonable, so neither implies the other.
    reviewProtection = schemaDefault("reviewProtection", true),
    disablePlayerControls = schemaDefault("disablePlayerControls", true),
    browser = false,
    identity = false,
    ratingBounds = {},
    captured = false,
}

--- Where the card sits, asked of the layout manager rather than worked out
--- here.
--
-- It is what applies UI Scale, keeps the surface on screen after a resolution
-- change and remembers where the player dragged it. A second copy of that
-- arithmetic in this file would be a second copy to get wrong.
local function surfaceRect()
    return ANKIGTA.Layout.rect("review")
end

--- The heights the surface is divided into, at the current scale.
local function surfaceBands(scale)
    return math.floor(TITLE_BAR_HEIGHT * scale),
        math.floor(RATING_BAR_HEIGHT * scale)
end

local function occupiedVehicle()
    local vehicle = getPedOccupiedVehicle(localPlayer)
    return isElement(vehicle) and vehicle or false
end

local function captureClientState()
    -- Restoration must return what was actually there, not a default: the
    -- player may already have had the cursor up, controls disabled by another
    -- resource, or damage-proofing set by a gamemode.
    local controls = {}
    if Review.disablePlayerControls then
        for _, control in ipairs(BLOCKED_CONTROLS) do
            controls[control] = isControlEnabled(control)
            toggleControl(control, false)
        end
    end

    local vehicle = occupiedVehicle()
    Review.captured = {
        controls = controls,
        -- The cursor is not captured. MTA counts requests for it across
        -- resources, so `isCursorShowing()` answers for everyone, and handing
        -- that answer back on the way out leaves this one asking forever --
        -- another resource's window open, then this, then both closed, and the
        -- cursor is stranded with nothing left to dismiss it. Everything else
        -- here really is ours to put back.
        cameraTarget = getCameraTarget(),
        radioChannel = getRadioChannel(),
        worldSoundEnabled = Review.muteGameWorld ~= true,
        playerDamageProof = isElementDamageProof(localPlayer),
        vehicle = vehicle,
        vehicleDamageProof = vehicle and isElementDamageProof(vehicle) or false,
    }

    if Review.reviewProtection then
        -- New damage only. Existing health is left exactly where it was: this
        -- is not a heal, and the world keeps running around the player.
        setElementDamageProof(localPlayer, true)
        if vehicle then
            setElementDamageProof(vehicle, true)
        end
    end
    showCursor(true)
end

local function restoreClientState()
    local captured = Review.captured
    if not captured then
        return
    end
    for control, enabled in pairs(captured.controls or {}) do
        toggleControl(control, enabled == true)
    end
    showCursor(false)
    if captured.cameraTarget and isElement(captured.cameraTarget) then
        setCameraTarget(captured.cameraTarget)
    end
    if type(captured.radioChannel) == "number" then
        setRadioChannel(captured.radioChannel)
    end
    setWorldSoundEnabled(0, captured.worldSoundEnabled ~= false)
    -- Protection goes back to whatever it was, which may well have been on:
    -- another resource's damage-proofing must survive a review.
    setElementDamageProof(localPlayer, captured.playerDamageProof == true)
    if captured.vehicle and isElement(captured.vehicle) then
        setElementDamageProof(
            captured.vehicle,
            captured.vehicleDamageProof == true
        )
    end
    Review.captured = false
end

local function destroyBrowser()
    if isElement(Review.browser) then
        destroyElement(Review.browser)
    end
    Review.browser = false
end

function isReviewModeActive()
    return Review.active == true
end

function reviewModeState()
    return {
        active = Review.active,
        side = Review.side,
        submitted = Review.submitted,
        awaitingResult = Review.awaitingResult,
        result = message(Review.result),
        warning = message(Review.warning),
        focused = Review.focused,
        externalPage = Review.externalPage,
        cardAudioEnabled = Review.cardAudioEnabled,
        muteGameWorld = Review.muteGameWorld,
    }
end

--- Card audio and world audio are separate controls.
-- Muting a noisy card should not also silence the game, and playing in silence
-- should not force card audio off.
--- Review Protection and control disabling are configured independently.
function setReviewProtection(protection, disableControls)
    Review.reviewProtection = protection ~= false
    Review.disablePlayerControls = disableControls ~= false
    return true
end

--- Whether an accepted rating closes the card.
-- The player owns this one (ADR 0014), so it is set here rather than carried
-- in the payload the server sends when it opens a card.
function setCloseAfterRating(closeAfterRating)
    Review.closeAfterRating = closeAfterRating ~= false
    return true
end

function setReviewAudio(cardAudioEnabled, muteGameWorld)
    Review.cardAudioEnabled = cardAudioEnabled ~= false
    Review.muteGameWorld = muteGameWorld == true
    if isElement(Review.browser) then
        setBrowserVolume(Review.browser, Review.cardAudioEnabled and 1 or 0)
    end
    setWorldSoundEnabled(0, not Review.muteGameWorld)
    return true
end

local function closeReviewMode(reason)
    if not Review.active then
        return false
    end
    Review.active = false
    Review.awaitingResult = false
    if ANKIGTA.Layout.dragging("review") then
        -- Closing mid-drag still ends where the player left it.
        ANKIGTA.Layout.endDrag()
    end
    unbindKey("escape", "down", requestCloseReviewMode)
    removeEventHandler("onClientRender", root, renderReviewMode)
    destroyBrowser()
    restoreClientState()
    local identity = Review.identity
    Review.identity = false
    Review.result = false
    Review.warning = false
    Review.submitted = false
    Review.side = "question"
    Review.externalPage = false
    triggerServerEvent(
        REVIEW_CLOSED_EVENT,
        resourceRoot,
        identity or false,
        reason or "closed"
    )
    return true
end

function requestCloseReviewMode()
    if not Review.active then
        return false
    end
    if Review.awaitingResult then
        -- A rating is in flight; closing now would leave the player unsure
        -- whether it counted.
        return false
    end
    return closeReviewMode(Review.submitted and "closed_after_rating" or "cancelled")
end

function renderReviewMode()
    if not Review.active then
        return
    end
    local x, y, width, height, scale = surfaceRect()
    local titleHeight, ratingHeight = surfaceBands(scale)
    dxDrawRectangle(0, 0, guiGetScreenSize(), tocolor(0, 0, 0, 180))
    dxDrawRectangle(x, y, width, height, tocolor(16, 16, 16, 235))

    Review.ratingBounds = {}

    -- The title bar is the drag handle, the same way a CEGUI window's is. It
    -- is drawn rather than owned by CEGUI because the card is a dx surface;
    -- what counts as the handle is the layout manager's to say, so nothing is
    -- recorded here for the click handler to test against.
    dxDrawRectangle(x, y, width, titleHeight, tocolor(38, 38, 38, 245))
    dxDrawText(
        label("review.title"),
        x + math.floor(8 * scale),
        y,
        x + width - math.floor(8 * scale),
        y + titleHeight,
        tocolor(235, 235, 235, 255),
        scale,
        "default-bold",
        "left",
        "center"
    )

    local cardY = y + titleHeight
    local cardHeight = height - titleHeight - ratingHeight
    if isElement(Review.browser) then
        dxDrawImage(x, cardY, width, cardHeight, Review.browser)
    end

    local warningText = message(Review.warning)
    if warningText then
        dxDrawText(
            warningText,
            x + math.floor(8 * scale),
            cardY + math.floor(8 * scale),
            x + width - math.floor(8 * scale),
            cardY + math.floor(28 * scale),
            tocolor(255, 190, 60, 255),
            scale,
            "default-bold"
        )
    end

    local barY = y + height - ratingHeight

    -- Review Mode swallows the game's hotkeys, F7 included, so the settings
    -- panel needs a way in that does not require closing the card first.
    Review.ratingBounds.settings = {
        x + 8,
        barY - SETTINGS_BUTTON_HEIGHT - 4,
        SETTINGS_BUTTON_WIDTH,
        SETTINGS_BUTTON_HEIGHT,
    }
    dxDrawRectangle(
        x + 8,
        barY - SETTINGS_BUTTON_HEIGHT - 4,
        SETTINGS_BUTTON_WIDTH,
        SETTINGS_BUTTON_HEIGHT,
        tocolor(48, 48, 48, 235)
    )
    dxDrawText(
        label("review.settings"),
        x + 8,
        barY - SETTINGS_BUTTON_HEIGHT - 4,
        x + 8 + SETTINGS_BUTTON_WIDTH,
        barY - 4,
        tocolor(235, 235, 235, 255),
        1,
        "default-bold",
        "center",
        "center"
    )

    if Review.externalPage then
        -- Optional, and never automatic: the card may have navigated somewhere
        -- the player actually wanted to read.
        local returnWidth = math.floor(220 * scale)
        local returnX = x + width - returnWidth - math.floor(8 * scale)
        local returnY = cardY + math.floor(8 * scale)
        local returnHeight = math.floor(28 * scale)
        Review.ratingBounds.returnToCard = {
            returnX,
            returnY,
            returnWidth,
            returnHeight,
        }
        dxDrawRectangle(
            returnX,
            returnY,
            returnWidth,
            returnHeight,
            tocolor(48, 48, 48, 235)
        )
        dxDrawText(
            label("review.returnToCard"),
            returnX,
            returnY,
            returnX + returnWidth,
            returnY + returnHeight,
            tocolor(235, 235, 235, 255),
            scale,
            "default-bold",
            "center",
            "center"
        )
    end
    if Review.side ~= "answer" then
        local revealLabel = label("review.showAnswer")
        Review.ratingBounds.reveal = {x, barY, width, ratingHeight}
        dxDrawRectangle(x, barY, width, ratingHeight, tocolor(40, 40, 40, 235))
        dxDrawText(
            revealLabel,
            x,
            barY,
            x + width,
            barY + ratingHeight,
            tocolor(235, 235, 235, 255),
            scale,
            "default-bold",
            "center",
            "center"
        )
        return
    end

    local buttonWidth = width / #RATINGS
    for index, rating in ipairs(RATINGS) do
        local buttonX = x + (index - 1) * buttonWidth
        Review.ratingBounds[rating] = {
            buttonX,
            barY,
            buttonWidth,
            ratingHeight,
        }
        local enabled = not Review.submitted and not Review.awaitingResult
        dxDrawRectangle(
            buttonX,
            barY,
            buttonWidth - 2,
            ratingHeight,
            enabled and tocolor(48, 48, 48, 235) or tocolor(28, 28, 28, 235)
        )
        dxDrawText(
            label(RATING_KEYS[rating]),
            buttonX,
            barY,
            buttonX + buttonWidth,
            barY + ratingHeight,
            enabled and tocolor(235, 235, 235, 255) or tocolor(120, 120, 120, 255),
            scale,
            "default-bold",
            "center",
            "center"
        )
    end

    local resultText = message(Review.result)
    if resultText then
        dxDrawText(
            resultText,
            x,
            barY - math.floor(24 * scale),
            x + width,
            barY,
            tocolor(150, 220, 150, 255),
            scale,
            "default-bold",
            "center",
            "center"
        )
    end
end

local function withinBounds(bounds, cursorX, cursorY)
    if type(bounds) ~= "table" then
        return false
    end
    return cursorX >= bounds[1]
        and cursorX <= bounds[1] + bounds[3]
        and cursorY >= bounds[2]
        and cursorY <= bounds[2] + bounds[4]
end

--- `onClientClick` hands over the cursor position first and the world point
--- after it: `button, state, screenX, screenY, worldX, worldY, worldZ, element`
--- (`CClientGame::ProcessMessage`, which pushes `vecCursorPosition` before
--- `vecCollision`). Hit-testing against the world point instead would put every
--- button somewhere the player is not clicking.
function handleReviewClick(button, state, cursorX, cursorY)
    if not Review.active or button ~= "left" then
        return
    end
    if state == "up" then
        if ANKIGTA.Layout.dragging("review") then
            ANKIGTA.Layout.endDrag()
            cancelEvent()
        end
        return
    end
    if state ~= "down" then
        return
    end
    cancelEvent()
    if not Review.focused then
        -- Regaining focus after Alt+Tab must cost a click, so the click that
        -- brings the window back cannot also rate the card.
        Review.focused = true
        return
    end
    if ANKIGTA.Layout.beginDrag("review", cursorX, cursorY) then
        -- The title bar moves the card; it never answers it.
        return
    end
    if withinBounds(Review.ratingBounds.settings, cursorX, cursorY) then
        triggerEvent(OPEN_SETTINGS_EVENT, resourceRoot)
        return
    end
    if withinBounds(Review.ratingBounds.returnToCard, cursorX, cursorY) then
        triggerServerEvent(
            REVIEW_RETURN_REQUEST_EVENT,
            resourceRoot,
            Review.identity or false,
            Review.side
        )
        return
    end
    if Review.side ~= "answer" then
        if withinBounds(Review.ratingBounds.reveal, cursorX, cursorY) then
            triggerServerEvent(
                REVIEW_REVEAL_REQUEST_EVENT,
                resourceRoot,
                Review.identity or false
            )
        end
        return
    end
    if Review.submitted or Review.awaitingResult then
        -- One accepted rating per Review Mode; further clicks are noise.
        return
    end
    for _, rating in ipairs(RATINGS) do
        if withinBounds(Review.ratingBounds[rating], cursorX, cursorY) then
            Review.awaitingResult = true
            triggerServerEvent(
                REVIEW_RATE_REQUEST_EVENT,
                resourceRoot,
                Review.identity or false,
                rating
            )
            return
        end
    end
end

local function openReviewMode(payload)
    if Review.active or type(payload) ~= "table" then
        return false
    end
    if type(payload.url) ~= "string" or payload.url == "" then
        return false
    end
    Review.active = true
    Review.side = payload.side == "answer" and "answer" or "question"
    Review.submitted = false
    Review.awaitingResult = false
    Review.result = false
    Review.warning = payload.warning or false
    Review.focused = true
    Review.identity = payload.cardIdentity or false
    Review.ratingBounds = {}

    captureClientState()

    local _x, _y, width, height, scale = surfaceRect()
    local titleHeight, ratingHeight = surfaceBands(scale)
    Review.browser = createBrowser(
        width,
        height - titleHeight - ratingHeight,
        false,
        false
    )
    if not Review.browser then
        closeReviewMode("browser_unavailable")
        return false
    end
    bindKey("escape", "down", requestCloseReviewMode)
    addEventHandler("onClientRender", root, renderReviewMode)
    return true
end

addEvent(REVIEW_OPEN_EVENT, true)
addEventHandler(REVIEW_OPEN_EVENT, resourceRoot, function(payload)
    openReviewMode(payload)
end)

addEvent(REVIEW_SIDE_EVENT, true)
addEventHandler(REVIEW_SIDE_EVENT, resourceRoot, function(payload)
    if not Review.active or type(payload) ~= "table" then
        return
    end
    if type(payload.url) ~= "string" or payload.url == "" then
        Review.warning = "review.sideLoadFailed"
        return
    end
    Review.side = payload.side == "answer" and "answer" or "question"
    Review.warning = payload.warning or false
    Review.externalPage = false
    if isElement(Review.browser) then
        loadBrowserURL(Review.browser, payload.url)
    end
end)

addEvent(REVIEW_RESULT_EVENT, true)
addEventHandler(REVIEW_RESULT_EVENT, resourceRoot, function(outcome)
    if not Review.active or type(outcome) ~= "table" then
        return
    end
    Review.awaitingResult = false
    if outcome.state == "applied" then
        Review.submitted = true
        Review.result = "review.applied"
        if Review.closeAfterRating then
            closeReviewMode("closed_after_rating")
        end
        return
    end
    if outcome.state == "outcome_unknown" then
        -- Not a failure the player can retry away: say so plainly and keep the
        -- card open rather than pretending the rating did or did not land.
        Review.submitted = true
        Review.result = false
        Review.warning = "review.outcomeUnknown"
        return
    end
    Review.warning = {
        key = "review.ratingRejected",
        args = {tostring(outcome.category or "unknown")},
    }
end)

addEventHandler("onClientBrowserNavigate", root, function(url, isBlocked)
    if not Review.active or source ~= Review.browser then
        return
    end
    if isBlocked then
        Review.warning = "review.navigationBlocked"
        return
    end
    -- MTA reports navigation after the fact; it cannot be cancelled from Lua
    -- (prototype 0006). Rating stays enabled -- the player still knows which
    -- card they were answering.
    if type(url) == "string" and not string.find(url, "/render/", 1, true) then
        Review.externalPage = true
        Review.warning = "review.externalPage"
    end
end)

addEventHandler("onClientBrowserLoadingFailed", root, function(url, errorCode)
    if not Review.active or source ~= Review.browser then
        return
    end
    -- A card that fails to render is still a card that can be rated.
    Review.warning = {
        key = "review.loadFailed",
        args = {tostring(errorCode or url or "unknown")},
    }
end)

addEventHandler("onClientBrowserCreated", root, function()
    if not Review.active or source ~= Review.browser then
        return
    end
    requestBrowserDomains({"127.0.0.1"})
end)

addEvent("ankigta:reviewBrowserReady", true)

addEventHandler("onClientBrowserWhitelistChange", root, function()
    if not Review.active or not isElement(Review.browser) then
        return
    end
    triggerServerEvent(
        REVIEW_REVEAL_REQUEST_EVENT,
        resourceRoot,
        Review.identity or false,
        "question"
    )
end)

-- Focus loss must neither close the card nor submit anything.
addEventHandler("onClientMainMenuOpen", root, function()
    Review.focused = false
end)

addEventHandler("onClientRestore", root, function(didClearRenderTargets)
    if Review.active then
        Review.focused = false
        if didClearRenderTargets and isElement(Review.browser) then
            focusBrowser(Review.browser)
        end
    end
end)

addEvent(AUTHORIZATION_EVENT, true)
addEventHandler(AUTHORIZATION_EVENT, resourceRoot, function(authorized)
    if authorized ~= true and Review.active then
        closeReviewMode("authorization_revoked")
    end
end)

-- `onClientCursorMove` reports the relative position first and the absolute
-- one after it (`button`-free: `relativeX, relativeY, absoluteX, absoluteY,
-- worldX, worldY, worldZ`), so the drag follows arguments three and four.
addEventHandler("onClientCursorMove", root, function(
    _relativeX,
    _relativeY,
    absoluteX,
    absoluteY
)
    if Review.active and ANKIGTA.Layout.dragging("review") then
        ANKIGTA.Layout.dragTo(absoluteX, absoluteY)
    end
end)

addEventHandler("onClientClick", root, handleReviewClick)
addEventHandler("onClientResourceStop", resourceRoot, function()
    if Review.active then
        closeReviewMode("resource_stop")
    end
end)

ANKIGTA.ReviewMode = Review

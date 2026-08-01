local STATUS_EVENT = "ankigta:companionStatus"
local START_STUDY_REQUEST_EVENT = "ankigta:startStudy"
local REBUILD_STUDY_REQUEST_EVENT = "ankigta:rebuildStudy"
local PAUSE_STUDY_REQUEST_EVENT = "ankigta:pauseStudy"
local STOP_STUDY_REQUEST_EVENT = "ankigta:stopStudy"
local CANCEL_STUDY_REQUEST_EVENT = "ankigta:cancelStudyRebuild"

ANKIGTA = ANKIGTA or {}

local function text(key, ...)
    -- Read when the control is written, so switching language and reopening
    -- the window needs no resource restart.
    if ANKIGTA.Locale then
        return ANKIGTA.Locale.format(key, ...)
    end
    return key
end

local window = nil
local statusLabel = nil
-- The last status drawn, so the window can be rebuilt in another language
-- without waiting for the companion to send the next one.
local lastStatus = nil
local startButton = nil
local pauseButton = nil
local rebuildButton = nil
local stopButton = nil
local cancelButton = nil
local earlyReview = nil

local function closeStudyUi()
    if isElement(window) then
        destroyElement(window)
    end
    window = nil
    statusLabel = nil
    startButton = nil
    pauseButton = nil
    rebuildButton = nil
    stopButton = nil
    cancelButton = nil
    earlyReview = nil
    showCursor(false)
end

local function studyText(study)
    if type(study) ~= "table" then
        return text("study.disconnected")
    end
    if study.sessionActive == true then
        return text(
            "study.session",
            tonumber(study.progress or 0),
            tonumber(study.total or 0)
        )
    end
    return text("study.paused")
end

local function ensureStudyUi()
    if isElement(window) then
        return
    end
    local screenWidth, screenHeight = guiGetScreenSize()
    local width, height = 420, 240
    window = guiCreateWindow(
        (screenWidth - width) / 2,
        (screenHeight - height) / 2,
        width,
        height,
        text("study.title"),
        false
    )
    statusLabel = guiCreateLabel(
        18,
        30,
        width - 36,
        24,
        text("study.paused"),
        false,
        window
    )
    earlyReview = guiCreateCheckBox(
        18,
        60,
        width - 36,
        24,
        text("settings.allowEarlyReview"),
        false,
        false,
        window
    )
    startButton = guiCreateButton(
        18, 96, 92, 30, text("study.start"), false, window
    )
    pauseButton = guiCreateButton(
        118, 96, 76, 30, text("study.pause"), false, window
    )
    rebuildButton = guiCreateButton(
        202, 96, 92, 30, text("study.rebuild"), false, window
    )
    stopButton = guiCreateButton(
        302, 96, 76, 30, text("study.stop"), false, window
    )
    cancelButton = guiCreateButton(
        18,
        136,
        140,
        30,
        text("study.cancelRebuild"),
        false,
        window
    )
    addEventHandler("onClientGUIClick", startButton, function()
        triggerServerEvent(
            START_STUDY_REQUEST_EVENT,
            resourceRoot,
            guiCheckBoxGetSelected(earlyReview)
        )
    end, false)
    addEventHandler("onClientGUIClick", pauseButton, function()
        triggerServerEvent(PAUSE_STUDY_REQUEST_EVENT, resourceRoot)
    end, false)
    addEventHandler("onClientGUIClick", rebuildButton, function()
        triggerServerEvent(
            REBUILD_STUDY_REQUEST_EVENT,
            resourceRoot,
            guiCheckBoxGetSelected(earlyReview)
        )
    end, false)
    addEventHandler("onClientGUIClick", stopButton, function()
        triggerServerEvent(STOP_STUDY_REQUEST_EVENT, resourceRoot)
    end, false)
    addEventHandler("onClientGUIClick", cancelButton, function()
        triggerServerEvent(CANCEL_STUDY_REQUEST_EVENT, resourceRoot)
    end, false)
    showCursor(true)
end

local function updateStudyUi(status)
    ensureStudyUi()
    guiSetText(statusLabel, studyText(status and status.study))
    local active = status
        and status.state == "connected"
        and status.study
        and status.study.sessionActive == true
    guiSetEnabled(startButton, not active)
    guiSetEnabled(pauseButton, active)
    guiSetEnabled(rebuildButton, active)
    guiSetEnabled(stopButton, active)
    guiSetEnabled(
        cancelButton,
        status
            and status.state == "connected"
            and status.study
            and status.study.pausedReason == "rebuilding"
    )
end

addCommandHandler("ankigta", function()
    ensureStudyUi()
end)

addEvent(STATUS_EVENT, true)
addEventHandler(STATUS_EVENT, resourceRoot, function(status)
    if source ~= resourceRoot or type(status) ~= "table" then
        return
    end
    lastStatus = status
    updateStudyUi(status)
end)

if ANKIGTA.Locale then
    ANKIGTA.Locale.onChange(function()
        if not isElement(window) then
            return
        end
        -- Labels are written once, when the control is built, so the window is
        -- rebuilt rather than relabelled control by control.
        closeStudyUi()
        updateStudyUi(lastStatus)
    end)
end

addEventHandler("onClientResourceStop", resourceRoot, closeStudyUi)

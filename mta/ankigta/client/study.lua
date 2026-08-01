local STATUS_EVENT = "ankigta:companionStatus"
local START_STUDY_REQUEST_EVENT = "ankigta:startStudy"
local REBUILD_STUDY_REQUEST_EVENT = "ankigta:rebuildStudy"
local PAUSE_STUDY_REQUEST_EVENT = "ankigta:pauseStudy"
local STOP_STUDY_REQUEST_EVENT = "ankigta:stopStudy"
local CANCEL_STUDY_REQUEST_EVENT = "ankigta:cancelStudyRebuild"

local window = nil
local statusLabel = nil
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
        return "Study: disconnected"
    end
    if study.sessionActive == true then
        return string.format(
            "Study: ANKIGTA Session (%d/%d)",
            tonumber(study.progress or 0),
            tonumber(study.total or 0)
        )
    end
    return "Study: paused"
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
        "ANKIGTA — Study",
        false
    )
    statusLabel = guiCreateLabel(18, 30, width - 36, 24, "Study: paused", false, window)
    earlyReview = guiCreateCheckBox(
        18,
        60,
        width - 36,
        24,
        "Разрешить досрочное повторение",
        false,
        false,
        window
    )
    startButton = guiCreateButton(18, 96, 92, 30, "Начать обучение", false, window)
    pauseButton = guiCreateButton(118, 96, 76, 30, "Пауза", false, window)
    rebuildButton = guiCreateButton(202, 96, 92, 30, "Перестроить", false, window)
    stopButton = guiCreateButton(302, 96, 76, 30, "Остановить", false, window)
    cancelButton = guiCreateButton(
        18,
        136,
        140,
        30,
        "Отменить перестройку",
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
    updateStudyUi(status)
end)

addEventHandler("onClientResourceStop", resourceRoot, closeStudyUi)

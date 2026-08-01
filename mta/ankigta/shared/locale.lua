ANKIGTA = ANKIGTA or {}

-- Localization.
--
-- Russian and English ship as UTF-8 tables. English is the fallback, and a
-- missing Russian string logs a diagnostic rather than showing a blank: a gap
-- in the translation is a bug to fix, not something to hide from whoever could
-- fix it.
--
-- What is never translated: card text, Map Entity names the user typed, Entity
-- Tags and Anki Tags. Those are the user's own words, and "translating" them
-- would be corrupting data. Stored technical values -- setting keys, states,
-- identifiers -- are likewise independent of language, so switching language
-- can never change what is persisted.

local DEFAULT_LANGUAGE = "en"

local Locale = {
    language = DEFAULT_LANGUAGE,
    -- Keys requested that the active language lacked, for diagnostics.
    missing = {},
}

Locale.strings = {
    en = {
        ["settings.title"] = "Settings",
        ["settings.activationRadius"] = "Activation Zone radius (m)",
        ["settings.activationDelaySeconds"] = "Activation delay (s)",
        ["settings.maxActivationSpeedKmh"] = "Maximum speed (km/h)",
        ["settings.allowEarlyReview"] = "Allow early review",
        ["settings.indicatorMode"] = "Next Card Indicator",
        ["settings.reviewProtection"] = "Review Protection",
        ["settings.disablePlayerControls"] = "Disable player controls",
        ["settings.closeAfterRating"] = "Close after rating",
        ["settings.cardAudioEnabled"] = "Card audio",
        ["settings.muteGameWorld"] = "Mute game world",
        ["settings.uiScale"] = "UI scale",
        ["settings.language"] = "Language",
        ["settings.error.unknown"] = "Unknown setting",
        ["settings.error.not_a_number"] = "Enter a number",
        ["settings.error.out_of_range"] = "Value is outside the allowed range",
        ["settings.error.not_on_step"] = "Value must fall on the allowed step",
        ["settings.error.too_precise"] = "Too many decimal places",
        ["settings.error.not_a_boolean"] = "Choose on or off",
        ["settings.error.not_a_choice"] = "Choose one of the offered options",
        ["settings.error.not_a_string"] = "Enter text",
        ["settings.error.wrong_authority"] = "This setting is owned elsewhere",
        ["review.showAnswer"] = "Show answer",
        ["review.again"] = "Again",
        ["review.hard"] = "Hard",
        ["review.good"] = "Good",
        ["review.easy"] = "Easy",
        ["review.applied"] = "Rating applied",
        ["review.outcomeUnknown"] =
            "Rating outcome is unknown; ANKIGTA will reconcile it later",
        ["review.returnToCard"] = "Return to card",
        ["review.externalPage"] = "External page opened",
        ["study.start"] = "Start studying",
        ["study.pause"] = "Pause studying",
        ["statistics.total"] = "Total",
        ["statistics.new"] = "New",
        ["statistics.learning"] = "Learning",
        ["statistics.due"] = "Due",
        ["statistics.early"] = "Early",
    },
    ru = {
        ["settings.title"] = "Настройки",
        ["settings.activationRadius"] = "Радиус зоны активации (м)",
        ["settings.activationDelaySeconds"] = "Задержка активации (с)",
        ["settings.maxActivationSpeedKmh"] = "Максимальная скорость (км/ч)",
        ["settings.allowEarlyReview"] = "Разрешить досрочное повторение",
        ["settings.indicatorMode"] = "Индикатор следующей карточки",
        ["settings.reviewProtection"] = "Защита во время повторения",
        ["settings.disablePlayerControls"] = "Отключать управление игроком",
        ["settings.closeAfterRating"] = "Закрывать после оценки",
        ["settings.cardAudioEnabled"] = "Звук карточки",
        ["settings.muteGameWorld"] = "Приглушать игровой мир",
        ["settings.uiScale"] = "Масштаб интерфейса",
        ["settings.language"] = "Язык",
        ["settings.error.unknown"] = "Неизвестная настройка",
        ["settings.error.not_a_number"] = "Введите число",
        ["settings.error.out_of_range"] = "Значение вне допустимого диапазона",
        ["settings.error.not_on_step"] = "Значение должно попадать на шаг",
        ["settings.error.too_precise"] = "Слишком много знаков после запятой",
        ["settings.error.not_a_boolean"] = "Выберите «включено» или «выключено»",
        ["settings.error.not_a_choice"] = "Выберите один из предложенных вариантов",
        ["settings.error.not_a_string"] = "Введите текст",
        ["settings.error.wrong_authority"] = "Этой настройкой владеет другая сторона",
        ["review.showAnswer"] = "Показать ответ",
        ["review.again"] = "Again",
        ["review.hard"] = "Hard",
        ["review.good"] = "Good",
        ["review.easy"] = "Easy",
        ["review.applied"] = "Оценка принята",
        ["review.outcomeUnknown"] =
            "Результат оценки неизвестен; ANKIGTA сверит его позже",
        ["review.returnToCard"] = "Вернуться к карточке",
        ["review.externalPage"] = "Открыта внешняя страница",
        ["study.start"] = "Начать обучение",
        ["study.pause"] = "Приостановить обучение",
        ["statistics.total"] = "Всего",
        ["statistics.new"] = "Новые",
        ["statistics.learning"] = "Изучаются",
        ["statistics.due"] = "К повторению",
        ["statistics.early"] = "Досрочные",
    },
}

function Locale.availableLanguages()
    return {"ru", "en"}
end

--- Which language to use when the setting is `auto`.
-- `getLocalization()` returns `{code, name}`; the code may be a bare language
-- or a full locale, so match on the prefix.
function Locale.detect(localization)
    local code = type(localization) == "table" and localization.code or nil
    if type(code) == "string" and string.sub(string.lower(code), 1, 2) == "ru" then
        return "ru"
    end
    return DEFAULT_LANGUAGE
end

--- Switch language. No resource restart: every lookup reads this at call time.
function Locale.setLanguage(language, localization)
    if language == "auto" then
        Locale.language = Locale.detect(localization)
        return true, Locale.language
    end
    if not Locale.strings[language] then
        return false, "settings.error.not_a_choice"
    end
    Locale.language = language
    return true, language
end

--- Translate a key, falling back to English and recording the gap.
function Locale.text(key)
    local active = Locale.strings[Locale.language] or {}
    local value = active[key]
    if value ~= nil then
        return value
    end

    local fallback = Locale.strings[DEFAULT_LANGUAGE][key]
    if fallback ~= nil then
        if Locale.language ~= DEFAULT_LANGUAGE and not Locale.missing[key] then
            Locale.missing[key] = Locale.language
            outputDebugString(
                string.format(
                    "[ANKIGTA] missing_translation language=%s key=%s",
                    tostring(Locale.language),
                    tostring(key)
                ),
                2
            )
        end
        return fallback
    end

    -- Not translated in any language: show the key rather than nothing, so the
    -- gap is visible instead of appearing as a blank control.
    if not Locale.missing[key] then
        Locale.missing[key] = "none"
        outputDebugString(
            "[ANKIGTA] untranslated_key key=" .. tostring(key),
            1
        )
    end
    return key
end

ANKIGTA.Locale = Locale

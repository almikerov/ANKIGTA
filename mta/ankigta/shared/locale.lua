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
    -- Modules that hold text on screen rather than reading it every frame.
    listeners = {},
}

--- Be told when the language changes.
-- A window writes its labels once, when it is built, so it cannot notice a
-- switch on its own. Without this, "switching needs no restart" would mean
-- "switching needs no restart, but close every window first".
function Locale.onChange(callback)
    if type(callback) == "function" then
        table.insert(Locale.listeners, callback)
    end
    return true
end

local function announce(language)
    for _, callback in ipairs(Locale.listeners) do
        -- One module failing to rebuild must not stop the rest from trying.
        local ok, failure = pcall(callback, language)
        if not ok then
            outputDebugString(
                "[ANKIGTA] locale_listener_failed error=" .. tostring(failure),
                2
            )
        end
    end
end

Locale.strings = {
    en = {
        ["common.confirm"] = "Confirm",
        ["common.cancel"] = "Cancel",
        ["common.close"] = "Close",
        ["common.yes"] = "yes",
        ["common.no"] = "no",
        ["common.empty"] = "—",
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
        ["review.sideLoadFailed"] = "The card side could not be loaded",
        ["review.ratingRejected"] = "Rating rejected: %s",
        ["review.navigationBlocked"] = "Navigation blocked by MTA settings",
        ["review.loadFailed"] = "Card failed to load (%s)",
        ["study.title"] = "ANKIGTA — Study",
        ["study.start"] = "Start studying",
        ["study.pause"] = "Pause",
        ["study.rebuild"] = "Rebuild",
        ["study.stop"] = "Stop",
        ["study.cancelRebuild"] = "Cancel rebuild",
        ["study.disconnected"] = "Study: disconnected",
        ["study.paused"] = "Study: paused",
        ["study.session"] = "Study: ANKIGTA Session (%d/%d)",
        ["statistics.total"] = "Total",
        ["statistics.new"] = "New",
        ["statistics.learning"] = "Learning",
        ["statistics.due"] = "Due",
        ["statistics.early"] = "Early",
        ["f7.title"] = "ANKIGTA — Map Entity",
        ["f7.column.mapEntity"] = "Map Entity",
        ["f7.column.type"] = "Type",
        ["f7.column.authored"] = "Authored transform / world",
        ["f7.column.runtime"] = "Runtime Instance",
        ["f7.column.link"] = "Spatial Link",
        ["f7.runtime.destroyed"] = "Unavailable — Runtime Instance destroyed",
        ["f7.runtime.notStreamed"] = "Unavailable — Runtime Instance not streamed",
        ["f7.runtime.streamed"] = "Available — Runtime Instance streamed",
        ["f7.authoredPosition"] =
            "%.2f, %.2f, %.2f · interior %d · dimension %d",
        ["f7.metadataSummary"] = "name=%s; tag=%s; radius=%.1f; show=%s",
        ["f7.cardIdentity"] = "%s / cardId %s",
        ["f7.entityLabel"] = "Map Entity: %s",
        ["f7.cardLabel"] = "Card: %s",
        ["f7.recheck"] = "Check again",
        ["f7.copyOriginal"] = "Original / renamed",
        ["f7.copyNew"] = "New copy",
        ["f7.copyDecisionHint"] =
            "Map copy decision: Original / renamed or New copy",
        ["f7.relink"] = "Relink entity",
        ["f7.unlink"] = "Unlink",
        ["f7.replaceCard"] = "Replace card",
        ["f7.cardPicker"] = "Card Picker",
        ["f7.pickEntity"] = "Pick Entity",
        ["f7.undo"] = "Undo",
        ["f7.redo"] = "Redo",
        ["f7.relink.title"] = "ANKIGTA — Relink entity preview",
        ["f7.relink.missing"] = "Missing: %s",
        ["f7.relink.target"] = "Target: %s",
        ["f7.relink.chooseTarget"] = "choose from F7 or Pick Entity",
        ["f7.relink.metadataMoved"] = "Metadata moved: %s",
        ["f7.relink.pickTarget"] = "Pick target",
        ["f7.unlink.title"] = "ANKIGTA — Confirm Unlink",
        ["f7.unlink.explanation"] =
            "Only Spatial Link is removed; metadata stays saved.",
        ["f7.unlink.confirm"] = "Confirm Unlink",
        ["f7.replace.title"] = "ANKIGTA — Confirm Replace card",
        ["f7.replace.oldCard"] = "Old card: %s",
        ["f7.replace.newCard"] = "New card: %s",
        ["f7.replace.explanation"] =
            "Replacement is atomic; no intermediate Unlink is performed.",
        ["f7.replace.confirm"] = "Confirm Replace",
        -- The state itself is a stable technical value; only its display
        -- follows the language.
        ["f7.linkState.Active Spatial Link"] = "Active Spatial Link",
        ["f7.linkState.Card missing"] = "Card missing",
        ["f7.linkState.Entity missing"] = "Entity missing",
        ["f7.linkState.Identity Collision"] = "Identity Collision",
        ["f7.linkState.Pending Map Save"] = "Pending Map Save",
        ["f7.linkState.Unlinked"] = "Unlinked",
        ["cardPicker.title"] = "ANKIGTA — Card Picker",
        ["cardPicker.replaceTitle"] = "ANKIGTA — Replace card",
        ["cardPicker.search"] = "Search cards",
        ["cardPicker.column.card"] = "Card",
        ["cardPicker.column.deck"] = "Deck",
        ["cardPicker.column.state"] = "State",
        ["cardPicker.column.collection"] = "Collection",
        ["cardPicker.alreadyLinked"] = "%s — already linked to %s",
        ["cardPicker.link"] = "Link selected card",
        ["cardPicker.previewReplacement"] = "Preview replacement",
        ["recovery.title"] = "ANKIGTA — Database recovery",
        ["recovery.reason.database_corrupt"] =
            "The ANKIGTA database could not be read.",
        ["recovery.reason.restore_interrupted"] =
            "A restore did not finish. Both files are still on disk.",
        ["recovery.damaged"] = "Database: %s (%s)",
        ["recovery.explanation"] =
            "Nothing has been changed. Choose a verified backup to restore; "
            .. "the damaged file is kept for diagnosis rather than deleted.",
        ["recovery.column.created"] = "Created",
        ["recovery.column.kind"] = "Kind",
        ["recovery.column.schema"] = "Schema",
        ["recovery.column.state"] = "State",
        ["recovery.column.file"] = "File",
        ["recovery.column.reason"] = "Reason",
        ["recovery.kind.daily"] = "daily",
        ["recovery.kind.premigration"] = "pre-migration",
        ["recovery.usable"] = "Verified",
        ["recovery.unusable"] = "Cannot be used: %s",
        ["recovery.restore"] = "Restore selected backup",
        ["recovery.quarantineTitle"] = "Kept for diagnosis",
        ["recovery.noVerifiedBackup"] =
            "No backup passed verification. Nothing will be replaced; "
            .. "the files below are kept for diagnosis.",
        ["connection.title"] = "ANKIGTA — Companion Connection",
        ["connection.disconnected"] = "Connection is down: %s",
        ["connection.connect"] = "Connect",
        ["connection.advanced"] = "Advanced settings…",
        ["connection.settingsTitle"] = "ANKIGTA — Connection settings",
        ["connection.currentMode"] = "Current mode: %s; token: %s",
        ["connection.tokenProtected"] = "protected (hidden)",
        ["connection.tokenDisabled"] = "disabled",
        ["connection.manualPort"] = "Manual port",
        ["connection.replacementToken"] = "Replacement token (blank keeps current)",
        ["connection.disableToken"] = "Disable token explicitly",
        ["connection.dismissWarning"] = "Dismiss empty-token warning",
        ["connection.manualMode"] = "Manual Connection Mode",
        ["connection.automaticMode"] = "Automatic Connection Mode",
        ["connection.clearTokenFirst"] =
            "ANKIGTA: clear the replacement token before disabling it.",
        ["connection.status.connected"] = "ANKIGTA Companion: connected",
        ["connection.status.connecting"] = "ANKIGTA Companion: connecting",
        ["connection.status.protocol_error"] = "ANKIGTA Companion: protocol error",
        ["connection.status.timeout"] = "ANKIGTA Companion: connection timed out",
        ["connection.status.transport_error"] = "ANKIGTA Companion: transport error",
        ["connection.status.collection_unavailable"] =
            "ANKIGTA Companion: collection unavailable",
        ["connection.status.compatibility_failure"] =
            "ANKIGTA Companion: incompatible Anki configuration",
        ["connection.status.authorization_failure"] =
            "ANKIGTA Companion: connection token rejected",
        ["connection.status.connection_config_invalid"] =
            "ANKIGTA Companion: connection configuration is invalid",
        ["connection.status.manual_connection_config_invalid"] =
            "ANKIGTA Companion: manual connection settings are invalid",
        ["connection.status.effective_config_mismatch"] =
            "ANKIGTA Companion: effective settings do not match",
        ["connection.status.connection_config_rollback"] =
            "ANKIGTA Companion: using last-known-good settings",
        ["connection.status.empty_token"] =
            "ANKIGTA Companion: token protection is disabled",
        ["connection.status.disconnected"] = "ANKIGTA Companion: disconnected",
        ["connection.status.unknown"] = "%s [%s]",
        ["guidance.copyBlocked"] =
            "Copied IDs are blocked until a decision: Original / renamed or New copy.",
        ["guidance.saveWithEditor"] = "Save the map with the stock Map Editor command.",
        ["guidance.retrySave"] =
            "Repeat the stock Save or the Editor recovery, then press Check again.",
        ["guidance.cardMissing"] =
            "The card was deleted from the Bound Anki Collection. Use Replace card.",
        ["notice.pendingActivated"] =
            "Spatial Link activated after an independent read-back.",
        ["notice.pendingNotConfirmed"] =
            "Read-back did not confirm the IDs; Pending Map Save kept: %s",
        ["notice.pendingDiscarded"] =
            "Pending Map Save discarded: the map was closed or reloaded without Save.",
        ["notice.undoUnavailable"] = "Undo unavailable: %s",
        ["notice.redoUnavailable"] = "Redo unavailable: %s",
        ["notice.copyDecisionApplied"] =
            "Map copy decision applied; New copy has no automatic Spatial Link.",
        ["notice.copyDecisionFailed"] = "Map copy decision was not applied: %s",
        ["notice.cardPickerUnavailable"] = "Card Picker unavailable: %s",
        ["notice.studyStartFailed"] = "Study start failed: %s",
        ["notice.studyRebuildFailed"] = "Study rebuild failed: %s",
        ["notice.studyPauseFailed"] = "Study pause failed: %s",
        ["notice.studyStopFailed"] = "Study stop failed: %s",
        ["notice.studyCancelFailed"] = "Study rebuild cancel failed: %s",
        ["notice.linkFailed"] = "Spatial Link was not activated: %s",
        ["notice.unlinked"] = "Spatial Link removed; Map Entity metadata kept.",
        ["notice.unlinkFailed"] = "Unlink failed: %s",
        ["notice.replaced"] = "Card replaced with no intermediate Unlink.",
        ["notice.replaceFailed"] = "Replace card failed: %s",
        ["notice.relinkApplied"] =
            "Relink entity completed; Spatial Link and metadata moved.",
        ["notice.relinkFailed"] = "Relink entity was not applied: %s",
        ["notice.pickEntityFailed"] = "Pick Entity: %s",
        ["notice.restored"] =
            "Database restored from %s; the damaged file is kept for diagnosis.",
        ["notice.restoreFailed"] =
            "Nothing was restored and nothing was replaced: %s",
    },
    ru = {
        ["common.confirm"] = "Подтвердить",
        ["common.cancel"] = "Отмена",
        ["common.close"] = "Закрыть",
        ["common.yes"] = "да",
        ["common.no"] = "нет",
        ["common.empty"] = "—",
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
        ["review.sideLoadFailed"] = "Не удалось загрузить сторону карточки",
        ["review.ratingRejected"] = "Оценка отклонена: %s",
        ["review.navigationBlocked"] = "Переход заблокирован настройками MTA",
        ["review.loadFailed"] = "Ошибка загрузки карточки (%s)",
        ["study.title"] = "ANKIGTA — Обучение",
        ["study.start"] = "Начать обучение",
        ["study.pause"] = "Пауза",
        ["study.rebuild"] = "Перестроить",
        ["study.stop"] = "Остановить",
        ["study.cancelRebuild"] = "Отменить перестройку",
        ["study.disconnected"] = "Обучение: нет подключения",
        ["study.paused"] = "Обучение: приостановлено",
        ["study.session"] = "Обучение: ANKIGTA Session (%d/%d)",
        ["statistics.total"] = "Всего",
        ["statistics.new"] = "Новые",
        ["statistics.learning"] = "Изучаются",
        ["statistics.due"] = "К повторению",
        ["statistics.early"] = "Досрочные",
        ["f7.title"] = "ANKIGTA — Map Entity",
        ["f7.column.mapEntity"] = "Map Entity",
        ["f7.column.type"] = "Тип",
        ["f7.column.authored"] = "Авторские координаты / мир",
        ["f7.column.runtime"] = "Runtime Instance",
        ["f7.column.link"] = "Spatial Link",
        ["f7.runtime.destroyed"] = "Недоступна — Runtime Instance уничтожена",
        ["f7.runtime.notStreamed"] = "Недоступна — Runtime Instance не прогружена",
        ["f7.runtime.streamed"] = "Доступна — Runtime Instance прогружена",
        ["f7.authoredPosition"] =
            "%.2f, %.2f, %.2f · интерьер %d · измерение %d",
        ["f7.metadataSummary"] = "имя=%s; метка=%s; радиус=%.1f; показывать=%s",
        ["f7.cardIdentity"] = "%s / cardId %s",
        ["f7.entityLabel"] = "Map Entity: %s",
        ["f7.cardLabel"] = "Карточка: %s",
        ["f7.recheck"] = "Проверить ещё раз",
        ["f7.copyOriginal"] = "Original / renamed",
        ["f7.copyNew"] = "New copy",
        ["f7.copyDecisionHint"] =
            "Решение о копии карты: Original / renamed или New copy",
        ["f7.relink"] = "Relink entity",
        ["f7.unlink"] = "Unlink",
        ["f7.replaceCard"] = "Replace card",
        ["f7.cardPicker"] = "Card Picker",
        ["f7.pickEntity"] = "Pick Entity",
        ["f7.undo"] = "Отменить",
        ["f7.redo"] = "Повторить",
        ["f7.relink.title"] = "ANKIGTA — Предпросмотр Relink entity",
        ["f7.relink.missing"] = "Отсутствует: %s",
        ["f7.relink.target"] = "Цель: %s",
        ["f7.relink.chooseTarget"] = "выберите в F7 или через Pick Entity",
        ["f7.relink.metadataMoved"] = "Переносимые metadata: %s",
        ["f7.relink.pickTarget"] = "Выбрать цель",
        ["f7.unlink.title"] = "ANKIGTA — Подтверждение Unlink",
        ["f7.unlink.explanation"] =
            "Удаляется только Spatial Link; metadata остаются сохранёнными.",
        ["f7.unlink.confirm"] = "Подтвердить Unlink",
        ["f7.replace.title"] = "ANKIGTA — Подтверждение Replace card",
        ["f7.replace.oldCard"] = "Прежняя карточка: %s",
        ["f7.replace.newCard"] = "Новая карточка: %s",
        ["f7.replace.explanation"] =
            "Замена атомарна; промежуточный Unlink не выполняется.",
        ["f7.replace.confirm"] = "Подтвердить замену",
        ["f7.linkState.Active Spatial Link"] = "Активная Spatial Link",
        ["f7.linkState.Card missing"] = "Карточка отсутствует",
        ["f7.linkState.Entity missing"] = "Map Entity отсутствует",
        ["f7.linkState.Identity Collision"] = "Коллизия идентичности",
        ["f7.linkState.Pending Map Save"] = "Ожидается сохранение карты",
        ["f7.linkState.Unlinked"] = "Без связи",
        ["cardPicker.title"] = "ANKIGTA — Card Picker",
        ["cardPicker.replaceTitle"] = "ANKIGTA — Replace card",
        ["cardPicker.search"] = "Искать карточки",
        ["cardPicker.column.card"] = "Карточка",
        ["cardPicker.column.deck"] = "Колода",
        ["cardPicker.column.state"] = "Состояние",
        ["cardPicker.column.collection"] = "Коллекция",
        ["cardPicker.alreadyLinked"] = "%s — уже связана с %s",
        ["cardPicker.link"] = "Связать выбранную карточку",
        ["cardPicker.previewReplacement"] = "Предпросмотр замены",
        ["recovery.title"] = "ANKIGTA — Восстановление базы данных",
        ["recovery.reason.database_corrupt"] =
            "Базу данных ANKIGTA не удалось прочитать.",
        ["recovery.reason.restore_interrupted"] =
            "Восстановление не завершилось. Оба файла остались на диске.",
        ["recovery.damaged"] = "База данных: %s (%s)",
        ["recovery.explanation"] =
            "Ничего не изменено. Выберите проверенную копию для восстановления; "
            .. "повреждённый файл сохраняется для диагностики, а не удаляется.",
        ["recovery.column.created"] = "Создана",
        ["recovery.column.kind"] = "Тип",
        ["recovery.column.schema"] = "Схема",
        ["recovery.column.state"] = "Состояние",
        ["recovery.column.file"] = "Файл",
        ["recovery.column.reason"] = "Причина",
        ["recovery.kind.daily"] = "ежедневная",
        ["recovery.kind.premigration"] = "предмиграционная",
        ["recovery.usable"] = "Проверена",
        ["recovery.unusable"] = "Нельзя использовать: %s",
        ["recovery.restore"] = "Восстановить выбранную копию",
        ["recovery.quarantineTitle"] = "Сохранено для диагностики",
        ["recovery.noVerifiedBackup"] =
            "Ни одна копия не прошла проверку. Ничего не будет заменено; "
            .. "файлы ниже сохранены для диагностики.",
        ["connection.title"] = "ANKIGTA — Companion Connection",
        ["connection.disconnected"] = "Соединение отключено: %s",
        ["connection.connect"] = "Подключиться",
        ["connection.advanced"] = "Дополнительные настройки…",
        ["connection.settingsTitle"] = "ANKIGTA — Настройки подключения",
        ["connection.currentMode"] = "Текущий режим: %s; токен: %s",
        ["connection.tokenProtected"] = "защищён (скрыт)",
        ["connection.tokenDisabled"] = "отключён",
        ["connection.manualPort"] = "Ручной порт",
        ["connection.replacementToken"] = "Новый токен (пусто — оставить текущий)",
        ["connection.disableToken"] = "Явно отключить токен",
        ["connection.dismissWarning"] = "Скрыть предупреждение о пустом токене",
        ["connection.manualMode"] = "Manual Connection Mode",
        ["connection.automaticMode"] = "Automatic Connection Mode",
        ["connection.clearTokenFirst"] =
            "ANKIGTA: очистите новый токен, прежде чем отключать его.",
        ["connection.status.connected"] = "ANKIGTA Companion: подключено",
        ["connection.status.connecting"] = "ANKIGTA Companion: подключение",
        ["connection.status.protocol_error"] = "ANKIGTA Companion: ошибка протокола",
        ["connection.status.timeout"] =
            "ANKIGTA Companion: превышено время ожидания",
        ["connection.status.transport_error"] = "ANKIGTA Companion: ошибка транспорта",
        ["connection.status.collection_unavailable"] =
            "ANKIGTA Companion: коллекция недоступна",
        ["connection.status.compatibility_failure"] =
            "ANKIGTA Companion: конфигурация Anki несовместима",
        ["connection.status.authorization_failure"] =
            "ANKIGTA Companion: токен подключения отклонён",
        ["connection.status.connection_config_invalid"] =
            "ANKIGTA Companion: конфигурация подключения повреждена",
        ["connection.status.manual_connection_config_invalid"] =
            "ANKIGTA Companion: ручные настройки подключения повреждены",
        ["connection.status.effective_config_mismatch"] =
            "ANKIGTA Companion: effective-настройки не совпадают",
        ["connection.status.connection_config_rollback"] =
            "ANKIGTA Companion: используется предыдущая рабочая конфигурация",
        ["connection.status.empty_token"] =
            "ANKIGTA Companion: защита токеном отключена",
        ["connection.status.disconnected"] = "ANKIGTA Companion: отключено",
        ["connection.status.unknown"] = "%s [%s]",
        ["guidance.copyBlocked"] =
            "Скопированные ID заблокированы до решения: Original / renamed или New copy.",
        ["guidance.saveWithEditor"] =
            "Сохраните карту штатной командой stock Map Editor.",
        ["guidance.retrySave"] =
            "Повторите stock Save или восстановление Editor, "
            .. "затем нажмите «Проверить ещё раз».",
        ["guidance.cardMissing"] =
            "Карточка удалена из Bound Anki Collection. Используйте Replace card.",
        ["notice.pendingActivated"] =
            "Spatial Link активирована после независимого read-back.",
        ["notice.pendingNotConfirmed"] =
            "Read-back не подтвердил ID; Pending Map Save сохранена: %s",
        ["notice.pendingDiscarded"] =
            "Pending Map Save удалена: карта была закрыта или перезагружена без Save.",
        ["notice.undoUnavailable"] = "Undo недоступен: %s",
        ["notice.redoUnavailable"] = "Redo недоступен: %s",
        ["notice.copyDecisionApplied"] =
            "Решение о копии карты применено; у New copy нет автоматической Spatial Link.",
        ["notice.copyDecisionFailed"] = "Решение о копии карты не применено: %s",
        ["notice.cardPickerUnavailable"] = "Card Picker недоступен: %s",
        ["notice.studyStartFailed"] = "Не удалось начать обучение: %s",
        ["notice.studyRebuildFailed"] = "Не удалось перестроить обучение: %s",
        ["notice.studyPauseFailed"] = "Не удалось приостановить обучение: %s",
        ["notice.studyStopFailed"] = "Не удалось остановить обучение: %s",
        ["notice.studyCancelFailed"] = "Не удалось отменить перестройку: %s",
        ["notice.linkFailed"] = "Spatial Link не активирована: %s",
        ["notice.unlinked"] = "Spatial Link удалена; Map Entity metadata сохранены.",
        ["notice.unlinkFailed"] = "Unlink не выполнен: %s",
        ["notice.replaced"] = "Карточка заменена без промежуточного Unlink.",
        ["notice.replaceFailed"] = "Replace card не выполнен: %s",
        ["notice.relinkApplied"] =
            "Relink entity выполнен; Spatial Link и metadata перенесены.",
        ["notice.relinkFailed"] = "Relink entity не выполнен: %s",
        ["notice.pickEntityFailed"] = "Pick Entity: %s",
        ["notice.restored"] =
            "База данных восстановлена из %s; "
            .. "повреждённый файл сохранён для диагностики.",
        ["notice.restoreFailed"] =
            "Ничего не восстановлено и ничего не заменено: %s",
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
    local previous = Locale.language
    local chosen = language
    if language == "auto" then
        chosen = Locale.detect(localization)
    elseif not Locale.strings[language] then
        return false, "settings.error.not_a_choice"
    end
    Locale.language = chosen
    if chosen ~= previous then
        announce(chosen)
    end
    return true, chosen
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

--- Translate a key and fill its placeholders.
-- The template comes from the table, the arguments never do: a card's text, a
-- Map Entity name or an error category is substituted in as-is. A translation
-- whose placeholders do not match the call site is a bug worth seeing, but not
-- one worth taking the interface down for, so the untouched template is shown.
function Locale.format(key, ...)
    local template = Locale.text(key)
    if select("#", ...) == 0 then
        return template
    end
    local ok, formatted = pcall(string.format, template, ...)
    if ok then
        return formatted
    end
    outputDebugString(
        "[ANKIGTA] malformed_translation key=" .. tostring(key),
        2
    )
    return template
end

ANKIGTA.Locale = Locale

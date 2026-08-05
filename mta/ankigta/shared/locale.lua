ANKIGTA = ANKIGTA or {}

-- The string table.
--
-- ANKIGTA speaks English and carries no machinery for speaking anything else.
-- The strings still live here, under one key each, rather than inline at their
-- call sites: that keeps a sentence out of the middle of a module, and it lets
-- a string that is missing be found by a test rather than by a player reading
-- `f7.pickEntity` off a button.
--
-- What is never looked up here: card text, Map Entity names the user typed,
-- Entity Tags and Anki Tags. Those are the user's own words, and putting them
-- through this table would be corrupting data. Stored technical values --
-- setting keys, states, identifiers -- are likewise not text: only their
-- display comes from here.

local Locale = {
    -- Keys asked for that this table lacks, so one gap is reported once rather
    -- than on every frame that draws it.
    missing = {},
}

Locale.strings = {
    ["common.confirm"] = "Confirm",
    ["common.cancel"] = "Cancel",
    ["common.close"] = "X",
    ["common.yes"] = "yes",
    ["common.no"] = "no",
    ["common.empty"] = "—",
    ["settings.title"] = "Settings",
    ["settings.activationRadius"] = "Activation Zone radius (m)",
    ["settings.activationDelaySeconds"] = "Activation delay (s)",
    ["settings.maxActivationSpeedKmh"] =
        "Open cards when speed lower than:",
    ["settings.reviewMode"] = "Review mode",
    ["settings.indicatorMode"] = "Next Card Indicator",
    ["settings.reviewProtection"] = "Review Protection",
    ["settings.disablePlayerControls"] = "Disable player controls",
    ["settings.closeAfterRating"] = "Close cards after rating",
    ["settings.cardAudioEnabled"] = "Card audio",
    ["settings.muteGameWorld"] = "Mute world while reviewing",
    ["settings.uiScale"] = "UI scale",
    ["settings.uiPlacement"] = "Window placement",
    ["settings.connectionPort"] = "Companion port",
    ["settings.connectionToken"] = "Companion token",
    ["settings.apply"] = "Apply",
    ["settings.close"] = "X",
    ["settings.connectionSettings"] = "Connection settings…",
    ["settings.value.true"] = "On",
    ["settings.value.false"] = "Off",
    ["settings.value.sphere_and_minimap"] = "Sphere and minimap",
    ["settings.value.minimap_only"] = "Minimap only",
    ["settings.value.none"] = "No marker",
    -- Each says which cards the session takes, which is the whole reason
    -- this stopped being a checkbox called "Allow early review".
    ["settings.value.allow_due"] = "Allow due",
    ["settings.value.allow_all"] = "Allow all",
    ["settings.error.unknown"] = "Unknown setting",
    ["settings.error.not_a_number"] = "Enter a number",
    ["settings.error.out_of_range"] = "Value is outside the allowed range",
    ["settings.error.not_on_step"] = "Value must fall on the allowed step",
    ["settings.error.too_precise"] = "Too many decimal places",
    ["settings.error.not_a_boolean"] = "Choose on or off",
    ["settings.error.not_a_choice"] = "Choose one of the offered options",
    ["settings.error.not_a_string"] = "Enter text",
    ["settings.error.secret_not_readable"] =
        "This value is never shown again after it is saved",
    ["settings.error.not_a_placement"] =
        "Stored window placement is not usable",
    ["settings.error.wrong_authority"] = "This setting is owned elsewhere",
    ["settings.error.not_saved"] = "The setting could not be saved",
    ["ui.smaller"] = "Smaller (−0.05)",
    ["ui.larger"] = "Larger (+0.05)",
    ["ui.reset"] = "Reset UI layout",
    ["ui.resetExplanation"] =
        "Puts UI scale and every window back where they shipped.",
    ["ui.resetDone"] = "UI layout reset.",
    ["ui.editHud"] = "Edit HUD layout",
    ["ui.editHudExplanation"] =
        "While this is on, drag the HUD counters with the mouse.",
    ["ui.hudHandle"] = "Edit HUD layout — drag to move",
    ["review.title"] = "ANKIGTA — Review Mode",
    ["review.showAnswer"] = "Show answer",
    ["review.again"] = "Again",
    ["review.hard"] = "Hard",
    ["review.good"] = "Good",
    ["review.easy"] = "Easy",
    ["review.applied"] = "Rating applied",
    ["review.outcomeUnknown"] =
        "Rating outcome is unknown; ANKIGTA will reconcile it later",
    ["review.returnToCard"] = "Return to card",
    ["review.settings"] = "Settings",
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
    ["diagnostics.title"] = "ANKIGTA diagnostics — paste these lines into a bug report",
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
    ["f7.authoredPosition"] =
        "%.2f, %.2f, %.2f · interior %d · dimension %d",
    ["f7.metadataSummary"] = "name=%s; tag=%s; radius=%.1f; show=%s",
    ["f7.cardIdentity"] = "%s / cardId %s",
    ["f7.entityLabel"] = "Map Entity: %s",
    ["f7.cardLabel"] = "Card: %s",
    ["f7.recheck"] = "Check again",
    ["f7.filter"] = "Search Map Entity",
    ["f7.filterApply"] = "Search",
    ["f7.filterResult"] = "Showing %d of %d",
    -- Deleted from the map, so it is no longer a Map Entity. The link was
    -- made deliberately, so removing it is asked rather than assumed.
    ["f7.deleted.question"] =
        "\"%s\" is no longer on map \"%s\". Remove its saved link?",
    ["f7.deleted.forget"] = "Remove",
    ["f7.deleted.keep"] = "Keep",
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
    ["cardPicker.anyDeck"] = "Every deck",
    ["inspector.title"] = "The card itself",
    ["inspector.tags"] = "Tags",
    ["inspector.tagsHint"] = "separated by spaces",
    ["inspector.save"] = "Save card",
    ["inspector.open"] = "Edit card",
    ["inspector.close"] = "Hide editor",
    ["inspector.saved"] = "Saved",
    ["inspector.loading"] = "Reading...",
    ["inspector.unreadable"] = "This card could not be read: %s",
    ["f7.teleport"] = "Teleport",
    ["f7.activation"] = "Activation Zone",
    ["f7.name"] = "Name",
    ["f7.entity.unnamed"] = "Unnamed Map Entity",
    -- MTA has no name for a ped skin, so the skin itself is the name.
    ["f7.entity.pedSkin"] = "Ped skin %d",
    ["f7.radius"] = "Radius (m)",
    ["f7.showRadius"] = "Draw radius",
    -- The standing answer, kept on the entity: the world shows it
    -- whether or not F7 is open.
    ["f7.drawAlways"] = "Draw always",
    ["f7.replaceTitle"] = "Replace the linked card?",
    ["f7.replaceWarning"] = "The current link is discarded. The card"
        .. " itself is not touched.",
    ["f7.replaceCurrent"] = "Currently linked",
    ["f7.replaceNew"] = "Replacing with",
    ["f7.replaceUnknownCard"] = "(unknown card)",
    ["f7.linkState.Not adopted"] = "Not adopted",
    ["f7.guidance.notAdopted"] = "In the world, not in ANKIGTA yet."
        .. " Pick a card and press Link to take it in.",
    ["f7.linkState.Active Spatial Link"] = "Active Spatial Link",
    ["f7.linkState.Card missing"] = "Card missing",
    ["f7.linkState.Entity missing"] = "Entity missing",
    ["f7.linkState.Identity Collision"] = "Identity Collision",
    ["f7.linkState.Pending Map Save"] = "Pending Map Save",
    ["f7.linkState.Unlinked"] = "Unlinked",
    ["cardPicker.title"] = "ANKIGTA — Card Picker",
    ["cardPicker.replaceTitle"] = "ANKIGTA — Replace card",
    ["cardPicker.search"] = "Search cards",
    -- The field takes what Anki takes, so the hint is an Anki search and
    -- not an invitation to type a word and hope.
    ["cardPicker.queryHint"] = "Anki search, e.g. tag:verb -is:suspended",
    ["cardPicker.scope.cards"] = "Cards",
    ["cardPicker.scope.notes"] = "Notes",
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
    ["panel.title"] = "ANKIGTA",
    ["panel.connection.explain"] =
        "ANKIGTA talks to the companion add-on in your running Anki, "
        .. "on this computer only. Leave the fields empty to use the "
        .. "port and token the add-on published.",
    ["panel.entities.empty"] = "No Map Entity is loaded",
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
    ["guidance.editorScratchMap"] =
        "Stored against the Map Editor's own scratch map, which it rewrites."
            .. " Relink it to an entity on a saved map, or remove the link.",
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
    -- Anki refused the expression, in its own words. Separate from the
    -- line above because that one sends the player to the connection and
    -- this one sends them back to what they typed.
    ["notice.cardPickerRejected"] = "Anki did not accept the search: %s",
    ["notice.studyStartFailed"] = "Study start failed: %s",
    ["notice.studyRebuildFailed"] = "Study rebuild failed: %s",
    ["notice.studyPauseFailed"] = "Study pause failed: %s",
    ["notice.studyStopFailed"] = "Study stop failed: %s",
    ["notice.studyCancelFailed"] = "Study rebuild cancel failed: %s",
    ["notice.studyStateUnavailable"] =
        "Card states and the next card are unavailable: %s",
    ["notice.spatialOpenFailed"] = "The card did not open: %s",
    ["notice.teleportFailed"] = "Teleport did not happen: %s",
    ["notice.forgetFailed"] = "The Map Entity was not removed: %s",
    ["notice.linkFailed"] = "Spatial Link was not activated: %s",
    ["notice.adoptFailed"] = "The object was not adopted: %s",
    ["notice.entityUpdateFailed"] = "The entity was not changed: %s",
    ["notice.noteUpdateFailed"] = "The card was not changed: %s",
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
}

--- The words for a key.
function Locale.text(key)
    local value = Locale.strings[key]
    if value ~= nil then
        return value
    end

    -- Nothing under that key: show the key rather than nothing, so the gap is
    -- visible instead of appearing as a blank control.
    if not Locale.missing[key] then
        Locale.missing[key] = true
        outputDebugString(
            "[ANKIGTA] missing_string key=" .. tostring(key),
            1
        )
    end
    return key
end

--- The words for a key, with its placeholders filled.
-- The template comes from the table, the arguments never do: a card's text, a
-- Map Entity name or an error category is substituted in as-is. A string whose
-- placeholders do not match the call site is a bug worth seeing, but not one
-- worth taking the interface down for, so the untouched template is shown.
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
        "[ANKIGTA] malformed_string key=" .. tostring(key),
        2
    )
    return template
end

ANKIGTA.Locale = Locale

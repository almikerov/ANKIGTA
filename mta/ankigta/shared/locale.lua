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
    -- The same, for refusal codes nobody has worded yet.
    missingReasons = {},
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
    ["settings.activationType"] = "Activation type",
    ["settings.activationKey"] = "Activation key",
    ["settings.value.automatic"] = "Automatic",
    ["settings.value.key"] = "Key",
    ["settings.showCorona"] = "Show corona",
    ["settings.reviewMode"] = "Review mode",
    -- Said where the mode is chosen rather than left to be discovered. A
    -- player who reads a label, believes they have repeated the card and finds
    -- the scheduler never saw it is worse off than one who has no such mode:
    -- they think they are learning while their schedule quietly diverges from
    -- their memory (ADR 0029). A setting gains a note like this by gaining the
    -- `.note` key; the panel keeps no list of which rows have one.
    ["settings.reviewMode.note"] =
        "Show text draws a line from the note on the object itself. No card"
        .. " is opened and nothing is rated: reading a label writes no"
        .. " repetition.",
    ["settings.textLabelField"] = "Text Label field",
    ["settings.textLabelColor"] = "Text Label colour",
    ["settings.textLabelSize"] = "Text Label size",
    ["settings.textLabelDistance"] = "Text Label distance (m)",
    ["settings.coronaColor"] = "Corona colour",
    ["settings.coronaOpacity"] = "Corona opacity (0–1)",
    ["settings.indicatorMode"] = "Next Card Indicator",
    -- The question the map answers is not "where are my objects" but "which of
    -- them are ready", so the words say state rather than presence.
    ["settings.showEntitiesOnMap"] = "Show every Map Entity on the map",
    ["settings.focusOnSelect"] = "Look at a Map Entity when I select it",
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
    -- A colour is chosen from swatches drawn in the page, and typed as hex for
    -- anything the swatches do not offer.
    ["settings.colorHex"] = "Hex",
    -- A beam, because that is what is drawn: a standing bar over the entity, as
    -- wide as its Activation Zone's radius. It was called a sphere and never
    -- was one -- the sphere is the *zone*, which `Draw radius` draws.
    ["settings.value.beam_and_minimap"] = "Beam and minimap",
    ["settings.value.minimap_only"] = "Minimap only",
    ["settings.value.none"] = "No marker",
    -- Each says which cards the session takes, which is the whole reason
    -- this stopped being a checkbox called "Allow early review".
    ["settings.value.allow_due"] = "Allow due",
    ["settings.value.allow_all"] = "Allow all",
    -- The third: nothing is opened at all, and the object carries a line from
    -- the note instead.
    ["settings.value.show_text"] = "Show text",
    ["settings.error.unknown"] = "Unknown setting",
    ["settings.error.not_a_number"] = "Enter a number",
    ["settings.error.out_of_range"] = "Value is outside the allowed range",
    ["settings.error.not_on_step"] = "Value must fall on the allowed step",
    ["settings.error.too_precise"] = "Too many decimal places",
    ["settings.error.not_a_boolean"] = "Choose on or off",
    ["settings.error.not_a_choice"] = "Choose one of the offered options",
    ["settings.error.not_a_string"] = "Enter text",
    ["settings.error.too_long"] = "That is longer than this field allows",
    ["settings.error.not_a_color"] = "Enter a colour as #rrggbb",
    ["settings.error.secret_not_readable"] =
        "This value is never shown again after it is saved",
    ["settings.error.not_a_placement"] =
        "Stored window placement is not usable",
    ["settings.error.wrong_authority"] = "This setting is owned elsewhere",
    ["settings.error.not_saved"] = "The setting could not be saved",
    ["settings.error.not_a_key"] = "That is not a key ANKIGTA can bind",
    -- Refused rather than allowed to shadow: a key ANKIGTA already answers to
    -- would stop doing what it does today, which is a different feature
    -- breaking for a reason nobody could see.
    ["settings.error.key_in_use"] = "ANKIGTA already uses that key",
    ["settings.error.not_overridable"] =
        "This setting cannot be set on a single link",
    -- Beside every global a link can override: it clears that override
    -- everywhere, so those links follow the global again.
    -- Map Entity, not link: an entity carries its own answer whether or not a
    -- card was ever hung on it, and a Spatial Link is the thing that hangs one.
    -- The count is of what the sweep will really change.
    ["settings.applyToAll"] = "Apply to all",
    ["settings.applyToAll.title"] =
        "Make every Map Entity follow this setting?",
    ["settings.applyToAll.question"] =
        "%d Map Entity have their own \"%s\". Clearing it makes them follow"
        .. " Settings, now and whenever it changes.",
    ["settings.applyToAll.none"] =
        "No Map Entity has its own \"%s\". Nothing to clear.",
    ["settings.applyToAll.confirm"] = "Clear overrides",
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
    -- The guard, not a case the player meets: a row is headed by the name the
    -- Map Editor gave it, which is the `entity_id` it is stored under, and a
    -- stored Map Entity always has one.
    ["f7.entity.unnamed"] = "Unnamed Map Entity",
    -- A cosmetic name replaces the editor's, which is the point -- but the
    -- editor's is the only thing tying the row to what the Map Editor shows,
    -- so the row keeps saying it.
    ["f7.entity.originalName"] = "originally %s",
    -- The pane is on screen whether or not a row is selected, so it has to say
    -- why it is empty rather than being blank.
    ["f7.noSelection"] = "Select a Map Entity to name it,"
        .. " or to say how close you must stand to it.",
    ["f7.radius"] = "Radius (m)",
    -- No answer of its own: what the control shows is the global, and it says
    -- so rather than leaving the player to guess whether it was chosen. One
    -- key, because it is one sentence on six controls -- it was two, and a
    -- third would have arrived with the next overridable setting.
    ["f7.inherited"] = "following Settings",
    ["f7.radiusClearHint"] = "Empty the box to follow Settings again",
    -- Beside `Show corona` rather than in Settings: both answer "what do I see
    -- around this row", and they were on two different screens. This one is
    -- still the player's own way of looking rather than anything the entity
    -- says, so the hint says whose it is and how long it lasts.
    ["f7.drawRadius"] = "Draw radius",
    ["f7.drawRadiusHint"] =
        "Draws the selected row's Activation Zone while F7 is open."
        .. " Yours alone; nobody else sees it.",
    -- What `Draw always` became. That switch made a drawn radius permanent,
    -- which confused a way of looking with a property of the thing looked at.
    -- `f7.showCorona` is the thing's half: a corona standing where it stands,
    -- the same for anyone looking. `f7.drawRadius` is the looking half, and the
    -- two are side by side on the pane again.
    ["f7.activationType"] = "Activation type",
    ["f7.activationKey"] = "Activation key",
    -- Drawn over the entity itself while the player is inside its zone. The
    -- key is substituted in, never looked up here: it is a stored technical
    -- value, and this is the whole of how the player discovers it.
    ["f7.activationPrompt"] = "%s to view",
    -- The way back for a field that offers a choice rather than a number, and
    -- so cannot be emptied: an entry in the list that means "follow Settings".
    ["f7.followSettings"] = "Follow Settings",
    ["f7.showCorona"] = "Show corona",
    ["f7.coronaColor"] = "Corona colour",
    ["f7.coronaOpacity"] = "Corona opacity",
    ["f7.coronaFollowSettings"] = "Follow Settings",
    ["f7.coronaOpacityClearHint"] = "Empty the box to follow Settings again",
    -- The Text Label this row would carry in `Show text`, and what it is
    -- really showing. Present on every row whatever the mode is: the three
    -- overrides are set here, and a player setting them has to see what they
    -- did without changing mode first.
    ["f7.textLabel"] = "Text Label",
    ["f7.textLabel.field"] = "Field",
    ["f7.textLabel.clearHint"] = "Empty the box to follow Settings again",
    ["f7.textLabel.color"] = "Colour",
    ["f7.textLabel.size"] = "Size",
    -- What the object really says, so a row reads as correct only when it is.
    ["f7.textLabel.showing"] = "Showing %s: %s",
    ["f7.textLabel.fallbackMissing"] =
        "This note has no field \"%s\", so it falls back to \"%s\": %s",
    ["f7.textLabel.fallbackWordless"] =
        "Field \"%s\" holds no words, so it falls back to \"%s\": %s",
    ["f7.textLabel.noWords"] = "This note has no words to show.",
    ["f7.textLabel.notCached"] =
        "Not read from Anki yet. Connect the companion once.",
    ["f7.textLabel.notLinked"] = "No card is linked, so there is no label.",
    -- A cap applied quietly reads as "that is all there is", and a player
    -- standing in a room they filled with cards would conclude the rest never
    -- got linked.
    ["textLabel.capped"] = "+%d more Text Labels nearby",
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

--- Why something was refused, in a sentence rather than in its code.
--
-- A refusal travels between the sides as a machine code -- `Locale` is not on
-- the wire, the code is what a log and a bug report want, and the side that
-- draws is the side that words it. What a player was shown, though, was the
-- code: `The entity was not changed: editor_play_test_map`, which tells them
-- nothing about what happened or what to do next.
--
-- One entry per code that a refusal on the panel's own paths can carry:
-- pointing at something and taking it in, hanging a card on it, naming it.
-- The store's and the backup's internal codes are not in here, and a code
-- with no entry is reported through `Locale.missing` the way a missing string
-- is, so the next gap is found by the debug log rather than by a player.
Locale.reasons = {
    -- What the editor's play-test leaves nothing to link against. Which of
    -- them it is matters: two of the three are fixed by stopping the test,
    -- and the third by putting the object back.
    ["play_test_without_open_map"] =
        "The Map Editor is play-testing but is not holding a map, so there is"
        .. " no saved object to link this card to. Stop the test and open the"
        .. " map again.",
    ["play_test_of_another_map"] =
        "This play-test is of a different map from the one the Map Editor now"
        .. " has open, so nothing here outlives the test. Stop the test and"
        .. " press Test again.",
    ["play_test_copy_has_no_original"] =
        "The Map Editor is not holding the object this play-test copy came"
        .. " from — it was deleted, or it is not on the map that is open — so"
        .. " a link made here would point at something that stops existing"
        .. " when the test does.",
    ["play_test_original_not_unique"] =
        "The Map Editor is holding more than one object under this name, so"
        .. " ANKIGTA cannot tell which of them the play-test copy came from.",
    -- Pointing at something, and what it turned out to be.
    ["entity_not_an_element"] = "That is not something in the world.",
    ["entity_not_managed"] =
        "That is the Map Editor's own drawing of an object rather than the"
        .. " object itself. Aim at the object.",
    ["entity_not_streamed"] =
        "That object is too far away to be loaded. Go closer and try again.",
    ["entity_no_longer_in_the_world"] =
        "That object is no longer in the world. Refresh the list.",
    ["entity_has_no_durable_id"] =
        "That object has no position ANKIGTA can write down, so it cannot be"
        .. " found again after a restart.",
    ["target_type_not_supported"] =
        "ANKIGTA can only hold a card on an object, a vehicle, a ped or a"
        .. " marker.",
    ["entity_already_adopted"] =
        "ANKIGTA already holds this object. Use its own row to link a card to"
        .. " it.",
    ["entity_already_linked"] =
        "This Map Entity already has a card. Use Replace card to change it.",
    ["entity_runtime_not_found"] =
        "Nothing in the world carries this Map Entity's identity right now.",
    ["entity_runtime_not_unique"] =
        "Two things in front of you carry this Map Entity's identity, so"
        .. " ANKIGTA will not guess which of them you mean.",
    ["entity_missing"] = "ANKIGTA holds no such Map Entity.",
    ["map_entity_not_loaded"] =
        "The map this Map Entity belongs to is not loaded.",
    ["map_entity_not_found"] = "ANKIGTA holds no such Map Entity.",
    ["map_entity_ambiguous"] =
        "Two maps hold a Map Entity under this name, so ANKIGTA will not"
        .. " guess which of them you mean.",
    ["map_identity_not_unique"] =
        "This map carries more than one ANKIGTA identity. Remove the extra"
        .. " one with the Map Editor.",
    ["persistent_map_identity_conflict"] =
        "This map already carries a different ANKIGTA identity.",
    ["persistent_entity_identity_conflict"] =
        "This object already carries a different ANKIGTA identity.",
    -- Hanging a card on it.
    ["invalid_anki_card_identity"] = "No Anki card was chosen.",
    ["invalid_card_identity"] = "No Anki card was chosen.",
    ["card_missing_requires_replace"] =
        "The linked card is gone from Anki. Use Replace card.",
    ["pending_map_save"] =
        "This link is waiting for the map to be saved with the stock Map"
        .. " Editor.",
    ["pending_map_save_exists"] =
        "This Map Entity is already waiting for the map to be saved.",
    ["pending_map_save_not_found"] =
        "Nothing here is waiting for the map to be saved.",
    ["identity_collision"] =
        "Two maps carry this identity, so ANKIGTA is waiting for you to say"
        .. " which is the original.",
    ["link_not_active"] = "There is no Spatial Link here to change.",
    ["invalid_pending_request"] =
        "ANKIGTA could not read what was being linked.",
    -- The map's own files.
    ["no_loaded_map"] = "The stock Map Editor has no map open.",
    ["ambiguous_map_file"] =
        "This resource declares more than one map file, so ANKIGTA cannot"
        .. " tell which one to write into.",
    ["saved_map_not_readable"] =
        "The saved map file could not be read. Save the map with the stock"
        .. " Map Editor and try again.",
    ["object_not_managed_by_stock_editor"] =
        "That object is not one the stock Map Editor is holding.",
    ["vehicle_not_managed_by_stock_editor"] =
        "That vehicle is not one the stock Map Editor is holding.",
    ["ped_not_managed_by_stock_editor"] =
        "That ped is not one the stock Map Editor is holding.",
    ["ankigta_edf_not_loaded"] =
        "The Map Editor is running without ANKIGTA's element definition."
        .. " Restart the editor.",
    ["editor_import_failed"] =
        "The stock Map Editor refused ANKIGTA's map identity.",
    ["imported_map_identity_not_found"] =
        "The map identity ANKIGTA added did not arrive in the open map.",
    ["ambiguous_map_identity"] =
        "This map carries more than one ANKIGTA identity. Remove the extra"
        .. " one with the Map Editor.",
    -- Who is asking.
    ["authentication_required"] = "Log in to use ANKIGTA.",
    ["forbidden"] = "Your account is not allowed to use ANKIGTA.",
    ["invalid_player"] = "ANKIGTA does not know who asked for this.",
    -- The store, where a player can still do something about it.
    ["storage_unavailable"] =
        "ANKIGTA's database is not open, so nothing can be saved.",
    ["invalid_map_entity"] = "ANKIGTA could not read what was being saved.",
    ["invalid_entity_metadata"] =
        "ANKIGTA could not read what was being changed.",
}

--- Which notice keys carry a machine code rather than something a person
--- wrote, derived from the key rather than listed.
--
-- A notice that names a failure ends in `Failed` or `Unavailable`, and the one
-- thing it substitutes is why. Everything else substitutes a name, a count or
-- somebody else's words -- Anki's rejected search, a restored file -- and must
-- pass through untouched.
local function carriesReason(key)
    return key:sub(-6) == "Failed" or key:sub(-11) == "Unavailable"
end

--- What ANKIGTA has to say about itself is never a reason to word.
local NOT_A_REASON = {["nil"] = true, ["true"] = true, ["false"] = true}

--- The code inside a refusal, and whatever it was said about.
--
-- Two shapes, because two exist: `map_entity_not_loaded`, and the same with a
-- subject after it -- `entity_runtime_not_unique: object (bin) (1) (2
-- copies)`. The second is the one that most needed wording and the one a
-- pattern matching only the first would have walked straight past.
local function splitReason(value)
    if type(value) ~= "string" or value == "" or NOT_A_REASON[value] then
        return nil
    end
    if value:match("^[a-z][a-z0-9_]*$") then
        return value, nil
    end
    return value:match("^([a-z][a-z0-9_]*):%s*(.+)$")
end

--- The sentence for a refusal code.
--
-- The code back where there is no sentence for it, so a refusal is never
-- swallowed -- and reported once, so the gap is found the way a missing
-- string is rather than by a player reading `map_entity_not_loaded`.
function Locale.reason(code)
    local head, subject = splitReason(code)
    if not head then
        return code == nil and "" or tostring(code)
    end
    local said = Locale.reasons[head]
    if said == nil then
        if not Locale.missingReasons[head] then
            Locale.missingReasons[head] = true
            outputDebugString(
                "[ANKIGTA] missing_reason code=" .. tostring(head),
                1
            )
        end
        return tostring(code)
    end
    if subject then
        -- The subject is a Map Entity's own name, which is the player's word
        -- rather than a machine's, so it is kept beside the sentence.
        return said .. " (" .. subject .. ")"
    end
    return said
end

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
-- The template comes from the table, and so does the *reason* a failure notice
-- carries -- but nothing else does: a card's text, a Map Entity name or a
-- count is substituted in as-is. A string whose placeholders do not match the
-- call site is a bug worth seeing, but not one worth taking the interface down
-- for, so the untouched template is shown.
--
-- Worded here rather than at each call site, so a surface that shows a refusal
-- cannot forget to: there are two of them for one notice, and the next one to
-- be written would have shown the code again.
function Locale.format(key, ...)
    local template = Locale.text(key)
    local count = select("#", ...)
    if count == 0 then
        return template
    end
    local arguments = {...}
    if carriesReason(key) then
        for index = 1, count do
            arguments[index] = Locale.reason(arguments[index])
        end
    end
    local ok, formatted = pcall(string.format, template, unpack(arguments, 1, count))
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

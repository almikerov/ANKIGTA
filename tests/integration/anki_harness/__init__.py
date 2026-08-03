from __future__ import annotations

import json
import os
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import aqt
from anki.decks import UpdateDeckConfigs
from aqt import gui_hooks, mw
from aqt.qt import QTimer


EVIDENCE_DIR = Path(os.environ["ANKIGTA_TICKET01_EVIDENCE"])
PHASE = os.environ["ANKIGTA_TICKET01_PHASE"]
SESSION_NAME = "ANKIGTA Session"

stage = "initial"
profile_name = ""
before_snapshot: dict[str, Any] | None = None
open_response: dict[str, Any] | None = None
card_search_response: dict[str, Any] | None = None
closing_response: dict[str, Any] | None = None
after_unload_response: dict[str, Any] | None = None


def write_evidence(name: str, payload: object) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / name
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def finish_process() -> None:
    QTimer.singleShot(250, mw.app.quit)


def deck_configuration() -> Any:
    deck_id = mw.col.decks.get_current_id()
    return mw.col.decks.get_deck_configs_for_update(deck_id)


def semantic_snapshot() -> dict[str, Any]:
    deck_names = sorted(
        item.name for item in mw.col.decks.all_names_and_ids(skip_empty_default=False)
    )
    return {
        "cards": [int(card_id) for card_id in mw.col.find_cards("")],
        "notes": [int(note_id) for note_id in mw.col.find_notes("")],
        "deckNames": deck_names,
        "fsrsEnabled": bool(deck_configuration().fsrs),
        "v3Scheduler": bool(mw.col.v3_scheduler()),
    }


def enable_fsrs_for_disposable_profile() -> None:
    current = deck_configuration()
    if bool(current.fsrs):
        return
    deck_id = mw.col.decks.get_current_id()
    selected = [
        item.config
        for item in current.all_config
        if int(item.config.id) == int(current.current_deck.config_id)
    ]
    if len(selected) != 1:
        raise RuntimeError(f"expected one current deck config, got {len(selected)}")
    mw.col.decks.update_deck_configs(
        UpdateDeckConfigs(
            target_deck_id=deck_id,
            configs=selected,
            card_state_customizer=current.card_state_customizer,
            limits=current.current_deck.limits,
            new_cards_ignore_review_limit=current.new_cards_ignore_review_limit,
            fsrs=True,
            apply_all_parent_limits=current.apply_all_parent_limits,
            fsrs_reschedule=False,
            fsrs_health_check=current.fsrs_health_check,
        )
    )


def setup_profile() -> None:
    enable_fsrs_for_disposable_profile()
    write_evidence(
        "setup.json",
        {
            "ankiVersion": aqt.appVersion,
            "snapshot": semantic_snapshot(),
        },
    )
    finish_process()


def control_request(
    addon: Any,
    path: str,
    request_id: str,
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://{addon.server.host}:{addon.server.port}{path}",
        data=json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": request_id,
                **(payload or {}),
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            status = response.status
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        status = error.code
        payload = json.loads(error.read())
    return {"status": status, "body": payload}


def health_request(addon: Any, request_id: str) -> dict[str, Any]:
    return control_request(addon, "/v1/health", request_id)


def card_search_request(addon: Any, request_id: str) -> dict[str, Any]:
    return control_request(
        addon,
        "/v1/cards/search",
        request_id,
        {"query": "", "deckFilter": False, "page": 0, "pageSize": 50},
    )


def begin_verification() -> None:
    global before_snapshot, card_search_response, open_response, profile_name, stage
    import ankigta_companion

    addon = ankigta_companion.addon
    if addon is None:
        raise RuntimeError("production add-on did not start")
    profile_name = mw.pm.name
    before_snapshot = semantic_snapshot()
    open_response = health_request(addon, "real-open")
    card_search_response = card_search_request(addon, "real-card-search")
    stage = "closing"

    def after_unload() -> None:
        def observe_closed_collection() -> None:
            global after_unload_response, stage
            after_unload_response = health_request(addon, "real-after-unload")
            mw.pm.load(profile_name)
            stage = "reopening"
            mw.loadProfile()

        QTimer.singleShot(25, observe_closed_collection)

    mw.unloadProfile(after_unload)


def on_profile_will_close() -> None:
    global closing_response
    if PHASE != "verify" or stage != "closing":
        return
    import ankigta_companion

    closing_response = health_request(ankigta_companion.addon, "real-closing")


def complete_verification() -> None:
    global stage
    import ankigta_companion

    addon = ankigta_companion.addon
    after_snapshot = semantic_snapshot()
    reopened_response = health_request(addon, "real-reopened")
    addon.stop()
    listener_released = False
    try:
        health_request(addon, "real-after-addon-unload")
    except OSError:
        listener_released = True
    stage = "finished"
    write_evidence(
        "verification.json",
        {
            "ankiVersion": aqt.appVersion,
            "beforeSnapshot": before_snapshot,
            "afterSnapshot": after_snapshot,
            "open": open_response,
            "cardSearch": card_search_response,
            "closing": closing_response,
            "afterUnload": after_unload_response,
            "reopened": reopened_response,
            "listenerReleased": listener_released,
            "ankigtaSessionAbsent": SESSION_NAME
            not in after_snapshot["deckNames"],
        },
    )
    finish_process()


def on_profile_did_open() -> None:
    if PHASE == "setup":
        QTimer.singleShot(0, lambda: guarded(setup_profile))
    elif stage == "initial":
        QTimer.singleShot(0, lambda: guarded(begin_verification))
    elif stage == "reopening":
        QTimer.singleShot(0, lambda: guarded(complete_verification))


def fail() -> None:
    write_evidence(
        f"failure-{PHASE}.json",
        {
            "phase": PHASE,
            "stage": stage,
            "traceback": traceback.format_exc(),
        },
    )
    finish_process()


def guarded(action: Callable[[], None]) -> None:
    try:
        action()
    except Exception:
        fail()


gui_hooks.profile_will_close.append(on_profile_will_close)
gui_hooks.profile_did_open.append(on_profile_did_open)

if mw.col is not None:
    on_profile_did_open()

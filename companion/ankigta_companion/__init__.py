"""ANKIGTA companion add-on entry point."""

from __future__ import annotations

import atexit
from pathlib import Path

from .collection_identity import (
    CollectionCopyDecision,
    CollectionIdentityService,
    CollectionIdentityState,
)
from .lifecycle import CompanionAddon


addon: CompanionAddon | None = None
collection_settings_action: object | None = None


def _show_collection_identity_settings() -> None:
    from aqt import mw
    from aqt.qt import QMessageBox

    if addon is None or mw.col is None:
        QMessageBox.information(
            mw,
            "ANKIGTA",
            "Сначала откройте коллекцию Anki.",
        )
        return
    identity = addon.current_collection_identity()
    if identity is None or identity.collection_uuid is None:
        QMessageBox.warning(
            mw,
            "ANKIGTA",
            "Коллекция не привязана: identity недоступна.",
        )
        return
    if identity.state is CollectionIdentityState.ERROR:
        QMessageBox.critical(
            mw,
            "ANKIGTA",
            "Не удалось безопасно сохранить identity коллекции. "
            "Коллекция остаётся unbound.",
        )
        return
    if identity.state is CollectionIdentityState.COPY_DECISION_REQUIRED:
        dialog = QMessageBox(mw)
        dialog.setWindowTitle("ANKIGTA — Collection Copy Decision")
        dialog.setText(
            "Обнаружена коллекция с ранее зарегистрированным UUID. "
            "Выберите, является ли она прежней коллекцией или новой копией."
        )
        previous_button = dialog.addButton(
            "Это прежняя коллекция",
            QMessageBox.ButtonRole.ActionRole,
        )
        new_copy_button = dialog.addButton(
            "Это новая копия",
            QMessageBox.ButtonRole.ActionRole,
        )
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(new_copy_button)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is previous_button:
            decision = CollectionCopyDecision.PREVIOUS_COLLECTION
        elif clicked is new_copy_button:
            decision = CollectionCopyDecision.NEW_COPY
        else:
            return
        addon.decide_current_collection_copy(
            identity.collection_uuid,
            decision,
        )
        return
    if identity.state is CollectionIdentityState.BOUND:
        QMessageBox.information(
            mw,
            "ANKIGTA",
            f"Эта коллекция уже выбрана как Bound Anki Collection.\n"
            f"UUID: {identity.collection_uuid}",
        )
        return

    prompt = (
        "Открыта другая коллекция. Обучение ANKIGTA приостановлено.\n\n"
        "Выбрать текущую коллекцию как новую Bound Anki Collection?"
        if identity.state is CollectionIdentityState.WRONG_COLLECTION
        else "Выбрать текущую коллекцию как Bound Anki Collection?"
    )
    answer = QMessageBox.question(
        mw,
        "ANKIGTA — Bound Anki Collection",
        prompt,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer is QMessageBox.StandardButton.Yes:
        addon.bind_current_collection(identity.collection_uuid)


def _register_collection_identity_settings() -> None:
    global collection_settings_action
    from aqt import mw
    from aqt.qt import QAction

    action = QAction(
        "ANKIGTA: Bound Anki Collection…",
        mw,
    )
    action.triggered.connect(_show_collection_identity_settings)
    mw.form.menuTools.addAction(action)
    collection_settings_action = action


def _start_inside_anki() -> None:
    global addon
    from aqt import appVersion, gui_hooks, mw
    from aqt.qt import QTimer

    addon = CompanionAddon(
        main_window=mw,
        hooks=gui_hooks,
        anki_version=appVersion,
        defer=lambda delay_ms, action: QTimer.singleShot(delay_ms, action),
        run_on_main=mw.taskman.run_on_main,
        identity_service=CollectionIdentityService(
            Path(mw.addonManager.addonsFolder(__name__))
            / "user_files"
            / "collection-registry.json"
        ),
    )
    addon.start()
    _register_collection_identity_settings()
    atexit.register(addon.stop)


try:
    import aqt
except ModuleNotFoundError as error:
    if error.name != "aqt":
        raise
else:
    _start_inside_anki()

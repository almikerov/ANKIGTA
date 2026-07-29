from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .collection_identity import (
    CollectionCopyDecision,
    CollectionIdentityState,
)

if TYPE_CHECKING:
    from .lifecycle import CompanionAddon


def show_collection_identity_settings(addon: CompanionAddon | None) -> None:
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
    if identity.state is CollectionIdentityState.WRONG_COLLECTION:
        QMessageBox.information(
            mw,
            "ANKIGTA — Bound Anki Collection",
            "Открыта другая коллекция. Обучение ANKIGTA приостановлено.\n\n"
            "Откройте ранее выбранную Bound Anki Collection.",
        )
        return

    answer = QMessageBox.question(
        mw,
        "ANKIGTA — Bound Anki Collection",
        "Выбрать текущую коллекцию как Bound Anki Collection?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer is QMessageBox.StandardButton.Yes:
        addon.bind_current_collection(identity.collection_uuid)


def register_collection_identity_settings(
    addon_provider: Callable[[], CompanionAddon | None],
) -> object:
    from aqt import mw
    from aqt.qt import QAction

    action = QAction(
        "ANKIGTA: Bound Anki Collection…",
        mw,
    )
    action.triggered.connect(
        lambda _checked=False: show_collection_identity_settings(addon_provider())
    )
    mw.form.menuTools.addAction(action)
    return action

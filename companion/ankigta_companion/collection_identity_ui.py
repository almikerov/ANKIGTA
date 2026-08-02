from __future__ import annotations

from typing import TYPE_CHECKING

from .collection_identity import (
    CollectionCopyDecision,
    CollectionIdentityObservation,
    CollectionIdentityState,
)

if TYPE_CHECKING:
    from .lifecycle import CompanionAddon


def announce_collection_identity(
    addon: CompanionAddon | None,
    identity: CollectionIdentityObservation,
) -> None:
    """Speak only when the state needs a person.

    Adopting the first collection is silent, so the states worth a dialog are
    the three that cannot be answered without one: a copy that has to be told
    apart from its original, a different collection than the one being studied,
    and an identity that could not be written down.
    """
    if identity.state not in {
        CollectionIdentityState.COPY_DECISION_REQUIRED,
        CollectionIdentityState.WRONG_COLLECTION,
        CollectionIdentityState.ERROR,
    }:
        return
    show_collection_identity_settings(addon)


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

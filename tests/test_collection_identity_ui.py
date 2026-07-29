from __future__ import annotations

import sys
from types import SimpleNamespace

from ankigta_companion.collection_identity import (
    CollectionIdentityObservation,
    CollectionIdentityState,
)
from ankigta_companion.collection_identity_ui import (
    show_collection_identity_settings,
)


class WrongCollectionAddon:
    def __init__(self) -> None:
        self.bind_calls: list[str] = []

    def current_collection_identity(self) -> CollectionIdentityObservation:
        return CollectionIdentityObservation(
            state=CollectionIdentityState.WRONG_COLLECTION,
            collection_uuid="d384e4c5-a509-43a8-b801-e50bff4f90e8",
        )

    def bind_current_collection(self, collection_uuid: str) -> None:
        self.bind_calls.append(collection_uuid)


def test_wrong_collection_ui_asks_to_open_the_bound_collection(
    monkeypatch: object,
) -> None:
    messages: list[str] = []

    class FakeMessageBox:
        @staticmethod
        def information(_parent: object, _title: str, message: str) -> None:
            messages.append(message)

    monkeypatch.setitem(  # type: ignore[attr-defined]
        sys.modules,
        "aqt",
        SimpleNamespace(mw=SimpleNamespace(col=object())),
    )
    monkeypatch.setitem(  # type: ignore[attr-defined]
        sys.modules,
        "aqt.qt",
        SimpleNamespace(QMessageBox=FakeMessageBox),
    )
    addon = WrongCollectionAddon()

    show_collection_identity_settings(addon)  # type: ignore[arg-type]

    assert messages == [
        "Открыта другая коллекция. Обучение ANKIGTA приостановлено.\n\n"
        "Откройте ранее выбранную Bound Anki Collection."
    ]
    assert addon.bind_calls == []

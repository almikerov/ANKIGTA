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


def test_only_a_state_that_needs_a_person_raises_a_dialog() -> None:
    """The menu item is gone, so this predicate is the whole trigger.

    Adopting the first collection is silent. Speaking on every observation
    would have replaced a button nobody pressed with a dialog everybody has to
    dismiss.
    """
    from ankigta_companion.collection_identity_ui import (
        announce_collection_identity,
    )

    shown: list[CollectionIdentityState] = []

    def record(_addon: object, identity: object) -> None:
        shown.append(identity.state)  # type: ignore[attr-defined]

    import ankigta_companion.collection_identity_ui as ui

    original = ui.show_collection_identity_settings
    ui.show_collection_identity_settings = (  # type: ignore[assignment]
        lambda addon: record(addon, current[0])
    )
    current: list[CollectionIdentityObservation] = []
    try:
        for state in CollectionIdentityState:
            identity = CollectionIdentityObservation(
                state=state,
                collection_uuid="11111111-1111-4111-8111-111111111111",
            )
            current[:] = [identity]
            announce_collection_identity(None, identity)
    finally:
        ui.show_collection_identity_settings = original  # type: ignore[assignment]

    assert set(shown) == {
        CollectionIdentityState.COPY_DECISION_REQUIRED,
        CollectionIdentityState.WRONG_COLLECTION,
        CollectionIdentityState.ERROR,
    }
    assert CollectionIdentityState.BOUND not in shown

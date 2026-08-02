"""Editing the note behind a card.

This is the only place in the companion that writes to the user's collection
outside of rating, so the tests here are mostly about what it refuses.
"""

from __future__ import annotations

from typing import Any

import pytest

from ankigta_companion.cards import CardPickerError
from ankigta_companion.collection_identity import (
    AnkiCardIdentity,
    CollectionIdentityObservation,
    CollectionIdentityState,
)
from ankigta_companion.notes import MAX_FIELD_LENGTH, MAX_TAGS, NoteEditorService

COLLECTION = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


class FakeNote:
    def __init__(self, fields: dict[str, str], tags: list[str]) -> None:
        self.id = 77
        self._fields = dict(fields)
        self.tags = list(tags)

    def keys(self) -> list[str]:
        return list(self._fields)

    def items(self) -> list[tuple[str, str]]:
        return list(self._fields.items())

    def __getitem__(self, name: str) -> str:
        return self._fields[name]

    def __setitem__(self, name: str, value: str) -> None:
        self._fields[name] = value


class FakeCard:
    def __init__(self, note: FakeNote) -> None:
        self._note = note

    def note(self) -> FakeNote:
        return self._note


class FakeCollection:
    def __init__(self, note: FakeNote) -> None:
        self.note = note
        self.updates = 0

    def get_card(self, card_id: int) -> FakeCard | None:
        return FakeCard(self.note) if card_id == 1001 else None

    def update_note(self, note: Any) -> None:
        self.updates += 1


def editor(collection: FakeCollection, *, uuid: str = COLLECTION) -> NoteEditorService:
    return NoteEditorService(
        lambda: CollectionIdentityObservation(
            CollectionIdentityState.BOUND, uuid
        ),
        lambda: collection,  # type: ignore[arg-type]
    )


@pytest.fixture
def collection() -> FakeCollection:
    return FakeCollection(
        FakeNote({"Front": "hablar", "Back": "to speak"}, ["spanish"])
    )


def test_a_field_is_written_and_read_back_from_the_note(
    collection: FakeCollection,
) -> None:
    update = editor(collection).update(
        AnkiCardIdentity(COLLECTION, 1001),
        fields=[("Back", "to talk")],
        tags=["spanish", "verbs"],
    )

    assert collection.note["Back"] == "to talk"
    assert collection.updates == 1
    # The answer is what the note says now, not what the request said.
    assert dict((f.name, f.value) for f in update.fields)["Back"] == "to talk"
    assert update.tags == ("spanish", "verbs")


def test_a_field_the_note_does_not_have_is_refused_rather_than_dropped(
    collection: FakeCollection,
) -> None:
    """Ignoring it would report success for a change that did not happen."""
    with pytest.raises(CardPickerError) as refused:
        editor(collection).update(
            AnkiCardIdentity(COLLECTION, 1001),
            fields=[("Middle", "nothing")],
            tags=[],
        )

    assert refused.value.category == "unknown_note_field"
    assert collection.updates == 0


def test_a_card_from_another_collection_is_refused(
    collection: FakeCollection,
) -> None:
    """A stale panel must not write into whatever happens to be open now."""
    with pytest.raises(CardPickerError) as refused:
        editor(collection).update(
            AnkiCardIdentity(OTHER, 1001),
            fields=[("Front", "x")],
            tags=[],
        )

    assert refused.value.category == "collection_identity_conflict"
    assert collection.updates == 0


def test_a_card_that_is_gone_is_refused(collection: FakeCollection) -> None:
    with pytest.raises(CardPickerError) as refused:
        editor(collection).update(
            AnkiCardIdentity(COLLECTION, 4242), fields=[], tags=[]
        )

    assert refused.value.category == "card_missing"


def test_a_tag_with_a_space_in_it_is_two_tags_wearing_a_disguise(
    collection: FakeCollection,
) -> None:
    with pytest.raises(CardPickerError) as refused:
        editor(collection).update(
            AnkiCardIdentity(COLLECTION, 1001),
            fields=[],
            tags=["one two"],
        )

    assert refused.value.category == "invalid_note_tags"
    assert collection.updates == 0


def test_blank_tags_are_dropped_and_repeats_collapse(
    collection: FakeCollection,
) -> None:
    update = editor(collection).update(
        AnkiCardIdentity(COLLECTION, 1001),
        fields=[],
        tags=["  spanish  ", "", "spanish", "verbs"],
    )

    assert update.tags == ("spanish", "verbs")


def test_the_same_field_twice_is_refused(collection: FakeCollection) -> None:
    """Two values for one field is a request with no single meaning."""
    with pytest.raises(CardPickerError) as refused:
        editor(collection).update(
            AnkiCardIdentity(COLLECTION, 1001),
            fields=[("Front", "a"), ("Front", "b")],
            tags=[],
        )

    assert refused.value.category == "invalid_note_fields"
    assert collection.updates == 0


def test_an_oversized_field_is_refused(collection: FakeCollection) -> None:
    with pytest.raises(CardPickerError) as refused:
        editor(collection).update(
            AnkiCardIdentity(COLLECTION, 1001),
            fields=[("Front", "x" * (MAX_FIELD_LENGTH + 1))],
            tags=[],
        )

    assert refused.value.category == "note_field_too_long"
    assert collection.updates == 0


def test_too_many_tags_is_refused(collection: FakeCollection) -> None:
    with pytest.raises(CardPickerError) as refused:
        editor(collection).update(
            AnkiCardIdentity(COLLECTION, 1001),
            fields=[],
            tags=[f"tag{index}" for index in range(MAX_TAGS + 1)],
        )

    assert refused.value.category == "too_many_tags"


def test_nothing_is_written_when_no_collection_is_bound(
    collection: FakeCollection,
) -> None:
    service = NoteEditorService(lambda: None, lambda: collection)  # type: ignore[arg-type]

    with pytest.raises(CardPickerError) as refused:
        service.update(AnkiCardIdentity(COLLECTION, 1001), fields=[], tags=[])

    assert refused.value.category == "collection_unavailable"
    assert collection.updates == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

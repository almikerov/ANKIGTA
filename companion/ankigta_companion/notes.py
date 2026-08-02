"""Editing the note behind a card.

Kept apart from `cards.py`, which says it is read-only and is. This is the only
place in the companion that writes to the user's collection outside of rating a
card, and that is worth being able to see at a glance.

What it will not do: change which note type a note has, create a note, or
delete one. Each of those is a different kind of risk -- a note type change
rewrites every note of that type's shape, and a delete takes the review history
with it -- and none of them is needed to fix a typo on a card you just linked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from .cards import CardPickerError, NoteField, NoteLike
from .collection_identity import AnkiCardIdentity, CollectionIdentityObservation

#: Anki's own limit is far higher, but a field arriving from a game panel that
#: is longer than this is a mistake or an attack rather than a note.
MAX_FIELD_LENGTH = 131072
MAX_TAG_LENGTH = 256
MAX_TAGS = 64


class EditableNote(NoteLike, Protocol):
    def __setitem__(self, name: str, value: str) -> None: ...


class EditableCard(Protocol):
    def note(self) -> EditableNote: ...


class EditableCollection(Protocol):
    def get_card(self, card_id: int) -> EditableCard | None: ...

    def update_note(self, note: EditableNote) -> object: ...


@dataclass(frozen=True)
class NoteUpdate:
    """What was actually written, read back from the note after the write."""

    note_id: int
    fields: tuple[NoteField, ...]
    tags: tuple[str, ...]


IdentityProvider = Callable[[], CollectionIdentityObservation | None]
CollectionProvider = Callable[[], EditableCollection | None]


class NoteEditorService:
    """Change the fields and tags of a note that already exists."""

    def __init__(
        self,
        identity_provider: IdentityProvider,
        collection_provider: CollectionProvider,
    ) -> None:
        self._identity_provider = identity_provider
        self._collection_provider = collection_provider

    def update(
        self,
        identity: AnkiCardIdentity,
        *,
        fields: Sequence[tuple[str, str]],
        tags: Sequence[str],
    ) -> NoteUpdate:
        """Write these fields and tags onto the note behind this card.

        The card is named by collection *and* id, and the collection has to be
        the bound one. Editing by card id alone would let a stale panel write
        into whatever collection happens to be open now.

        Only fields the note already has are written. A name the note does not
        know is refused rather than ignored: silently dropping it would report
        success for a change that did not happen.
        """
        collection = self._bound_collection(identity)
        try:
            card = collection.get_card(identity.card_id)
        except Exception as error:
            raise CardPickerError(
                "note_update_failed",
                "Anki rejected the card read",
            ) from error
        if card is None:
            raise CardPickerError(
                "card_missing",
                "card is missing from the bound collection",
            )
        note = card.note()
        known = self._field_names(note)

        for name, value in self._checked_fields(fields, known):
            note[name] = value
        note.tags = list(self._checked_tags(tags))

        try:
            collection.update_note(note)
        except Exception as error:
            raise CardPickerError(
                "note_update_failed",
                "Anki refused the note update",
            ) from error
        return self._read_back(note)

    # --- checking ----------------------------------------------------------

    @staticmethod
    def _field_names(note: EditableNote) -> tuple[str, ...]:
        try:
            return tuple(str(name) for name in note.keys())
        except Exception as error:
            raise CardPickerError(
                "note_shape_unknown",
                "the note's fields could not be read",
            ) from error

    @staticmethod
    def _checked_fields(
        fields: Sequence[tuple[str, str]],
        known: Sequence[str],
    ) -> tuple[tuple[str, str], ...]:
        checked: list[tuple[str, str]] = []
        seen: set[str] = set()
        for entry in fields:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise CardPickerError(
                    "invalid_note_fields",
                    "each field must be a name and a value",
                )
            name, value = entry
            if not isinstance(name, str) or not isinstance(value, str):
                raise CardPickerError(
                    "invalid_note_fields",
                    "field names and values must be strings",
                )
            if name not in known:
                raise CardPickerError(
                    "unknown_note_field",
                    f"this note has no field named {name!r}",
                )
            if name in seen:
                raise CardPickerError(
                    "invalid_note_fields",
                    f"field {name!r} was given twice",
                )
            if len(value) > MAX_FIELD_LENGTH:
                raise CardPickerError(
                    "note_field_too_long",
                    "a field value was longer than the limit",
                )
            seen.add(name)
            checked.append((name, value))
        return tuple(checked)

    @staticmethod
    def _checked_tags(tags: Sequence[str]) -> tuple[str, ...]:
        if len(tags) > MAX_TAGS:
            raise CardPickerError("too_many_tags", "too many tags")
        checked: list[str] = []
        for tag in tags:
            if not isinstance(tag, str):
                raise CardPickerError("invalid_note_tags", "tags must be strings")
            # Anki separates tags by spaces, so a tag containing one is two
            # tags wearing a disguise.
            cleaned = tag.strip()
            if cleaned == "":
                continue
            if " " in cleaned or len(cleaned) > MAX_TAG_LENGTH:
                raise CardPickerError(
                    "invalid_note_tags",
                    "a tag may not contain a space or exceed the length limit",
                )
            if cleaned not in checked:
                checked.append(cleaned)
        return tuple(checked)

    # --- reading back ------------------------------------------------------

    @staticmethod
    def _read_back(note: EditableNote) -> NoteUpdate:
        """What the note says now, not what it was asked to say.

        Anki normalises tags and may rewrite a field on save, so answering with
        the request would report a change the collection did not make.
        """
        try:
            note_id = int(note.id)
        except Exception:
            note_id = 0
        try:
            pairs = tuple(
                NoteField(name=str(name), value=str(value))
                for name, value in note.items()
            )
        except Exception:
            pairs = ()
        try:
            tags = tuple(str(tag) for tag in note.tags)
        except Exception:
            tags = ()
        return NoteUpdate(note_id=note_id, fields=pairs, tags=tags)

    def _bound_collection(self, identity: AnkiCardIdentity) -> EditableCollection:
        observation = self._identity_provider()
        if observation is None or not observation.collection_uuid:
            raise CardPickerError(
                "collection_unavailable",
                "no collection is bound",
            )
        if identity.collection_uuid != observation.collection_uuid:
            raise CardPickerError(
                "collection_identity_conflict",
                "the card belongs to a different collection",
            )
        collection = self._collection_provider()
        if collection is None:
            raise CardPickerError(
                "collection_unavailable",
                "the collection is not open",
            )
        return collection

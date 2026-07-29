from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from ankigta_companion.collection_identity import (
    AnkiCardIdentity,
    COLLECTION_UUID_CONFIG_KEY,
    CollectionCopyDecision,
    CollectionIdentityService,
    CollectionIdentityState,
)


@dataclass
class FakeCollection:
    config: dict[str, object] = field(default_factory=dict)
    fail_assignment: bool = False

    def get_config(self, key: str, default: object | None = None) -> object:
        return self.config.get(key, default)

    def set_config(
        self,
        key: str,
        value: object,
        *,
        undoable: bool = False,
    ) -> object:
        assert undoable is False
        if self.fail_assignment:
            raise OSError("injected collection config failure")
        self.config[key] = value
        return object()


def test_equal_numeric_card_ids_in_different_collections_are_distinct() -> None:
    card_in_a = AnkiCardIdentity(
        collection_uuid="2a7aae27-9655-4140-b23d-308209f2e433",
        card_id=1785280605920,
    )
    card_in_b = AnkiCardIdentity(
        collection_uuid="54b32861-9c39-41ac-8553-60c28fc2d106",
        card_id=1785280605920,
    )

    assert card_in_a != card_in_b


def test_first_open_atomically_assigns_a_persistent_collection_uuid(
    tmp_path: Path,
) -> None:
    assigned_uuid = UUID("c26d12be-04da-43d4-a2af-2e7b183f32c6")
    collection = FakeCollection()
    locator = tmp_path / "Profile A" / "collection.anki2"
    locator.parent.mkdir()
    locator.touch()
    registry_path = tmp_path / "addon" / "collection-registry.json"

    first_service = CollectionIdentityService(
        registry_path,
        uuid_factory=lambda: assigned_uuid,
    )
    first = first_service.observe_open_collection(collection, locator)

    restarted_service = CollectionIdentityService(registry_path)
    restarted = restarted_service.observe_open_collection(collection, locator)

    assert collection.config[COLLECTION_UUID_CONFIG_KEY] == str(assigned_uuid)
    assert first.collection_uuid == str(assigned_uuid)
    assert restarted.collection_uuid == str(assigned_uuid)
    assert first.state is CollectionIdentityState.UNBOUND
    assert restarted.state is CollectionIdentityState.UNBOUND


def test_present_original_forces_a_copy_to_a_new_unbound_identity(
    tmp_path: Path,
) -> None:
    original_uuid = UUID("316e9f53-af6c-4ff4-9588-a421ec924ffe")
    copy_uuid = UUID("26bc2d22-cc1e-4a46-b88a-9cfb71d88060")
    generated = iter((original_uuid, copy_uuid))
    registry_path = tmp_path / "addon" / "collection-registry.json"
    service = CollectionIdentityService(
        registry_path,
        uuid_factory=lambda: next(generated),
    )
    original_locator = tmp_path / "Original" / "collection.anki2"
    original_locator.parent.mkdir()
    original_locator.touch()
    original_collection = FakeCollection()

    original = service.observe_open_collection(
        original_collection,
        original_locator,
    )
    service.bind_current(original.collection_uuid)

    copy_locator = tmp_path / "Copy" / "collection.anki2"
    copy_locator.parent.mkdir()
    copy_locator.touch()
    copied_collection = FakeCollection(config=original_collection.config.copy())
    copied = service.observe_open_collection(copied_collection, copy_locator)

    assert copied.collection_uuid == str(copy_uuid)
    assert copied.state is CollectionIdentityState.WRONG_COLLECTION
    assert copied_collection.config[COLLECTION_UUID_CONFIG_KEY] == str(copy_uuid)
    assert original_collection.config[COLLECTION_UUID_CONFIG_KEY] == str(original_uuid)


def test_absent_original_requires_an_explicit_copy_decision_defaulting_to_new(
    tmp_path: Path,
) -> None:
    original_uuid = UUID("7b90c76f-2a85-47e8-8c4b-15365e312831")
    service = CollectionIdentityService(
        tmp_path / "collection-registry.json",
        uuid_factory=lambda: original_uuid,
    )
    original_locator = tmp_path / "Original" / "collection.anki2"
    original_locator.parent.mkdir()
    original_locator.touch()
    original_collection = FakeCollection()
    original = service.observe_open_collection(original_collection, original_locator)
    service.bind_current(original.collection_uuid)
    original_locator.unlink()

    restored_locator = tmp_path / "Restored" / "collection.anki2"
    restored_locator.parent.mkdir()
    restored_locator.touch()
    restored_collection = FakeCollection(config=original_collection.config.copy())
    pending = service.observe_open_collection(restored_collection, restored_locator)

    assert pending.state is CollectionIdentityState.COPY_DECISION_REQUIRED
    assert pending.copy_decision_options == (
        CollectionCopyDecision.PREVIOUS_COLLECTION,
        CollectionCopyDecision.NEW_COPY,
    )
    assert pending.default_copy_decision is CollectionCopyDecision.NEW_COPY

    decided = service.decide_copy(
        restored_collection,
        restored_locator,
        original.collection_uuid,
        CollectionCopyDecision.PREVIOUS_COLLECTION,
    )

    assert decided.collection_uuid == original.collection_uuid
    assert decided.state is CollectionIdentityState.BOUND


def test_profile_rename_keeps_the_same_registered_instance(
    tmp_path: Path,
) -> None:
    collection_uuid = UUID("48514929-dc2b-4741-a0e4-cd0bc5cf8a71")
    service = CollectionIdentityService(
        tmp_path / "collection-registry.json",
        uuid_factory=lambda: collection_uuid,
    )
    original_locator = tmp_path / "Before Rename" / "collection.anki2"
    renamed_locator = tmp_path / "After Rename" / "collection.anki2"
    original_locator.parent.mkdir()
    original_locator.touch()
    collection = FakeCollection()
    original = service.observe_open_collection(collection, original_locator)
    service.bind_current(original.collection_uuid)
    original_locator.parent.rename(renamed_locator.parent)

    renamed = service.observe_open_collection(collection, renamed_locator)

    assert renamed.collection_uuid == str(collection_uuid)
    assert renamed.state is CollectionIdentityState.BOUND


def test_reused_registered_path_is_not_mistaken_for_the_original_instance(
    tmp_path: Path,
) -> None:
    collection_uuid = UUID("e0c8a39a-2d8f-44eb-a453-895876285017")
    service = CollectionIdentityService(
        tmp_path / "collection-registry.json",
        uuid_factory=lambda: collection_uuid,
    )
    locator = tmp_path / "Profile" / "collection.anki2"
    locator.parent.mkdir()
    locator.write_text("original", encoding="utf-8")
    original_collection = FakeCollection()
    original = service.observe_open_collection(original_collection, locator)
    service.bind_current(original.collection_uuid)
    locator.unlink()
    locator.write_text("different collection", encoding="utf-8")
    reused_path_collection = FakeCollection(config=original_collection.config.copy())

    observed = service.observe_open_collection(reused_path_collection, locator)

    assert observed.state is CollectionIdentityState.COPY_DECISION_REQUIRED
    assert observed.default_copy_decision is CollectionCopyDecision.NEW_COPY


def test_new_copy_decision_assigns_a_new_uuid_without_inheriting_binding(
    tmp_path: Path,
) -> None:
    original_uuid = UUID("9db1e2a8-b079-490d-9963-a150dc4558d3")
    copy_uuid = UUID("c53cc8c6-024e-43f9-9660-02ad5d07c75e")
    generated = iter((original_uuid, copy_uuid))
    service = CollectionIdentityService(
        tmp_path / "collection-registry.json",
        uuid_factory=lambda: next(generated),
    )
    original_locator = tmp_path / "Original" / "collection.anki2"
    original_locator.parent.mkdir()
    original_locator.touch()
    original_collection = FakeCollection()
    original = service.observe_open_collection(original_collection, original_locator)
    service.bind_current(original.collection_uuid)
    original_locator.unlink()

    copy_locator = tmp_path / "Copy" / "collection.anki2"
    copy_locator.parent.mkdir()
    copy_locator.touch()
    copied_collection = FakeCollection(config=original_collection.config.copy())
    service.observe_open_collection(copied_collection, copy_locator)

    decided = service.decide_copy(
        copied_collection,
        copy_locator,
        original.collection_uuid,
        CollectionCopyDecision.NEW_COPY,
    )

    assert decided.collection_uuid == str(copy_uuid)
    assert decided.state is CollectionIdentityState.WRONG_COLLECTION


def test_uuid_assignment_failure_leaves_the_collection_unbound(
    tmp_path: Path,
) -> None:
    collection = FakeCollection(fail_assignment=True)
    registry_path = tmp_path / "collection-registry.json"
    service = CollectionIdentityService(registry_path)

    observation = service.observe_open_collection(
        collection,
        tmp_path / "Profile" / "collection.anki2",
    )

    assert observation.state is CollectionIdentityState.ERROR
    assert observation.error_category == "collection_identity_persistence_failed"
    assert COLLECTION_UUID_CONFIG_KEY not in collection.config
    assert not registry_path.exists()


def test_registry_update_failure_never_partially_binds_an_assigned_uuid(
    tmp_path: Path,
) -> None:
    assigned_uuid = UUID("2e5060a1-a804-45dd-a1fb-83de4e42a5b9")
    registry_path = tmp_path / "collection-registry.json"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected registry replace failure")

    service = CollectionIdentityService(
        registry_path,
        uuid_factory=lambda: assigned_uuid,
        replace_file=fail_replace,
    )
    collection = FakeCollection()

    observation = service.observe_open_collection(
        collection,
        tmp_path / "Profile" / "collection.anki2",
    )

    assert observation.state is CollectionIdentityState.ERROR
    assert observation.collection_uuid == str(assigned_uuid)
    assert observation.error_category == "collection_identity_persistence_failed"
    assert collection.config[COLLECTION_UUID_CONFIG_KEY] == str(assigned_uuid)
    assert not registry_path.exists()


def test_copy_decision_registry_failure_preserves_the_existing_binding(
    tmp_path: Path,
) -> None:
    original_uuid = UUID("8af1ab9f-e33f-421e-b390-e5e2078230ed")
    fail_registry_update = False

    def replace_file(source: Path, target: Path) -> None:
        if fail_registry_update:
            raise OSError("injected copy-decision registry failure")
        source.replace(target)

    service = CollectionIdentityService(
        tmp_path / "collection-registry.json",
        uuid_factory=lambda: original_uuid,
        replace_file=replace_file,
    )
    original_locator = tmp_path / "Original" / "collection.anki2"
    original_locator.parent.mkdir()
    original_locator.touch()
    original_collection = FakeCollection()
    original = service.observe_open_collection(original_collection, original_locator)
    service.bind_current(original.collection_uuid)
    original_locator.unlink()

    restored_locator = tmp_path / "Restored" / "collection.anki2"
    restored_locator.parent.mkdir()
    restored_locator.touch()
    restored_collection = FakeCollection(config=original_collection.config.copy())
    service.observe_open_collection(restored_collection, restored_locator)
    fail_registry_update = True

    failed = service.decide_copy(
        restored_collection,
        restored_locator,
        original.collection_uuid,
        CollectionCopyDecision.PREVIOUS_COLLECTION,
    )

    assert failed.state is CollectionIdentityState.ERROR
    assert failed.error_category == "collection_identity_persistence_failed"
    persisted = CollectionIdentityService(
        tmp_path / "collection-registry.json"
    ).observe_open_collection(restored_collection, restored_locator)
    assert persisted.state is CollectionIdentityState.COPY_DECISION_REQUIRED

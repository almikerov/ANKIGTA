from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4


COLLECTION_UUID_CONFIG_KEY = "ankigta.collectionUuid"
REGISTRY_VERSION = 1


class CollectionConfiguration(Protocol):
    def get_config(self, key: str, default: object | None = None) -> object: ...

    def set_config(
        self,
        key: str,
        value: object,
        *,
        undoable: bool = False,
    ) -> object: ...


class CollectionIdentityState(StrEnum):
    UNBOUND = "unbound"
    BOUND = "bound"
    WRONG_COLLECTION = "wrong_collection"
    COPY_DECISION_REQUIRED = "copy_decision_required"
    ERROR = "identity_error"


@dataclass(frozen=True)
class AnkiCardIdentity:
    collection_uuid: str
    card_id: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "collection_uuid",
            str(UUID(self.collection_uuid)),
        )
        if self.card_id <= 0:
            raise ValueError("cardId must be positive")


class CollectionCopyDecision(StrEnum):
    PREVIOUS_COLLECTION = "previous_collection"
    NEW_COPY = "new_copy"


@dataclass(frozen=True)
class CollectionIdentityObservation:
    state: CollectionIdentityState
    collection_uuid: str | None
    error_category: str | None = None
    copy_decision_options: tuple[CollectionCopyDecision, ...] = ()
    default_copy_decision: CollectionCopyDecision | None = None


class CollectionIdentityService:
    def __init__(
        self,
        registry_path: Path,
        *,
        uuid_factory: Callable[[], UUID] = uuid4,
        replace_file: Callable[[Path, Path], None] = os.replace,
    ) -> None:
        self._registry_path = registry_path
        self._uuid_factory = uuid_factory
        self._replace_file = replace_file
        self._current: CollectionIdentityObservation | None = None

    def observe_open_collection(
        self,
        collection: CollectionConfiguration,
        locator: Path,
    ) -> CollectionIdentityObservation:
        try:
            return self._observe_open_collection(collection, locator)
        except Exception:
            try:
                collection_uuid = self._read_collection_uuid(collection)
            except Exception:
                collection_uuid = None
            return self._remember(
                CollectionIdentityObservation(
                    state=CollectionIdentityState.ERROR,
                    collection_uuid=collection_uuid,
                    error_category="collection_identity_persistence_failed",
                )
            )

    def _observe_open_collection(
        self,
        collection: CollectionConfiguration,
        locator: Path,
    ) -> CollectionIdentityObservation:
        collection_uuid = self._read_collection_uuid(collection)
        if collection_uuid is None:
            collection_uuid = self._assign_new_uuid(collection, set())
            if collection_uuid is None:
                return self._remember(
                    CollectionIdentityObservation(
                        state=CollectionIdentityState.ERROR,
                        collection_uuid=None,
                        error_category="collection_uuid_assignment_failed",
                    )
                )

        registry = self._load_registry()
        instances = registry["instances"]
        assert isinstance(instances, dict)
        normalized_locator = self._normalize_locator(locator)
        file_identity = self._file_identity(locator)
        registered = instances.get(collection_uuid)
        if registered is None:
            instances[collection_uuid] = {
                "locator": normalized_locator,
                "fileIdentity": file_identity,
            }
            self._save_registry(registry)
        elif self._registered_file_identity(registered) == file_identity:
            if self._registered_locator(registered) != normalized_locator:
                instances[collection_uuid] = {
                    "locator": normalized_locator,
                    "fileIdentity": file_identity,
                }
                self._save_registry(registry)
        else:
            registered_locator = self._registered_locator(registered)
            if self._registered_instance_is_present(registered):
                replacement_uuid = self._assign_new_uuid(
                    collection,
                    set(instances),
                )
                if replacement_uuid is None:
                    return self._remember(
                        CollectionIdentityObservation(
                            state=CollectionIdentityState.ERROR,
                            collection_uuid=None,
                            error_category="collection_uuid_assignment_failed",
                        )
                    )
                collection_uuid = replacement_uuid
                instances[collection_uuid] = {
                    "locator": normalized_locator,
                    "fileIdentity": file_identity,
                }
                self._save_registry(registry)
            else:
                return self._remember(
                    CollectionIdentityObservation(
                        state=CollectionIdentityState.COPY_DECISION_REQUIRED,
                        collection_uuid=collection_uuid,
                        copy_decision_options=(
                            CollectionCopyDecision.PREVIOUS_COLLECTION,
                            CollectionCopyDecision.NEW_COPY,
                        ),
                        default_copy_decision=CollectionCopyDecision.NEW_COPY,
                    )
                )

        bound_collection_uuid = registry["boundCollectionUuid"]
        state = self._binding_state(bound_collection_uuid, collection_uuid)
        return self._remember(
            CollectionIdentityObservation(
                state=state,
                collection_uuid=collection_uuid,
            )
        )

    def bind_current(
        self,
        expected_collection_uuid: str | None,
    ) -> CollectionIdentityObservation:
        current = self._current
        if (
            current is None
            or current.collection_uuid != expected_collection_uuid
            or current.state
            not in {
                CollectionIdentityState.UNBOUND,
                CollectionIdentityState.WRONG_COLLECTION,
                CollectionIdentityState.BOUND,
            }
        ):
            raise ValueError("current collection identity is not bindable")
        registry = self._load_registry()
        registry["boundCollectionUuid"] = current.collection_uuid
        self._save_registry(registry)
        self._current = CollectionIdentityObservation(
            state=CollectionIdentityState.BOUND,
            collection_uuid=current.collection_uuid,
        )
        return self._current

    def clear_current(self) -> None:
        self._current = None

    def decide_copy(
        self,
        collection: CollectionConfiguration,
        locator: Path,
        expected_collection_uuid: str | None,
        decision: CollectionCopyDecision,
    ) -> CollectionIdentityObservation:
        current = self._current
        if (
            current is None
            or current.state is not CollectionIdentityState.COPY_DECISION_REQUIRED
            or current.collection_uuid != expected_collection_uuid
        ):
            raise ValueError("current collection has no matching copy decision")

        try:
            registry = self._load_registry()
            instances = registry["instances"]
            assert isinstance(instances, dict)
            normalized_locator = self._normalize_locator(locator)
            if decision is CollectionCopyDecision.PREVIOUS_COLLECTION:
                assert current.collection_uuid is not None
                instances[current.collection_uuid] = {
                    "locator": normalized_locator,
                    "fileIdentity": self._file_identity(locator),
                }
                collection_uuid = current.collection_uuid
            else:
                replacement_uuid = self._assign_new_uuid(collection, set(instances))
                if replacement_uuid is None:
                    return self._remember(
                        CollectionIdentityObservation(
                            state=CollectionIdentityState.ERROR,
                            collection_uuid=None,
                            error_category="collection_uuid_assignment_failed",
                        )
                    )
                collection_uuid = replacement_uuid
                instances[collection_uuid] = {
                    "locator": normalized_locator,
                    "fileIdentity": self._file_identity(locator),
                }

            self._save_registry(registry)
            return self._remember(
                CollectionIdentityObservation(
                    state=self._binding_state(
                        registry["boundCollectionUuid"],
                        collection_uuid,
                    ),
                    collection_uuid=collection_uuid,
                )
            )
        except Exception:
            try:
                failed_uuid = self._read_collection_uuid(collection)
            except Exception:
                failed_uuid = current.collection_uuid
            return self._remember(
                CollectionIdentityObservation(
                    state=CollectionIdentityState.ERROR,
                    collection_uuid=failed_uuid,
                    error_category="collection_identity_persistence_failed",
                )
            )

    def _assign_new_uuid(
        self,
        collection: CollectionConfiguration,
        reserved: set[str],
    ) -> str | None:
        while True:
            collection_uuid = str(self._uuid_factory())
            if collection_uuid not in reserved:
                break
        collection.set_config(
            COLLECTION_UUID_CONFIG_KEY,
            collection_uuid,
            undoable=False,
        )
        if self._read_collection_uuid(collection) != collection_uuid:
            return None
        return collection_uuid

    def _read_collection_uuid(
        self,
        collection: CollectionConfiguration,
    ) -> str | None:
        value = collection.get_config(COLLECTION_UUID_CONFIG_KEY)
        if not isinstance(value, str):
            return None
        try:
            return str(UUID(value))
        except ValueError:
            return None

    def _load_registry(self) -> dict[str, object]:
        if not self._registry_path.exists():
            return {
                "version": REGISTRY_VERSION,
                "boundCollectionUuid": None,
                "instances": {},
            }
        loaded = json.loads(self._registry_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("collection identity registry must be an object")
        return loaded

    def _save_registry(self, registry: dict[str, object]) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._registry_path.parent,
                prefix=f".{self._registry_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(registry, temporary, ensure_ascii=False, sort_keys=True)
                temporary.flush()
                os.fsync(temporary.fileno())
            self._replace_file(temporary_path, self._registry_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _normalize_locator(locator: Path) -> str:
        return os.path.normcase(str(locator.resolve(strict=False)))

    @staticmethod
    def _registered_locator(registered: object) -> str | None:
        if not isinstance(registered, dict):
            return None
        locator = registered.get("locator")
        return locator if isinstance(locator, str) else None

    @staticmethod
    def _file_identity(locator: Path) -> dict[str, int]:
        stat = locator.stat()
        return {
            "device": stat.st_dev,
            "inode": stat.st_ino,
        }

    @staticmethod
    def _registered_file_identity(registered: object) -> dict[str, int] | None:
        if not isinstance(registered, dict):
            return None
        identity = registered.get("fileIdentity")
        if not isinstance(identity, dict):
            return None
        device = identity.get("device")
        inode = identity.get("inode")
        if not isinstance(device, int) or not isinstance(inode, int):
            return None
        return {"device": device, "inode": inode}

    @classmethod
    def _registered_instance_is_present(cls, registered: object) -> bool:
        locator = cls._registered_locator(registered)
        expected_identity = cls._registered_file_identity(registered)
        if locator is None or expected_identity is None:
            return False
        try:
            return cls._file_identity(Path(locator)) == expected_identity
        except OSError:
            return False

    @staticmethod
    def _binding_state(
        bound_collection_uuid: object,
        collection_uuid: str,
    ) -> CollectionIdentityState:
        if bound_collection_uuid == collection_uuid:
            return CollectionIdentityState.BOUND
        if bound_collection_uuid is not None:
            return CollectionIdentityState.WRONG_COLLECTION
        return CollectionIdentityState.UNBOUND

    def _remember(
        self,
        observation: CollectionIdentityObservation,
    ) -> CollectionIdentityObservation:
        self._current = observation
        return observation

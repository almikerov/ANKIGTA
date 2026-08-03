from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import AppConfig, ResourceConfig
from .debounce import DebounceManager
from .discovery import discover_resource_paths
from .http_client import HotReloadHTTPError, MTAHttpClient
from .path_rules import is_ignored, is_watched_path, relative_path
from .validation import validate_changed_files


def log(message: str, resource_name: str | None = None) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    resource = f" [{resource_name}]" if resource_name else ""
    print(f"[{timestamp}]{resource} {message}", flush=True)


class ReloadProcessor:
    def __init__(self, config: AppConfig, client: Any) -> None:
        self.config = config
        self.client = client
        self.resources = {item.name: item for item in config.watch.resources}
        self._lock = threading.RLock()

    def add_resource(self, resource: ResourceConfig) -> None:
        with self._lock:
            self.resources[resource.name] = resource

    def __call__(self, resource_name: str, changed_files: tuple[str, ...]) -> None:
        with self._lock:
            resource = self.resources.get(resource_name)
        if resource is None:
            log("Reload skipped because the local resource mapping disappeared", resource_name)
            return
        try:
            self.process(resource, changed_files)
        except Exception as exc:  # Keep all other resource watchers alive.
            log(f"Unexpected reload error: {exc}", resource_name)
            traceback.print_exc()

    def process(self, resource: ResourceConfig, changed_files: tuple[str, ...]) -> bool:
        log(f"Validating {len(changed_files)} changed file(s)...", resource.name)
        report = validate_changed_files(resource.path, changed_files, self.config.validation)
        if report.skipped_lua_files:
            log(
                f"Lua syntax validation skipped for {report.skipped_lua_files} file(s); no compiler is configured",
                resource.name,
            )
        if report.issues:
            for issue in report.issues:
                log(f"Validation error: {issue.display()}", resource.name)
            if self.config.validation.block_reload_on_error:
                log("Reload blocked because validation failed", resource.name)
                return False
            log("Validation failed, but configuration allows the reload", resource.name)
        else:
            checked_note = f" ({report.checked_files} syntax-checked)" if report.checked_files else ""
            log(f"Validation passed{checked_note}", resource.name)

        log("Sending reload request...", resource.name)
        try:
            result = self.client.reload(resource.name)
        except HotReloadHTTPError as exc:
            log(f"Reload request failed: {exc}", resource.name)
            return False

        action = str(result.payload.get("action", "reload")).capitalize()
        message = str(result.payload.get("message", "request accepted"))
        state = result.payload.get("stateBefore")
        state_note = f"; previous state: {state}" if state is not None else ""
        log(f"{action} accepted: {message}{state_note}", resource.name)
        return True


def collect_validation_candidates(resource: ResourceConfig) -> tuple[str, ...]:
    candidates: list[str] = []
    for path in resource.path.rglob("*"):
        if not path.is_file():
            continue
        relative_name = path.relative_to(resource.path).as_posix()
        if is_ignored(relative_name):
            continue
        if path.suffix.casefold() in {".lua", ".xml", ".map", ".edf"}:
            candidates.append(relative_name)
    return tuple(sorted(candidates, key=str.casefold))


def create_event_handler(resource: ResourceConfig, debouncer: DebounceManager, ignore_synthetic: bool) -> Any:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent

    class ResourceEventHandler(FileSystemEventHandler):
        def _record(self, candidate: str, *, is_directory: bool, event_type: str) -> None:
            if ignore_synthetic and getattr(self._current_event, "is_synthetic", False):
                return
            if is_directory and event_type not in {"created", "deleted", "moved"}:
                return
            relative_name = relative_path(resource.path, candidate)
            if relative_name is None or not is_watched_path(relative_name, is_directory=is_directory):
                return
            if debouncer.record(resource.name, relative_name):
                suffix = "/" if is_directory and not relative_name.endswith("/") else ""
                log(f"Changed: {relative_name}{suffix}", resource.name)

        def on_any_event(self, event: FileSystemEvent) -> None:
            self._current_event = event
            if event.event_type == "opened" or event.event_type == "closed" or event.event_type == "closed_no_write":
                return
            self._record(event.src_path, is_directory=event.is_directory, event_type=event.event_type)
            if isinstance(event, FileSystemMovedEvent):
                self._record(event.dest_path, is_directory=event.is_directory, event_type="moved")

    return ResourceEventHandler()


class WatcherApplication:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.client = MTAHttpClient(config.mta)
        self.processor = ReloadProcessor(config, self.client)
        self.debouncer = DebounceManager(config.watch.debounce_ms / 1000.0, self.processor)
        self._observer: Any = None
        self._stop_event = threading.Event()
        self._sync_thread: threading.Thread | None = None
        self._watch_lock = threading.RLock()
        self._watches: dict[str, tuple[Any, Path]] = {}
        self._dynamic_names: set[str] = set()
        self._last_allowed: frozenset[str] | None = None
        self._unresolved: set[str] = set()
        self._last_sync_error: str | None = None

    def _schedule_resource(self, resource: ResourceConfig) -> None:
        with self._watch_lock:
            current = self._watches.get(resource.name)
            if current and current[1] == resource.path:
                return
            if current:
                self._observer.unschedule(current[0])
            handler = create_event_handler(
                resource, self.debouncer, self.config.watch.ignore_initial_events
            )
            watch = self._observer.schedule(handler, str(resource.path), recursive=True)
            self._watches[resource.name] = (watch, resource.path)
            self.processor.add_resource(resource)
        log(f"Watching {resource.path}", resource.name)

    def _remove_dynamic_resource(self, resource_name: str) -> None:
        with self._watch_lock:
            current = self._watches.pop(resource_name, None)
            if current:
                self._observer.unschedule(current[0])
        if current:
            log("No longer watched (set to ignored in MTA)", resource_name)

    def _sync_from_mta(self) -> None:
        try:
            result = self.client.check()
            allowed_raw = result.payload.get("allowedResources", [])
            if not isinstance(allowed_raw, list):
                raise HotReloadHTTPError("INVALID_RESPONSE", "Endpoint returned an invalid allowedResources list")
            allowed = frozenset(str(name) for name in allowed_raw)
            explicit_names = {resource.name for resource in self.config.watch.resources}
            needs_discovery = allowed != self._last_allowed or bool(self._unresolved)
            if needs_discovery:
                root = self.config.watch.resources_root
                if root is None:
                    return
                found, problems = discover_resource_paths(root, allowed - explicit_names)
                desired_dynamic = set(found)
                for resource_name in self._dynamic_names - desired_dynamic:
                    self._remove_dynamic_resource(resource_name)
                for resource in found.values():
                    self._schedule_resource(resource)
                self._dynamic_names = desired_dynamic
                self._unresolved = set(allowed - explicit_names - desired_dynamic)
                for problem in problems:
                    log(f"Auto-sync warning: {problem}")
                if allowed != self._last_allowed:
                    log(
                        f"MTA selection synchronized: {len(allowed)} allowed resource(s), "
                        f"{len(desired_dynamic) + len(explicit_names & allowed)} watched"
                    )
                self._last_allowed = allowed
            if self._last_sync_error is not None:
                log("Connection to the MTA resource manager restored")
            self._last_sync_error = None
        except HotReloadHTTPError as exc:
            message = str(exc)
            if message != self._last_sync_error:
                log(f"MTA selection sync unavailable: {message}; watching will continue")
                self._last_sync_error = message

    def _sync_loop(self) -> None:
        while not self._stop_event.is_set():
            self._sync_from_mta()
            self._stop_event.wait(self.config.watch.sync_interval_seconds)

    def run(self) -> int:
        try:
            from watchdog.observers import Observer
        except ImportError:
            print(
                "ERROR: watchdog is not installed. Run: python -m pip install -r requirements.txt",
                file=sys.stderr,
            )
            return 3

        self._observer = Observer()
        for resource in self.config.watch.resources:
            self._schedule_resource(resource)

        self._observer.start()
        if self.config.watch.auto_sync_from_mta:
            log(
                f"Automatic MTA selection sync enabled ({self.config.watch.sync_interval_seconds:g}s)"
            )
            self._sync_thread = threading.Thread(
                target=self._sync_loop, name="mta-hotreload-sync", daemon=True
            )
            self._sync_thread.start()
        log("Hot Reload watcher is running. Press Ctrl+C to stop.")
        try:
            while not self._stop_event.wait(0.5):
                if not self._observer.is_alive():
                    log("Filesystem observer stopped unexpectedly")
                    return 4
        except KeyboardInterrupt:
            log("Stopping Hot Reload watcher...")
        finally:
            self.stop()
        return 0

    def stop(self) -> None:
        self._stop_event.set()
        if self._sync_thread is not None:
            self._sync_thread.join(timeout=1)
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
        self.debouncer.shutdown(wait=True)
        log("Hot Reload watcher stopped")

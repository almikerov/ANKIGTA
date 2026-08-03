from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass
class _ResourceState:
    pending: set[str] = field(default_factory=set)
    timer: threading.Timer | None = None
    running: bool = False
    last_event_at: float = 0.0


class DebounceManager:
    """Combine changes per resource and serialize callbacks for each resource."""

    def __init__(
        self,
        quiet_seconds: float,
        callback: Callable[[str, tuple[str, ...]], None],
    ) -> None:
        self.quiet_seconds = quiet_seconds
        self.callback = callback
        self._states: dict[str, _ResourceState] = {}
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._closed = False

    def record(self, resource_name: str, relative_path: str) -> bool:
        with self._lock:
            if self._closed:
                return False
            state = self._states.setdefault(resource_name, _ResourceState())
            state.pending.add(relative_path)
            state.last_event_at = time.monotonic()
            if not state.running:
                self._replace_timer(resource_name, state, self.quiet_seconds)
            return True

    def _replace_timer(
        self, resource_name: str, state: _ResourceState, delay: float
    ) -> None:
        if state.timer is not None:
            state.timer.cancel()
        timer = threading.Timer(delay, self._run_batch, args=(resource_name,))
        timer.daemon = True
        state.timer = timer
        timer.start()

    def _run_batch(self, resource_name: str) -> None:
        with self._lock:
            if self._closed:
                return
            state = self._states[resource_name]
            elapsed = time.monotonic() - state.last_event_at
            if elapsed < self.quiet_seconds:
                self._replace_timer(resource_name, state, self.quiet_seconds - elapsed)
                return
            if state.running or not state.pending:
                return
            changed = tuple(sorted(state.pending, key=str.casefold))
            state.pending.clear()
            state.timer = None
            state.running = True

        try:
            self.callback(resource_name, changed)
        finally:
            with self._lock:
                state = self._states[resource_name]
                state.running = False
                if state.pending and not self._closed:
                    elapsed = time.monotonic() - state.last_event_at
                    self._replace_timer(
                        resource_name, state, max(0.0, self.quiet_seconds - elapsed)
                    )
                self._condition.notify_all()

    def pending_for(self, resource_name: str) -> tuple[str, ...]:
        with self._lock:
            state = self._states.get(resource_name)
            return tuple(sorted(state.pending, key=str.casefold)) if state else ()

    def shutdown(self, *, wait: bool = True, timeout: float = 5.0) -> None:
        with self._lock:
            self._closed = True
            for state in self._states.values():
                if state.timer is not None:
                    state.timer.cancel()
            if wait:
                deadline = time.monotonic() + timeout
                while any(state.running for state in self._states.values()):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._condition.wait(remaining)

    def resources(self) -> Iterable[str]:
        with self._lock:
            return tuple(self._states)

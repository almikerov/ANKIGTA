"""Talk to dev_hotreload through its command file.

This replaces an HTTP client that authenticated with an MTA account. The
account needed a password, and that password sat in ``config.json`` in plain
text; a ``.gitignore`` keeps a secret out of a publication, not off a disk.
Here there is no secret to keep and no socket to reach: writing into the
resource's own folder is already something this process can do, because
watching that folder is its whole job.

The protocol is one request line in ``command.txt`` and one JSON object per
answer appended to ``result.txt``. Requests carry a ``requestId`` so an answer
is matched to the request that earned it rather than to whatever arrived next.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import MTAConfig


class HotReloadChannelError(RuntimeError):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class EndpointRejected(HotReloadChannelError):
    """The resource answered, and the answer was no."""

    def __init__(self, payload: dict[str, Any]):
        code = str(payload.get("error", "ENDPOINT_REJECTED"))
        message = str(payload.get("message", "Endpoint returned false"))
        super().__init__(code, f"{code}: {message}")
        self.payload = payload


@dataclass(frozen=True)
class EndpointResult:
    accepted: bool
    payload: dict[str, Any]
    raw: list[Any]


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def encode_request(command: str, payload: dict[str, Any] | None = None) -> str:
    if not payload:
        return command
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"{command} {body}"


class FileChannel:
    """A request/answer pair of files inside the dev_hotreload resource."""

    def __init__(self, resource_dir: Path, timeout_seconds: float):
        self.resource_dir = Path(resource_dir)
        self.timeout_seconds = float(timeout_seconds)
        self.command_path = self.resource_dir / "command.txt"
        self.result_path = self.resource_dir / "result.txt"

    def _result_size(self) -> int:
        try:
            return self.result_path.stat().st_size
        except OSError:
            return 0

    def _write_command(self, line: str) -> None:
        # Written to a neighbouring file and moved into place, so the resource
        # cannot read a request that is still half-written. `os.replace` is
        # atomic where it matters, and on Windows it can still lose a race with
        # the reader having the file open, which is what the retry is for.
        temporary = self.command_path.with_suffix(".txt.part")
        last_error: OSError | None = None
        for _ in range(20):
            try:
                temporary.write_text(line + "\n", encoding="utf-8")
                os.replace(temporary, self.command_path)
                return
            except OSError as error:
                last_error = error
                time.sleep(0.05)
        raise HotReloadChannelError(
            "COMMAND_WRITE_FAILED",
            f"Could not write {self.command_path}: {last_error}",
        )

    def _read_answers_from(self, offset: int) -> list[dict[str, Any]]:
        try:
            with self.result_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                text = handle.read()
        except OSError:
            return []
        answers: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                answers.append(parsed)
        return answers

    def request(self, command: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.resource_dir.is_dir():
            raise HotReloadChannelError(
                "RESOURCE_MISSING",
                f"dev_hotreload is not installed at {self.resource_dir}",
            )
        body = dict(payload or {})
        request_id = new_request_id()
        body["requestId"] = request_id

        # Where the answer file ends now, so only what arrives after this
        # request is considered. Answers to earlier requests are still in the
        # file and would otherwise match by luck.
        offset = self._result_size()
        self._write_command(encode_request(command, body))

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            for answer in self._read_answers_from(offset):
                if answer.get("requestId") == request_id:
                    return answer
            time.sleep(0.05)

        raise HotReloadChannelError(
            "CHANNEL_TIMEOUT",
            f"No answer to '{command}' within {self.timeout_seconds:g}s. "
            "Is dev_hotreload running?",
        )


def _to_result(answer: dict[str, Any]) -> EndpointResult:
    detail = answer.get("result")
    payload = detail if isinstance(detail, dict) else {}
    if answer.get("ok") is not True:
        rejection = dict(payload)
        for key in ("error", "message"):
            if key in answer:
                rejection.setdefault(key, answer[key])
        raise EndpointRejected(rejection)
    return EndpointResult(accepted=True, payload=payload, raw=[answer])


class HotReloadClient:
    """The same two calls the HTTP client offered, over the file channel."""

    def __init__(
        self,
        config: MTAConfig,
        *,
        attempts: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.attempts = max(1, attempts)
        self._sleeper = sleeper
        self._channel = FileChannel(config.resource_dir, config.timeout_seconds)

    def reload(self, resource_name: str) -> EndpointResult:
        return self._call("reload", {"resource": resource_name})

    def check(self) -> EndpointResult:
        return self._call("status", None)

    def _call(self, command: str, payload: dict[str, Any] | None) -> EndpointResult:
        for attempt in range(1, self.attempts + 1):
            try:
                return _to_result(self._channel.request(command, payload))
            except EndpointRejected:
                # The resource answered and said no. Asking again would get the
                # same no; only the reasons below are worth a second try.
                raise
            except HotReloadChannelError:
                if attempt < self.attempts:
                    self._sleeper(min(0.5 * (2 ** (attempt - 1)), 4.0))
                    continue
                raise
        raise HotReloadChannelError("UNKNOWN_CHANNEL_ERROR", "Channel request failed")

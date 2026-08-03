from __future__ import annotations

import base64
import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

from .config import MTAConfig


class HotReloadHTTPError(RuntimeError):
    def __init__(self, kind: str, message: str, *, status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


class EndpointRejected(HotReloadHTTPError):
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


def build_call_url(base_url: str, resource: str, function_name: str) -> str:
    return f"{base_url.rstrip('/')}/{quote(resource, safe='')}/call/{quote(function_name, safe='')}"


def build_basic_auth_header(username: str, password: str) -> str:
    encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def build_request(
    mta: MTAConfig, function_name: str, arguments: list[Any]
) -> urllib.request.Request:
    body = json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        build_call_url(mta.base_url, mta.hotreload_resource, function_name),
        data=body,
        method="POST",
    )
    request.add_header("Content-Type", "application/json; charset=utf-8")
    request.add_header("Accept", "application/json")
    request.add_header("Authorization", build_basic_auth_header(mta.username, mta.password))
    return request


def parse_response(data: bytes) -> EndpointResult:
    try:
        decoded = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HotReloadHTTPError("INVALID_JSON", f"MTA returned invalid JSON: {exc}") from exc
    if not isinstance(decoded, list) or not decoded or not isinstance(decoded[0], bool):
        raise HotReloadHTTPError("INVALID_RESPONSE", "MTA response must be a JSON array beginning with true or false")
    payload = decoded[1] if len(decoded) > 1 and isinstance(decoded[1], dict) else {}
    if decoded[0] is False:
        raise EndpointRejected(payload)
    return EndpointResult(True, payload, decoded)


class MTAHttpClient:
    def __init__(
        self,
        config: MTAConfig,
        *,
        attempts: int = 3,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.attempts = max(1, attempts)
        self._opener = opener
        self._sleeper = sleeper

    def reload(self, resource_name: str) -> EndpointResult:
        return self._call("reloadResourceByName", [resource_name])

    def check(self) -> EndpointResult:
        return self._call("getHotReloadStatus", [])

    def _call(self, function_name: str, arguments: list[Any]) -> EndpointResult:
        request = build_request(self.config, function_name, arguments)
        for attempt in range(1, self.attempts + 1):
            try:
                with self._opener(request, timeout=self.config.timeout_seconds) as response:
                    return parse_response(response.read())
            except urllib.error.HTTPError as exc:
                status = exc.code
                labels = {
                    401: "HTTP 401: authentication failed; check the dedicated account credentials",
                    403: (
                        "HTTP 403: account lacks "
                        f"resource.{self.config.hotreload_resource}.http access"
                    ),
                    404: "HTTP 404: endpoint not found; check the HTTP port, resource name, and exports",
                    500: "HTTP 500: MTA endpoint failed while processing the request",
                }
                message = labels.get(status, f"HTTP {status}: MTA rejected the request")
                if status in {500, 502, 503, 504} and attempt < self.attempts:
                    self._sleeper(min(0.5 * (2 ** (attempt - 1)), 4.0))
                    continue
                raise HotReloadHTTPError(f"HTTP_{status}", message, status=status) from exc
            except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as exc:
                reason = getattr(exc, "reason", exc)
                is_timeout = isinstance(reason, (socket.timeout, TimeoutError))
                is_refused = isinstance(reason, ConnectionRefusedError)
                if is_timeout:
                    kind = "TIMEOUT"
                    message = "MTA HTTP request timed out"
                elif is_refused:
                    kind = "CONNECTION_REFUSED"
                    message = "Connection refused by the MTA HTTP interface"
                else:
                    kind = "CONNECTION_ERROR"
                    message = f"Cannot connect to the MTA HTTP interface: {reason}"
                if attempt < self.attempts:
                    self._sleeper(min(0.5 * (2 ** (attempt - 1)), 4.0))
                    continue
                raise HotReloadHTTPError(kind, message) from exc

        raise HotReloadHTTPError("UNKNOWN_HTTP_ERROR", "HTTP request failed")

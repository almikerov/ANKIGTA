from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from ankigta_companion.http_server import HealthServer


REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_RESOURCE = REPO_ROOT / "mta" / "ankigta"
DRIVER_RESOURCE = Path(__file__).resolve().parent / "driver"
EXPECTED_MTA_BUILD = 24124


@dataclass(frozen=True)
class HealthCase:
    anki_version: str
    collection_state: CollectionState
    profile_name: str | None


HEALTH_CASES = {
    "success": HealthCase("26.05", CollectionState.OPEN, "Ticket 02"),
    "collection_unavailable": HealthCase(
        "26.05",
        CollectionState.ABSENT,
        None,
    ),
    "compatibility_failure": HealthCase(
        "25.07.3",
        CollectionState.OPEN,
        "Ticket 02",
    ),
}

ADVERSE_CASES: dict[str, dict[str, object]] = {
    "wrong_content_type": {"content_type": "text/plain"},
    "json_prefix_content_type": {"content_type": "application/jsonp"},
    "malformed_json": {"malformed_json": True},
    "missing_health_fields": {"missing_health_fields": True},
    "success_with_error": {"success_with_error": True},
    "error_missing_message": {"error_missing_message": True},
    "compatibility_contradiction": {"compatibility_contradiction": True},
    "late_callback": {"delay_seconds": 5.3, "wait_after_ms": 800},
    "protocol_version_string": {"protocol_version": "1"},
    "wrong_protocol_version": {"protocol_version": 2},
    "wrong_request_id": {"request_id": "some-other-request"},
}


def _set_required_text(root: ET.Element[str], tag: str, value: str) -> None:
    element = root.find(tag)
    if element is None:
        raise AssertionError(f"MTA server configuration is missing <{tag}>")
    element.text = value


class AdverseHealthServer:
    host = "127.0.0.1"

    def __init__(self, case_name: str) -> None:
        try:
            self._case = ADVERSE_CASES[case_name]
        except KeyError as error:
            raise ValueError(f"unknown ticket 02 case: {case_name}") from error
        self._server = HTTPServer((self.host, 0), self._handler_type())
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        case = self._case

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                content_length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(content_length))
                delay_seconds = case.get("delay_seconds")
                if isinstance(delay_seconds, float):
                    time.sleep(delay_seconds)
                response: dict[str, object] = {
                    "protocol": "ankigta-control",
                    "protocolVersion": 1,
                    "requestId": request["requestId"],
                    "ok": True,
                    "error": None,
                    "payload": {
                        "anki": {
                            "version": "26.05",
                            "v3Scheduler": True,
                            "fsrsEnabled": True,
                        },
                        "collection": {
                            "state": "open",
                            "profileName": "Ticket 02 adverse",
                        },
                        "compatibility": {
                            "status": "supported",
                            "previewReadOnlyCompatible": True,
                            "sessionCompatible": True,
                            "ratingCompatible": True,
                        },
                        "study": {
                            "sessionActive": False,
                            "ratingEnabled": False,
                        }
                    },
                }
                if case.get("missing_health_fields") is True:
                    response["payload"] = {
                        "study": {
                            "sessionActive": False,
                            "ratingEnabled": False,
                        }
                    }
                if case.get("success_with_error") is True:
                    response["error"] = {
                        "category": "unexpected_error",
                        "message": "must conflict with ok=true",
                    }
                if case.get("error_missing_message") is True:
                    response["ok"] = False
                    response["error"] = {
                        "category": "collection_unavailable",
                    }
                    payload = response["payload"]
                    assert isinstance(payload, dict)
                    collection = payload["collection"]
                    assert isinstance(collection, dict)
                    collection["state"] = "absent"
                if case.get("compatibility_contradiction") is True:
                    payload = response["payload"]
                    assert isinstance(payload, dict)
                    compatibility = payload["compatibility"]
                    assert isinstance(compatibility, dict)
                    compatibility["ratingCompatible"] = False
                content_type = str(case.get("content_type", "application/json"))
                if case.get("malformed_json") is True:
                    encoded = b'{"protocol":'
                else:
                    if "protocol_version" in case:
                        response["protocolVersion"] = case["protocol_version"]
                    if "request_id" in case:
                        response["requestId"] = case["request_id"]
                    encoded = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler

    def __enter__(self) -> AdverseHealthServer:
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def _configure_server(server_root: Path) -> None:
    deathmatch = server_root / "mods" / "deathmatch"
    config_path = deathmatch / "mtaserver.conf"
    config = ET.parse(config_path)
    root = config.getroot()
    for resource in list(root.findall("resource")):
        root.remove(resource)
    ET.SubElement(
        root,
        "resource",
        {"src": "ankigta", "startup": "1", "protected": "0"},
    )
    ET.SubElement(
        root,
        "resource",
        {"src": "ankigta_ticket02_tests", "startup": "1", "protected": "0"},
    )
    _set_required_text(
        root,
        "servername",
        "ANKIGTA TICKET 02 DISPOSABLE ACCEPTANCE",
    )
    _set_required_text(root, "serverip", "127.0.0.1")
    _set_required_text(root, "serverport", "22232")
    _set_required_text(root, "httpserver", "0")
    _set_required_text(root, "ase", "0")
    _set_required_text(root, "donotbroadcastlan", "1")
    _set_required_text(root, "maxplayers", "1")
    config.write(config_path, encoding="utf-8", xml_declaration=False)

    acl_path = deathmatch / "acl.xml"
    acl_tree = ET.parse(acl_path)
    admin_group = next(
        group
        for group in acl_tree.getroot().findall("group")
        if group.get("name") == "Admin"
    )
    existing = {item.get("name") for item in admin_group.findall("object")}
    for resource_name in ("resource.ankigta", "resource.ankigta_ticket02_tests"):
        if resource_name not in existing:
            ET.SubElement(admin_group, "object", {"name": resource_name})
    acl_tree.write(acl_path, encoding="utf-8", xml_declaration=False)


def _server_executable(server_root: Path) -> Path:
    for name in ("MTA Server64.exe", "MTA Server.exe"):
        candidate = server_root / name
        if candidate.exists():
            return candidate
    raise RuntimeError(f"MTA Server executable is missing under {server_root}")


def _install_late_callback_probe(target_resource: Path) -> None:
    probe_source = DRIVER_RESOURCE / "late_callback_probe.lua"
    probe_relative_path = "tests/late_callback_probe.lua"
    probe_target = target_resource / probe_relative_path
    probe_target.parent.mkdir(parents=True)
    shutil.copy2(probe_source, probe_target)

    manifest_path = target_resource / "meta.xml"
    manifest = ET.parse(manifest_path)
    root = manifest.getroot()
    scripts = list(root.findall("script"))
    companion_script = next(
        script
        for script in scripts
        if script.get("src") == "server/companion.lua"
    )
    companion_index = list(root).index(companion_script)
    root.insert(
        companion_index,
        ET.Element(
            "script",
            {"src": probe_relative_path, "type": "server"},
        ),
    )
    manifest.write(manifest_path, encoding="utf-8", xml_declaration=False)


def _prepare_runtime(mta_server_root: Path, case: dict[str, object]) -> tuple[Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="ankigta-ticket02-"))
    server_root = temp_root / "server"
    shutil.copytree(mta_server_root, server_root)
    resources = server_root / "mods" / "deathmatch" / "resources"
    target_resource = resources / "ankigta"
    driver_resource = resources / "ankigta_ticket02_tests"
    shutil.copytree(PRODUCTION_RESOURCE, target_resource)
    shutil.copytree(DRIVER_RESOURCE, driver_resource)
    if case["name"] == "late_callback":
        _install_late_callback_probe(target_resource)
    (driver_resource / "case.json").write_text(
        json.dumps(case, ensure_ascii=False),
        encoding="utf-8",
    )
    _configure_server(server_root)
    return temp_root, driver_resource


def _run_mta(
    mta_server_root: Path,
    case: dict[str, object],
) -> dict[str, Any]:
    temp_root, driver_resource = _prepare_runtime(mta_server_root, case)
    server_root = temp_root / "server"
    result_path = driver_resource / "result.json"
    executable = _server_executable(server_root)
    process = subprocess.Popen(
        [str(executable), "-s", "-D", str(server_root)],
        cwd=server_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    deadline = time.monotonic() + 15
    result: dict[str, Any] | None = None
    try:
        while time.monotonic() < deadline:
            if result_path.exists():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        if process.poll() is None:
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=5)

    if result is None:
        stdout, stderr = process.communicate()
        server_log = (
            server_root / "mods" / "deathmatch" / "logs" / "server.log"
        )
        log_text = (
            server_log.read_text(encoding="utf-8", errors="replace")
            if server_log.exists()
            else ""
        )
        raise AssertionError(
            "MTA Server did not produce ticket 02 evidence\n"
            + stdout.decode(errors="replace")
            + stderr.decode(errors="replace")
            + "\nSERVER LOG\n"
            + log_text
        )
    shutil.rmtree(temp_root, ignore_errors=True)
    version = result.get("mtaVersion")
    sortable = version.get("sortable", "") if isinstance(version, dict) else ""
    if str(EXPECTED_MTA_BUILD) not in sortable:
        raise AssertionError(f"unexpected MTA build evidence: {result}")
    return result


def run_health_case(mta_server_root: Path, case_name: str) -> dict[str, Any]:
    health_case = HEALTH_CASES.get(case_name)
    if health_case is not None:
        observation = RuntimeObservation(
            anki_version=health_case.anki_version,
            v3_scheduler=True,
            fsrs_enabled=True,
            collection=CollectionObservation(
                state=health_case.collection_state,
                profile_name=health_case.profile_name,
            ),
        )
        server_context: HealthServer | AdverseHealthServer = HealthServer(
            lambda: observation
        )
    elif case_name in ADVERSE_CASES:
        server_context = AdverseHealthServer(case_name)
    else:
        raise ValueError(f"unknown ticket 02 case: {case_name}")

    with server_context as server:
        case: dict[str, object] = {
            "name": case_name,
            "port": server.port,
            "requestId": f"ticket02-{case_name}",
        }
        wait_after_ms = ADVERSE_CASES.get(case_name, {}).get("wait_after_ms")
        if isinstance(wait_after_ms, int):
            case["waitAfterMs"] = wait_after_ms
        return _run_mta(
            mta_server_root,
            case,
        )


def configured_mta_server_root() -> Path:
    configured = os.environ.get("ANKIGTA_MTA_SERVER_ROOT")
    candidates = [
        Path(configured) if configured else None,
        REPO_ROOT
        / ".scratch"
        / "0004-mta-loopback-transport-prototype"
        / "runtime"
        / "mta-package"
        / "server",
        Path(r"C:\Games\MTA San Andreas 1.6\server"),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        resolved = candidate.resolve()
        if any((resolved / name).exists() for name in ("MTA Server64.exe", "MTA Server.exe")):
            return resolved
    raise RuntimeError("a tested MTA Server 1.6 build 24124 is not available")

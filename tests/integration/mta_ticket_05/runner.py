from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_RESOURCE = REPO_ROOT / "mta" / "ankigta"
DRIVER_RESOURCE = Path(__file__).resolve().parent / "driver"
EXPECTED_MTA_BUILD = 24124


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


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
        {"src": "ankigta_ticket05_tests", "startup": "1", "protected": "0"},
    )
    root.find("servername").text = "ANKIGTA TICKET 05 DISPOSABLE ACCEPTANCE"
    root.find("serverip").text = "127.0.0.1"
    root.find("serverport").text = "22235"
    root.find("httpserver").text = "0"
    root.find("ase").text = "0"
    root.find("donotbroadcastlan").text = "1"
    root.find("maxplayers").text = "2"
    config.write(config_path, encoding="utf-8", xml_declaration=False)

    acl_path = deathmatch / "acl.xml"
    acl_tree = ET.parse(acl_path)
    admin_group = next(
        group
        for group in acl_tree.getroot().findall("group")
        if group.get("name") == "Admin"
    )
    existing = {item.get("name") for item in admin_group.findall("object")}
    for resource_name in ("resource.ankigta", "resource.ankigta_ticket05_tests"):
        if resource_name not in existing:
            ET.SubElement(admin_group, "object", {"name": resource_name})

    admin_acl = next(
        acl
        for acl in acl_tree.getroot().findall("acl")
        if acl.get("name") == "Admin"
    )
    loadstring_right = next(
        (
            right
            for right in admin_acl.findall("right")
            if right.get("name") == "function.loadstring"
        ),
        None,
    )
    if loadstring_right is None:
        loadstring_right = ET.SubElement(
            admin_acl,
            "right",
            {"name": "function.loadstring"},
        )
    loadstring_right.set("access", "true")
    acl_tree.write(acl_path, encoding="utf-8", xml_declaration=False)


def _prepare_runtime(mta_server_root: Path) -> tuple[Path, Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="ankigta-ticket05-"))
    server_root = temp_root / "server"
    shutil.copytree(mta_server_root, server_root)

    resources = server_root / "mods" / "deathmatch" / "resources"
    target_resource = resources / "ankigta"
    driver_resource = resources / "ankigta_ticket05_tests"
    shutil.copytree(PRODUCTION_RESOURCE, target_resource)
    shutil.copytree(DRIVER_RESOURCE, driver_resource)
    _configure_server(server_root)
    return temp_root, target_resource, driver_resource


def _create_legacy_database(path: Path, *, inconsistent: bool = False) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE schema_meta (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                version INTEGER NOT NULL
            );
            INSERT INTO schema_meta (singleton, version) VALUES (1, 1);
            CREATE TABLE maps (
                map_id TEXT PRIMARY KEY,
                resource_name TEXT NOT NULL,
                map_name TEXT NOT NULL
            );
            CREATE TABLE map_entities (
                map_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                entity_type TEXT NOT NULL CHECK (entity_type = 'object'),
                model INTEGER NOT NULL,
                authored_x REAL NOT NULL,
                authored_y REAL NOT NULL,
                authored_z REAL NOT NULL,
                authored_heading REAL NOT NULL,
                interior INTEGER NOT NULL,
                dimension INTEGER NOT NULL,
                PRIMARY KEY (map_id, entity_id),
                FOREIGN KEY (map_id) REFERENCES maps(map_id) ON DELETE CASCADE
            );
            INSERT INTO maps (map_id, resource_name, map_name)
            VALUES ('ticket05-map', 'ankigta', 'Ticket 05 tracer map');
            INSERT INTO map_entities (
                map_id, entity_id, entity_type, model,
                authored_x, authored_y, authored_z, authored_heading,
                interior, dimension
            ) VALUES (
                'ticket05-map', 'ticket05-entity', 'object', 1337,
                10.5, -20.25, 4.75, 135.0,
                3, 17
            );
            """
        )
        if inconsistent:
            connection.execute(
                "ALTER TABLE map_entities ADD COLUMN rotation_x REAL NOT NULL DEFAULT 0"
            )
        connection.commit()
    finally:
        connection.close()


def _read_database(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        version = connection.execute(
            "SELECT version FROM schema_meta WHERE singleton = 1"
        ).fetchone()
        columns = [
            row["name"]
            for row in connection.execute("PRAGMA table_info(map_entities)").fetchall()
        ]
        heading_expression = (
            "authored_heading"
            if "authored_heading" in columns
            else "rotation_z AS authored_heading"
        )
        entity = connection.execute(
            f"""
            SELECT map_id, entity_id, entity_type, model,
                   authored_x, authored_y, authored_z,
                   {heading_expression}, interior, dimension
            FROM map_entities
            WHERE map_id = 'ticket05-map' AND entity_id = 'ticket05-entity'
            """
        ).fetchone()
        return {
            "version": version["version"],
            "columns": columns,
            "entity": dict(entity) if entity else None,
        }
    finally:
        connection.close()


def _run_server_case(
    server_root: Path,
    target_resource: Path,
    driver_resource: Path,
    case_name: str,
) -> dict[str, Any]:
    result_path = driver_resource / "result.json"
    case_path = driver_resource / "case.json"
    database_path = target_resource / "ankigta.sqlite"
    if result_path.exists():
        result_path.unlink()
    if database_path.exists():
        database_path.unlink()
    _write_json(case_path, {"name": case_name})

    if case_name == "migration":
        _create_legacy_database(database_path)
    elif case_name == "migration_failure":
        _create_legacy_database(database_path, inconsistent=True)

    executable = server_root / "MTA Server64.exe"
    process = subprocess.Popen(
        [str(executable), "-s", "-D", str(server_root)],
        cwd=server_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    deadline = time.monotonic() + 30
    result: dict[str, Any] | None = None
    try:
        while time.monotonic() < deadline:
            if result_path.exists():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                break
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(
                    "MTA Server exited before producing ticket 05 evidence\n"
                    + stdout.decode(errors="replace")
                    + stderr.decode(errors="replace")
                )
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
            server_root
            / "mods"
            / "deathmatch"
            / "logs"
            / "server.log"
        )
        log_text = (
            server_log.read_text(encoding="utf-8", errors="replace")
            if server_log.exists()
            else ""
        )
        raise AssertionError(
            "MTA Server timed out before producing ticket 05 evidence\n"
            + stdout.decode(errors="replace")
            + stderr.decode(errors="replace")
            + "\nSERVER LOG\n"
            + log_text
        )

    database = _read_database(database_path)
    backup_path = target_resource / "backups" / "pre-migration-v1-to-v2.sqlite"
    backup = _read_database(backup_path) if backup_path.exists() else None
    return {
        "mta": result,
        "database": database,
        "backup": backup,
    }


def run_acceptance_suite(mta_server_root: Path) -> dict[str, Any]:
    if not PRODUCTION_RESOURCE.exists():
        raise AssertionError(f"production MTA resource is missing: {PRODUCTION_RESOURCE}")
    executable = mta_server_root / "MTA Server64.exe"
    if not executable.exists():
        raise AssertionError(f"MTA Server64.exe is missing: {executable}")

    temp_root, target_resource, driver_resource = _prepare_runtime(mta_server_root)
    server_root = temp_root / "server"
    try:
        cases = {
            name: _run_server_case(
                server_root,
                target_resource,
                driver_resource,
                name,
            )
            for name in ("fresh", "migration", "migration_failure")
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    builds = {
        case["mta"]["mtaVersion"]["sortable"]
        for case in cases.values()
        if isinstance(case["mta"].get("mtaVersion"), dict)
    }
    if not any(str(EXPECTED_MTA_BUILD) in build for build in builds):
        raise AssertionError(f"unexpected MTA build evidence: {sorted(builds)}")
    return cases


def configured_mta_server_root() -> Path:
    configured = os.environ.get("ANKIGTA_MTA_SERVER_ROOT")
    if not configured:
        raise RuntimeError("ANKIGTA_MTA_SERVER_ROOT is not configured")
    return Path(configured).resolve()

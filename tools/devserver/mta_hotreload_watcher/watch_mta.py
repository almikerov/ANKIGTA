from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hotreload.config import AppConfig, ConfigError, ResourceConfig, load_config
from hotreload.discovery import discover_resource_paths
from hotreload.file_client import HotReloadChannelError, HotReloadClient
from hotreload.runtime import (
    ReloadProcessor,
    WatcherApplication,
    collect_validation_candidates,
    log,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch MTA resources and hot reload changed targets")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config.json",
        help="configuration file (default: config.json beside this script)",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true", help="check folders, authentication, and endpoint")
    actions.add_argument("--reload", metavar="NAME", help="validate and reload one configured resource")
    actions.add_argument("--list", action="store_true", help="list configured resource mappings")
    return parser


def resolve_resources_from_mta(
    config: AppConfig, client
) -> tuple[tuple[ResourceConfig, ...], list[str]]:
    resources = {item.name: item for item in config.watch.resources}
    problems: list[str] = []
    if config.watch.auto_sync_from_mta:
        result = client.check()
        allowed_raw = result.payload.get("allowedResources", [])
        allowed = {str(name) for name in allowed_raw} if isinstance(allowed_raw, list) else set()
        root = config.watch.resources_root
        if root is not None:
            discovered, discovery_problems = discover_resource_paths(root, allowed - set(resources))
            resources.update(discovered)
            problems.extend(discovery_problems)
    return tuple(sorted(resources.values(), key=lambda item: item.name.casefold())), problems


def list_resources(config: AppConfig) -> int:
    try:
        resources, problems = resolve_resources_from_mta(config, HotReloadClient(config.mta))
    except HotReloadChannelError as exc:
        log(f"Cannot read the current MTA UI selection: {exc}")
        return 2
    print("Configured MTA resource mappings:")
    for resource in resources:
        print(f"  {resource.name} -> {resource.path}")
    for problem in problems:
        print(f"  WARNING: {problem}")
    return 0 if not problems else 2


def check_connection(config: AppConfig) -> int:
    log(f"Configuration is valid: {config.source_path}")
    if config.watch.resources_root:
        log(f"Resources root is available: {config.watch.resources_root}")
    for resource in config.watch.resources:
        log(f"Folder is available: {resource.path}", resource.name)
    log("Checking MTA authentication and Hot Reload endpoint (no resource will be restarted)...")
    try:
        result = HotReloadClient(config.mta).check()
    except HotReloadChannelError as exc:
        log(f"Connection check failed: {exc}")
        return 2

    allowed_raw = result.payload.get("allowedResources", [])
    allowed = {str(name) for name in allowed_raw} if isinstance(allowed_raw, list) else set()
    missing = [item.name for item in config.watch.resources if item.name not in allowed]
    if missing:
        log("Endpoint is reachable, but these explicit mappings are ignored in the MTA UI: " + ", ".join(missing))
        return 2
    if config.watch.auto_sync_from_mta and config.watch.resources_root:
        _, problems = discover_resource_paths(
            config.watch.resources_root,
            allowed - {item.name for item in config.watch.resources},
        )
        if problems:
            for problem in problems:
                log(f"Auto-sync mapping error: {problem}")
            return 2
    log("Configuration, authentication, endpoint, folders, and allowlist are ready")
    return 0


def manual_reload(config: AppConfig, resource_name: str) -> int:
    try:
        resources, problems = resolve_resources_from_mta(config, HotReloadClient(config.mta))
    except HotReloadChannelError as exc:
        log(f"Cannot read the current MTA UI selection: {exc}")
        return 2
    for problem in problems:
        log(f"Auto-sync mapping error: {problem}")
    resource = next((item for item in resources if item.name == resource_name), None)
    if resource is None:
        print(f"ERROR: resource is not configured: {resource_name}", file=sys.stderr)
        print("Use --list to show configured names.", file=sys.stderr)
        return 2
    candidates = collect_validation_candidates(resource)
    log(f"Manual reload requested; validating {len(candidates)} Lua/XML candidate(s)", resource.name)
    processor = ReloadProcessor(config, HotReloadClient(config.mta))
    return 0 if processor.process(resource, candidates) else 2


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("ERROR: Python 3.11 or newer is required.", file=sys.stderr)
        return 3
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"CONFIGURATION ERROR: {exc}", file=sys.stderr)
        return 2

    if config.validation.enabled and config.validation.lua_compiler is None:
        log("WARNING: no Lua compiler is configured; Lua syntax validation will be skipped")

    if args.list:
        return list_resources(config)
    if args.check:
        return check_connection(config)
    if args.reload:
        return manual_reload(config, args.reload)
    return WatcherApplication(config).run()


if __name__ == "__main__":
    raise SystemExit(main())

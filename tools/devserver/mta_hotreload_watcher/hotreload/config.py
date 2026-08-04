from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class ConfigError(ValueError):
    """Raised when the watcher configuration cannot be used safely."""


@dataclass(frozen=True)
class MTAConfig:
    """Where dev_hotreload lives and how long to wait for it to answer.

    No URL, no account, no password. The watcher reaches the resource by
    writing into its folder, which it can already do -- watching that folder is
    the job. A secret that does not exist beats a secret stored correctly.
    """

    resource_dir: Path
    hotreload_resource: str
    timeout_seconds: float


@dataclass(frozen=True)
class ResourceConfig:
    name: str
    path: Path


@dataclass(frozen=True)
class WatchConfig:
    debounce_ms: int
    ignore_initial_events: bool
    resources: tuple[ResourceConfig, ...]
    resources_root: Path | None
    auto_sync_from_mta: bool
    sync_interval_seconds: float


@dataclass(frozen=True)
class ValidationConfig:
    enabled: bool
    lua_compiler: Path | None
    validate_xml: bool
    block_reload_on_error: bool


@dataclass(frozen=True)
class AppConfig:
    mta: MTAConfig
    watch: WatchConfig
    validation: ValidationConfig
    source_path: Path


def normalize_windows_path(path: str | os.PathLike[str]) -> str:
    """Return a stable comparison key while preserving bracketed path segments."""
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"'{field}' must be a JSON object")
    return value


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{field}' must be a non-empty string")
    return value.strip()


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"'{field}' must be true or false")
    return value


def _required_number(value: Any, field: str, *, minimum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ConfigError(f"'{field}' must be a number greater than or equal to {minimum}")
    return float(value)


def _validate_base_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError("'mta.base_url' must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigError("'mta.base_url' must not contain credentials, a query, or a fragment")
    if parsed.path not in {"", "/"}:
        raise ConfigError("'mta.base_url' must not contain a path")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ConfigError("'mta.base_url' contains an invalid port") from exc
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def load_config(config_path: str | os.PathLike[str]) -> AppConfig:
    path = Path(config_path).expanduser()
    if not path.is_file():
        raise ConfigError(
            f"Configuration file not found: {path}. Copy config.example.json to config.json and edit it."
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Malformed JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration file {path}: {exc}") from exc

    root = _mapping(raw, "configuration")
    mta_raw = _mapping(root.get("mta"), "mta")
    watch_raw = _mapping(root.get("watch"), "watch")
    validation_raw = _mapping(root.get("validation"), "validation")

    for retired, why in (
        ("base_url", "there is no HTTP endpoint any more"),
        ("username", "the channel needs no MTA account"),
        ("password", "the channel needs no password -- delete this line"),
    ):
        if retired in mta_raw:
            raise ConfigError(
                f"'mta.{retired}' is no longer used: {why}. "
                "See config.example.json; the watcher now writes into the "
                "dev_hotreload resource folder instead of calling it over HTTP."
            )
    hotreload_resource = _required_string(
        mta_raw.get("hotreload_resource"), "mta.hotreload_resource"
    )
    timeout_seconds = _required_number(
        mta_raw.get("timeout_seconds"), "mta.timeout_seconds", minimum=0.1
    )

    debounce_value = _required_number(
        watch_raw.get("debounce_ms"), "watch.debounce_ms", minimum=1
    )
    if not debounce_value.is_integer():
        raise ConfigError("'watch.debounce_ms' must be a whole number")
    ignore_initial = _required_bool(
        watch_raw.get("ignore_initial_events"), "watch.ignore_initial_events"
    )

    auto_sync = watch_raw.get("auto_sync_from_mta", False)
    if not isinstance(auto_sync, bool):
        raise ConfigError("'watch.auto_sync_from_mta' must be true or false")
    sync_interval = _required_number(
        watch_raw.get("sync_interval_seconds", 3),
        "watch.sync_interval_seconds",
        minimum=1,
    )

    resources_raw = watch_raw.get("resources", [])
    if not isinstance(resources_raw, list):
        raise ConfigError("'watch.resources' must be a JSON array")

    config_dir = path.resolve().parent
    resources_root: Path | None = None
    root_raw = watch_raw.get("resources_root", "")
    if not isinstance(root_raw, str):
        raise ConfigError("'watch.resources_root' must be a string")
    if root_raw.strip():
        resources_root = Path(root_raw.strip()).expanduser()
        if not resources_root.is_absolute():
            resources_root = config_dir / resources_root
        resources_root = Path(normalize_windows_path(resources_root))
        if not resources_root.is_dir():
            raise ConfigError(f"MTA resources root directory does not exist: {resources_root}")
    if auto_sync and resources_root is None:
        raise ConfigError("'watch.resources_root' is required when auto_sync_from_mta is true")
    if not auto_sync and not resources_raw:
        raise ConfigError("Configure at least one watch.resources entry or enable auto_sync_from_mta")

    resources: list[ResourceConfig] = []
    names: set[str] = set()
    normalized_paths: set[str] = set()
    for index, item in enumerate(resources_raw):
        entry = _mapping(item, f"watch.resources[{index}]")
        name = _required_string(entry.get("name"), f"watch.resources[{index}].name")
        raw_path = _required_string(entry.get("path"), f"watch.resources[{index}].path")
        resource_path = Path(raw_path).expanduser()
        if not resource_path.is_absolute():
            resource_path = config_dir / resource_path
        resource_path = Path(normalize_windows_path(resource_path))

        name_key = name.casefold()
        if name_key in names:
            raise ConfigError(f"Duplicate watched resource name: {name}")
        names.add(name_key)

        path_key = normalize_windows_path(resource_path).casefold()
        if path_key in normalized_paths:
            raise ConfigError(f"Duplicate watched resource path: {resource_path}")
        normalized_paths.add(path_key)

        if not resource_path.is_dir():
            raise ConfigError(f"Watched resource directory does not exist: {resource_path}")
        if name_key == hotreload_resource.casefold() or resource_path.name.casefold() == hotreload_resource.casefold():
            raise ConfigError(
                f"Target path cannot point to the Hot Reload resource itself: {resource_path}"
            )
        resources.append(ResourceConfig(name=name, path=resource_path))

    enabled = _required_bool(validation_raw.get("enabled"), "validation.enabled")
    validate_xml = _required_bool(
        validation_raw.get("validate_xml"), "validation.validate_xml"
    )
    block_on_error = _required_bool(
        validation_raw.get("block_reload_on_error"), "validation.block_reload_on_error"
    )
    compiler_raw = validation_raw.get("lua_compiler")
    if not isinstance(compiler_raw, str):
        raise ConfigError("'validation.lua_compiler' must be a string (empty disables Lua validation)")
    lua_compiler: Path | None = None
    if compiler_raw.strip():
        compiler_path = Path(compiler_raw.strip()).expanduser()
        if not compiler_path.is_absolute():
            compiler_path = config_dir / compiler_path
        compiler_path = compiler_path.resolve()
        if not compiler_path.is_file():
            raise ConfigError(f"Configured Lua compiler does not exist: {compiler_path}")
        lua_compiler = compiler_path

    # Where to write. Named outright if the config says so; otherwise the
    # obvious place, beside the resources being watched. Checked here rather
    # than at the first reload, so a wrong path is a startup error with a name
    # on it instead of a timeout later.
    resource_dir_raw = mta_raw.get("resource_dir", "")
    if not isinstance(resource_dir_raw, str):
        raise ConfigError("'mta.resource_dir' must be a string")
    if resource_dir_raw.strip():
        resource_dir = Path(resource_dir_raw.strip()).expanduser()
        if not resource_dir.is_absolute():
            resource_dir = config_dir / resource_dir
    elif resources_root is not None:
        resource_dir = resources_root / hotreload_resource
    else:
        raise ConfigError(
            "Set 'mta.resource_dir' to the dev_hotreload folder, or set "
            "'watch.resources_root' so it can be found beside the watched resources"
        )
    resource_dir = Path(normalize_windows_path(resource_dir))
    if not resource_dir.is_dir():
        raise ConfigError(f"dev_hotreload resource folder does not exist: {resource_dir}")

    return AppConfig(
        mta=MTAConfig(
            resource_dir=resource_dir,
            hotreload_resource=hotreload_resource,
            timeout_seconds=timeout_seconds,
        ),
        watch=WatchConfig(
            debounce_ms=int(debounce_value),
            ignore_initial_events=ignore_initial,
            resources=tuple(resources),
            resources_root=resources_root,
            auto_sync_from_mta=auto_sync,
            sync_interval_seconds=sync_interval,
        ),
        validation=ValidationConfig(
            enabled=enabled,
            lua_compiler=lua_compiler,
            validate_xml=validate_xml,
            block_reload_on_error=block_on_error,
        ),
        source_path=path.resolve(),
    )

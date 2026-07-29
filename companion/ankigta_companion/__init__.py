"""ANKIGTA companion add-on entry point."""

from __future__ import annotations

import atexit
from pathlib import Path

from .collection_identity import CollectionIdentityService
from .collection_identity_ui import register_collection_identity_settings
from .connection_settings_ui import (
    prompt_initial_connection_setup,
    register_connection_settings,
)
from .lifecycle import CompanionAddon


addon: CompanionAddon | None = None
collection_settings_action: object | None = None
connection_settings_action: object | None = None


def _start_inside_anki() -> None:
    global addon, collection_settings_action, connection_settings_action
    from aqt import appVersion, gui_hooks, mw
    from aqt.qt import QTimer

    user_files = (
        Path(mw.addonManager.addonsFolder(__name__))
        / "user_files"
    )
    addon = CompanionAddon(
        main_window=mw,
        hooks=gui_hooks,
        anki_version=appVersion,
        defer=lambda delay_ms, action: QTimer.singleShot(delay_ms, action),
        identity_service=CollectionIdentityService(
            user_files / "collection-registry.json"
        ),
        connection_settings_path=user_files / "connection-settings.json",
    )
    addon.start()
    collection_settings_action = register_collection_identity_settings(lambda: addon)
    connection_settings_action = register_connection_settings(lambda: addon)
    QTimer.singleShot(
        0,
        lambda: prompt_initial_connection_setup(addon),
    )
    atexit.register(addon.stop)


try:
    import aqt
except ModuleNotFoundError as error:
    if error.name != "aqt":
        raise
else:
    _start_inside_anki()

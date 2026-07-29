"""ANKIGTA companion add-on entry point."""

from __future__ import annotations

import atexit
from pathlib import Path

from .collection_identity import CollectionIdentityService
from .lifecycle import CompanionAddon


addon: CompanionAddon | None = None


def _start_inside_anki() -> None:
    global addon
    from aqt import appVersion, gui_hooks, mw
    from aqt.qt import QTimer

    addon = CompanionAddon(
        main_window=mw,
        hooks=gui_hooks,
        anki_version=appVersion,
        defer=lambda delay_ms, action: QTimer.singleShot(delay_ms, action),
        run_on_main=mw.taskman.run_on_main,
        identity_service=CollectionIdentityService(
            Path(mw.addonManager.addonsFolder(__name__))
            / "user_files"
            / "collection-registry.json"
        ),
    )
    addon.start()
    atexit.register(addon.stop)


try:
    import aqt
except ModuleNotFoundError as error:
    if error.name != "aqt":
        raise
else:
    _start_inside_anki()

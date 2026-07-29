"""ANKIGTA companion add-on entry point."""

from __future__ import annotations

import atexit

from .lifecycle import CompanionAddon


addon: CompanionAddon | None = None


def _start_inside_anki() -> None:
    global addon
    from aqt import appVersion, gui_hooks, mw

    addon = CompanionAddon(
        main_window=mw,
        hooks=gui_hooks,
        anki_version=appVersion,
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

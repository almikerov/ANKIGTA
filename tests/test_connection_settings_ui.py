from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from ankigta_companion.connection_settings_ui import (
    connection_summary,
    prompt_initial_connection_setup,
    resolve_manual_token,
)


class SetupAddon:
    def __init__(self) -> None:
        self.selected: list[Path] = []

    def connection_status(self) -> dict[str, object]:
        return {
            "configured": False,
            "mode": "automatic",
            "port": 32145,
            "tokenProtected": True,
            "unprotectedWarning": False,
            "unprotectedWarningDismissed": False,
        }

    def select_mta_resource_folder(self, folder: Path) -> None:
        self.selected.append(folder)


def test_initial_setup_asks_for_resource_folder_without_secret_copy(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    addon = SetupAddon()

    class FakeFileDialog:
        @staticmethod
        def getExistingDirectory(
            _parent: object,
            _title: str,
        ) -> str:
            return str(resource_folder)

    monkeypatch.setitem(  # type: ignore[attr-defined]
        sys.modules,
        "aqt",
        SimpleNamespace(mw=object()),
    )
    monkeypatch.setitem(  # type: ignore[attr-defined]
        sys.modules,
        "aqt.qt",
        SimpleNamespace(QFileDialog=FakeFileDialog),
    )

    prompt_initial_connection_setup(addon)  # type: ignore[arg-type]

    assert addon.selected == [resource_folder]


def test_connection_summary_masks_token_and_exposes_empty_token_warning() -> None:
    summary = connection_summary(
        {
            "configured": True,
            "mode": "manual",
            "port": 32145,
            "tokenProtected": False,
            "unprotectedWarning": True,
            "unprotectedWarningDismissed": False,
        }
    )

    assert "manual" in summary
    assert "32145" in summary
    assert "token: disabled" in summary
    assert "Warning" in summary


def test_blank_manual_token_keeps_hidden_token_unless_disable_is_explicit() -> None:
    assert resolve_manual_token("", disable_token=False) is None
    assert resolve_manual_token("", disable_token=True) == ""
    assert resolve_manual_token("replacement", disable_token=False) == "replacement"

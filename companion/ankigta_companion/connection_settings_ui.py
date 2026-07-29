from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .lifecycle import CompanionAddon


def connection_summary(status: dict[str, object]) -> str:
    mode = str(status.get("mode", "unknown"))
    port = str(status.get("port", "unknown"))
    protected = status.get("tokenProtected") is True
    lines = [
        f"mode: {mode}",
        f"port: {port}",
        f"token: {'protected (hidden)' if protected else 'disabled'}",
    ]
    if (
        status.get("unprotectedWarning") is True
        and status.get("unprotectedWarningDismissed") is not True
    ):
        lines.append(
            "Warning: token protection is disabled for this local connection."
        )
    return "\n".join(lines)


def resolve_manual_token(
    replacement: str,
    *,
    disable_token: bool,
) -> str | None:
    if replacement:
        return replacement
    if disable_token:
        return ""
    return None


def prompt_initial_connection_setup(addon: CompanionAddon | None) -> None:
    from aqt import mw
    from aqt.qt import QFileDialog

    if addon is None or addon.connection_status()["configured"] is True:
        return
    selected = QFileDialog.getExistingDirectory(
        mw,
        "ANKIGTA — select the MTA resource folder",
    )
    if selected:
        addon.select_mta_resource_folder(Path(selected))


def show_connection_settings(addon: CompanionAddon | None) -> None:
    from aqt import mw
    from aqt.qt import QInputDialog, QLineEdit, QMessageBox

    if addon is None:
        QMessageBox.warning(
            mw,
            "ANKIGTA",
            "Companion connection is unavailable.",
        )
        return
    status = addon.connection_status()
    if status["configured"] is not True:
        prompt_initial_connection_setup(addon)
        return

    dialog = QMessageBox(mw)
    dialog.setWindowTitle("ANKIGTA — advanced connection settings")
    dialog.setText(connection_summary(status))
    automatic_button = dialog.addButton(
        "Automatic Connection Mode",
        QMessageBox.ButtonRole.ActionRole,
    )
    manual_button = dialog.addButton(
        "Set manual port/token…",
        QMessageBox.ButtonRole.ActionRole,
    )
    dismiss_button = None
    if (
        status.get("unprotectedWarning") is True
        and status.get("unprotectedWarningDismissed") is not True
    ):
        dismiss_button = dialog.addButton(
            "Dismiss warning",
            QMessageBox.ButtonRole.ActionRole,
        )
    dialog.addButton(QMessageBox.StandardButton.Cancel)
    dialog.exec()
    clicked = dialog.clickedButton()

    if clicked is automatic_button:
        addon.use_automatic_connection()
        return
    if clicked is dismiss_button:
        addon.dismiss_unprotected_warning()
        return
    if clicked is not manual_button:
        return

    current_port = status.get("port")
    initial_port = current_port if isinstance(current_port, int) else 1
    port, port_ok = QInputDialog.getInt(
        mw,
        "ANKIGTA — Manual Connection Mode",
        "Replacement loopback port:",
        initial_port,
        1,
        65535,
        1,
    )
    if not port_ok:
        return
    token, token_ok = QInputDialog.getText(
        mw,
        "ANKIGTA — Manual Connection Mode",
        "Replacement token (blank keeps the hidden current token):",
        QLineEdit.EchoMode.Password,
        "",
    )
    if not token_ok:
        return
    disable_token = False
    if token == "":
        token_choice = QMessageBox(mw)
        token_choice.setWindowTitle("ANKIGTA — hidden token")
        token_choice.setText(
            "Keep the current hidden token, or explicitly disable token "
            "protection?"
        )
        keep_button = token_choice.addButton(
            "Keep current token",
            QMessageBox.ButtonRole.AcceptRole,
        )
        disable_button = token_choice.addButton(
            "Disable token",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        token_choice.addButton(QMessageBox.StandardButton.Cancel)
        token_choice.exec()
        if token_choice.clickedButton() is keep_button:
            pass
        elif token_choice.clickedButton() is disable_button:
            disable_token = True
        else:
            return
    addon.set_manual_connection(
        port,
        resolve_manual_token(token, disable_token=disable_token),
    )


def register_connection_settings(
    addon_provider: Callable[[], CompanionAddon | None],
) -> object:
    from aqt import mw
    from aqt.qt import QAction

    action = QAction(
        "ANKIGTA: Companion Connection…",
        mw,
    )
    action.triggered.connect(
        lambda _checked=False: show_connection_settings(addon_provider())
    )
    mw.form.menuTools.addAction(action)
    return action

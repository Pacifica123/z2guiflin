"""User-facing application settings."""

from __future__ import annotations

from typing import Any

from ..qt_compat import require_pyqt
from ..theme import THEME_DARK, THEME_LIGHT, apply_application_theme, normalize_theme_name


def make_settings_page(settings: Any) -> Any:
    """Create persistent appearance controls without touching runtime policy."""

    QtCore, QtWidgets = require_pyqt()
    from PyQt6 import QtGui  # type: ignore[import-not-found]

    class ThemeToggle(QtWidgets.QAbstractButton):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            self.setCheckable(True)
            self.setFixedSize(48, 26)
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Переключить светлую/тёмную тему")

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            track = QtGui.QColor("#8e70a0" if self.isChecked() else "#cfc6d4")
            knob = QtGui.QColor("#fffaff")
            painter.setBrush(track)
            painter.drawRoundedRect(self.rect(), 13, 13)
            knob_x = self.width() - 23 if self.isChecked() else 3
            painter.setBrush(knob)
            painter.drawEllipse(knob_x, 3, 20, 20)

    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(12)

    title = QtWidgets.QLabel("Настройки")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel("Параметры интерфейса сохраняются локально через QSettings.")
    intro.setWordWrap(True)

    card = QtWidgets.QFrame()
    card.setObjectName("settingsCard")
    card_layout = QtWidgets.QHBoxLayout(card)
    card_layout.setContentsMargins(16, 14, 16, 14)
    card_layout.setSpacing(14)

    labels = QtWidgets.QVBoxLayout()
    labels.setSpacing(4)
    card_title = QtWidgets.QLabel("Тёмная тема")
    card_title.setObjectName("settingsCardTitle")
    card_hint = QtWidgets.QLabel("Переключение применяется сразу и сохраняется для следующего запуска.")
    card_hint.setObjectName("settingsValueHint")
    card_hint.setWordWrap(True)
    labels.addWidget(card_title)
    labels.addWidget(card_hint)

    toggle = ThemeToggle()
    current_theme = normalize_theme_name(settings.value("ui/theme", THEME_LIGHT))
    toggle.setChecked(current_theme == THEME_DARK)

    current_label = QtWidgets.QLabel("Тёмная" if toggle.isChecked() else "Светлая")
    current_label.setObjectName("settingsValueHint")
    current_label.setMinimumWidth(62)

    def apply_selected_theme(checked: bool) -> None:
        theme_name = THEME_DARK if checked else THEME_LIGHT
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        normalized = apply_application_theme(app, theme_name)
        settings.setValue("ui/theme", normalized)
        settings.sync()
        current_label.setText("Тёмная" if normalized == THEME_DARK else "Светлая")
        toggle.update()

    toggle.toggled.connect(apply_selected_theme)

    card_layout.addLayout(labels, 1)
    card_layout.addWidget(current_label)
    card_layout.addWidget(toggle)

    boundary = QtWidgets.QLabel(
        "Тема меняет только отображение. Runtime, подтверждения, nftables и systemd не затрагиваются."
    )
    boundary.setObjectName("settingsValueHint")
    boundary.setWordWrap(True)

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(card)
    layout.addWidget(boundary)
    layout.addStretch(1)
    return page

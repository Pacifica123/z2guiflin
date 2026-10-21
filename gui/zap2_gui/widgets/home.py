"""«Главная»: витрина программы.

Текст лежит в `assets/showcase/showcase.json`, чтобы его можно было править без кода.
Страница ничего не проверяет и не ходит в сеть: открывается мгновенно и без побочных эффектов.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Callable, Optional

from ..qt_compat import require_pyqt
from ..theme_profiles import theme_profile_from_settings

SHOWCASE_PATH = Path(__file__).resolve().parents[1] / "assets" / "showcase" / "showcase.json"

_FALLBACK = {
    "title": "z2guiflin",
    "lead": "Если вы здесь, вы и так знаете, что это про zapret.",
    "paragraphs": [],
    "credits": [],
    "also": [],
    "refrain": "i just trying..",
}


def load_showcase(path: Path = SHOWCASE_PATH) -> dict[str, Any]:
    """Текст витрины; при битом или отсутствующем файле — короткий запасной вариант."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_FALLBACK)
    if not isinstance(data, dict):
        return dict(_FALLBACK)
    return {**_FALLBACK, **data}


def _name_html(entry: dict[str, Any], link_color: str) -> str:
    name = html.escape(str(entry.get("name", "")))
    url = str(entry.get("url", ""))
    if url.startswith("https://"):
        style = f' style="color:{html.escape(link_color, quote=True)}"' if link_color else ""
        return f'<a href="{html.escape(url, quote=True)}"{style}>{name}</a>'
    return name


def showcase_html(data: dict[str, Any], link_color: str = "") -> str:
    """Тело витрины без заголовка и рефрена (они — отдельные виджеты)."""

    parts = [f"<p><b>{html.escape(str(data.get('lead', '')))}</b></p>"]
    parts += [f"<p>{html.escape(str(p))}</p>" for p in data.get("paragraphs", [])]
    credits = [c for c in data.get("credits", []) if isinstance(c, dict)]
    if credits:
        parts.append(f"<h3>{html.escape(str(data.get('creditsTitle', 'На чьих плечах')))}</h3>")
        parts += [f"<p>{_name_html(c, link_color)} — {html.escape(str(c.get('text', '')))}</p>" for c in credits]
    also = [a for a in data.get("also", []) if isinstance(a, dict)]
    if also:
        names = ", ".join(_name_html(a, link_color) for a in also)
        parts.append(f"<p>{html.escape(str(data.get('alsoTitle', 'Также')))}: {names}.</p>")
    return "\n".join(parts)


def make_home_page(on_start: Optional[Callable[[], None]] = None, path: Path = SHOWCASE_PATH) -> Any:
    """Страница «Главная». `on_start` — переход к диагностике (кнопка скрыта, если не задан)."""

    QtCore, QtWidgets = require_pyqt()
    data = load_showcase(path)

    page = QtWidgets.QWidget()
    outer = QtWidgets.QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QtWidgets.QScrollArea()
    scroll.setObjectName("homeScrollArea")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    content = QtWidgets.QWidget()
    content.setObjectName("homeContent")
    layout = QtWidgets.QVBoxLayout(content)
    layout.setContentsMargins(24, 18, 24, 18)
    layout.setSpacing(12)

    title = QtWidgets.QLabel(str(data.get("title", "z2guiflin")))
    title.setObjectName("pageTitle")
    class _ShowcaseLabel(QtWidgets.QLabel):  # type: ignore[misc, valid-type]
        """Перерисовывает ссылки при смене темы: цвет ссылки — акцент текущей темы."""

        def render(self) -> None:
            settings = QtCore.QSettings("The Grey Network", "z2guiflin")
            self.setText(showcase_html(data, theme_profile_from_settings(settings).colors["accent"]))

        def changeEvent(self, event: Any) -> None:  # noqa: N802
            super().changeEvent(event)
            if event.type() in (QtCore.QEvent.Type.PaletteChange, QtCore.QEvent.Type.StyleChange):
                self.render()

    body = _ShowcaseLabel()
    body.render()
    body.setObjectName("homeShowcaseText")
    body.setTextFormat(QtCore.Qt.TextFormat.RichText)
    body.setWordWrap(True)
    body.setOpenExternalLinks(True)
    body.setMaximumWidth(760)
    body.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)

    layout.addWidget(title)
    layout.addWidget(body)
    if on_start is not None:
        start = QtWidgets.QPushButton("Что-то не открывается? Начать с диагностики →")
        start.setObjectName("homeStartDiagnostics")
        start.clicked.connect(lambda _checked=False: on_start())
        row = QtWidgets.QHBoxLayout()
        row.addWidget(start)
        row.addStretch(1)
        layout.addSpacing(6)
        layout.addLayout(row)
    layout.addStretch(1)

    refrain = QtWidgets.QLabel(f"<i>{html.escape(str(data.get('refrain', '')))}</i>")
    refrain.setObjectName("homeRefrain")
    refrain.setTextFormat(QtCore.Qt.TextFormat.RichText)
    refrain.setStyleSheet("color: palette(placeholder-text);")
    layout.addWidget(refrain)

    scroll.setWidget(content)
    outer.addWidget(scroll)
    return page


__all__ = ["SHOWCASE_PATH", "load_showcase", "showcase_html", "make_home_page"]

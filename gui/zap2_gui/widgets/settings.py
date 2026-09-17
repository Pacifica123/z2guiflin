"""User-facing application settings."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from ..qt_compat import require_pyqt
from ..theme import THEME_DARK, THEME_LIGHT, apply_application_theme, normalize_theme_name
from ..theme_profiles import ThemeProfile, apply_theme_profile, builtin_theme_profile, clear_theme_profile, load_theme_profile, save_theme_profile, save_theme_profile_to_settings, theme_profile_from_settings

_COLOR_FIELDS=(("text","Текст"),("muted","Вторичный текст"),("window","Фон окна"),("surface","Поверхность"),("card","Карточки"),("input","Поля ввода"),("border","Границы"),("control","Кнопки/навигация"),("hover","Наведение"),("selection","Выделение"),("selectionText","Текст выделения"),("accent","Акцент / Пуск"),("noticeBg","Уведомление: фон"),("noticeBorder","Уведомление: граница"),("noticeText","Уведомление: текст"),("noticeBadge","Уведомление: код"),("noticeBadgeText","Уведомление: текст кода"),("statusRunning","Индикатор: запущено"),("statusStopped","Индикатор: остановлено"),("statusWarning","Индикатор: проблема"),("statusUnknown","Индикатор: неизвестно"))

def make_settings_page(settings: Any) -> Any:
    QtCore,QtWidgets=require_pyqt(); from PyQt6 import QtGui
    class ThemeToggle(QtWidgets.QAbstractButton):
        def __init__(self): super().__init__(); self.setCheckable(True); self.setFixedSize(48,26); self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        def paintEvent(self,_event):
            colors = theme_profile_from_settings(settings).colors
            painter=QtGui.QPainter(self); painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing); painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(colors["accent"] if self.isChecked() else colors["border"])); painter.drawRoundedRect(self.rect(),13,13)
            painter.setBrush(QtGui.QColor(colors["input"])); painter.drawEllipse(self.width()-23 if self.isChecked() else 3,3,20,20)
    page=QtWidgets.QWidget(); layout=QtWidgets.QVBoxLayout(page); layout.setContentsMargins(10,10,10,10); layout.setSpacing(12)
    title=QtWidgets.QLabel("Настройки"); title.setObjectName("pageTitle"); intro=QtWidgets.QLabel("Тема настраивается полностью через семантические цвета и метрики; профиль можно импортировать/экспортировать как JSON."); intro.setWordWrap(True)
    scroll=QtWidgets.QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame); body=QtWidgets.QWidget(); bl=QtWidgets.QVBoxLayout(body); bl.setContentsMargins(0,0,6,0)
    group=QtWidgets.QGroupBox("Оформление"); gl=QtWidgets.QVBoxLayout(group)
    row=QtWidgets.QHBoxLayout(); row.addWidget(QtWidgets.QLabel("Тёмная основа")); row.addStretch(1); current_label=QtWidgets.QLabel(); current_label.setObjectName("settingsValueHint"); toggle=ThemeToggle(); current_theme=normalize_theme_name(settings.value("ui/theme", THEME_LIGHT)); toggle.setChecked(current_theme==THEME_DARK); row.addWidget(current_label); row.addWidget(toggle); gl.addLayout(row)
    name=QtWidgets.QLineEdit(); font=QtWidgets.QFontComboBox(); size=QtWidgets.QSpinBox(); size.setRange(8,18); radius=QtWidgets.QSpinBox(); radius.setRange(0,24); nav=QtWidgets.QSpinBox(); nav.setRange(176,360)
    metrics=QtWidgets.QFormLayout(); metrics.addRow("Название",name); metrics.addRow("Шрифт",font); metrics.addRow("Размер шрифта, pt",size); metrics.addRow("Скругление, px",radius); metrics.addRow("Ширина навигации, px",nav); gl.addLayout(metrics)
    grid=QtWidgets.QGridLayout(); edits={}
    for i,(key,label) in enumerate(_COLOR_FIELDS):
        r,c=divmod(i,2); c*=3; edit=QtWidgets.QLineEdit(); edit.setMaxLength(7); pick=QtWidgets.QToolButton(); pick.setText("…"); grid.addWidget(QtWidgets.QLabel(label),r,c); grid.addWidget(edit,r,c+1); grid.addWidget(pick,r,c+2); edits[key]=edit
        def choose(_checked=False,target=edit):
            color=QtWidgets.QColorDialog.getColor(QtGui.QColor(target.text()),page,"Цвет темы");
            if color.isValid(): target.setText(color.name())
        pick.clicked.connect(choose)
    grid.setColumnStretch(1,1); grid.setColumnStretch(4,1); gl.addLayout(grid)
    actions=QtWidgets.QHBoxLayout(); apply_btn=QtWidgets.QPushButton("Применить"); reset_btn=QtWidgets.QPushButton("Сбросить"); import_btn=QtWidgets.QPushButton("Импорт темы…"); export_btn=QtWidgets.QPushButton("Экспорт темы…"); actions.addWidget(apply_btn); actions.addWidget(reset_btn); actions.addStretch(1); actions.addWidget(import_btn); actions.addWidget(export_btn); gl.addLayout(actions)
    theme_status=QtWidgets.QLabel(); theme_status.setObjectName("settingsValueHint"); theme_status.setWordWrap(True); gl.addWidget(theme_status)
    presets=QtWidgets.QGroupBox("Пресеты"); pl=QtWidgets.QVBoxLayout(presets); hot=QtWidgets.QCheckBox("Применять пресет одним кликом"); hot.setChecked(settings.value("presets/one-click-apply",True,type=bool)); hint=QtWidgets.QLabel("При активном Default выполняется stop → смена selection → start; при ошибке запуска — попытка отката. sudo может запроситься повторно после окончания сессии."); hint.setObjectName("settingsValueHint"); hint.setWordWrap(True); pl.addWidget(hot); pl.addWidget(hint)
    boundary=QtWidgets.QLabel("Тема не меняет runtime. Hot-swap выполняется только после явного клика по пресету."); boundary.setObjectName("settingsValueHint"); boundary.setWordWrap(True); bl.addWidget(group); bl.addWidget(presets); bl.addWidget(boundary); bl.addStretch(1); scroll.setWidget(body); layout.addWidget(title); layout.addWidget(intro); layout.addWidget(scroll,1)
    loading={"v":False}
    def from_ui(): return ThemeProfile(name.text(),THEME_DARK if toggle.isChecked() else THEME_LIGHT,{k:e.text() for k,e in edits.items()},font.currentText(),size.value(),radius.value(),nav.value()).normalized()
    def fill(p):
        loading["v"]=True; p=p.normalized(); toggle.setChecked(p.base==THEME_DARK); current_label.setText("Тёмная" if p.base==THEME_DARK else "Светлая"); name.setText(p.name); font.setCurrentText(p.font_family); size.setValue(p.font_size_pt); radius.setValue(p.corner_radius_px); nav.setValue(p.navigation_width_px)
        for k,e in edits.items(): e.setText(p.colors[k])
        loading["v"]=False
    def apply_p(p,msg):
        app=QtWidgets.QApplication.instance();
        if app is None:return
        p=save_theme_profile_to_settings(settings,p); apply_theme_profile(app,p); fill(p); rail=page.window().findChild(QtWidgets.QFrame,"navigationRail");
        if rail is not None: rail.setFixedWidth(p.navigation_width_px)
        theme_status.setText(msg)
    def apply_selected_theme(checked: bool):
        if loading["v"]:return
        theme_name=THEME_DARK if checked else THEME_LIGHT; app=QtWidgets.QApplication.instance();
        if app is None:return
        normalized=apply_application_theme(app, theme_name); settings.setValue("ui/theme", normalized); settings.sync(); apply_p(builtin_theme_profile(normalized),"Основа изменена; цвета сброшены к значениям основы.")
    def apply_custom():
        try: apply_p(from_ui(),"Тема применена и сохранена.")
        except Exception as exc: QtWidgets.QMessageBox.critical(page,"Тема не применена",str(exc))
    def reset():
        p=clear_theme_profile(settings,THEME_DARK if toggle.isChecked() else THEME_LIGHT); app=QtWidgets.QApplication.instance();
        if app: apply_theme_profile(app,p)
        rail=page.window().findChild(QtWidgets.QFrame,"navigationRail");
        if rail is not None: rail.setFixedWidth(p.navigation_width_px)
        fill(p); theme_status.setText("Тема сброшена.")
    def imp():
        fn,_=QtWidgets.QFileDialog.getOpenFileName(page,"Импорт темы","","z2guiflin theme (*.json);;JSON (*.json)");
        if fn:
            try: apply_p(load_theme_profile(Path(fn)),f"Импортировано: {fn}")
            except Exception as exc: QtWidgets.QMessageBox.critical(page,"Тема не импортирована",str(exc))
    def exp():
        fn,_=QtWidgets.QFileDialog.getSaveFileName(page,"Экспорт темы","z2guiflin-theme.json","z2guiflin theme (*.json);;JSON (*.json)");
        if fn:
            try:
                p=Path(fn); p=p if p.suffix.lower()==".json" else p.with_suffix(".json"); save_theme_profile(p,from_ui()); theme_status.setText(f"Сохранено: {p}")
            except Exception as exc: QtWidgets.QMessageBox.critical(page,"Тема не экспортирована",str(exc))
    toggle.toggled.connect(apply_selected_theme); apply_btn.clicked.connect(apply_custom); reset_btn.clicked.connect(reset); import_btn.clicked.connect(imp); export_btn.clicked.connect(exp); hot.toggled.connect(lambda v:(settings.setValue("presets/one-click-apply",bool(v)),settings.sync())); fill(theme_profile_from_settings(settings)); return page

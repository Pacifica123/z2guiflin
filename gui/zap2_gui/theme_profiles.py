"""Portable user theme profiles for z2guiflin."""
from __future__ import annotations
from dataclasses import dataclass
import json, re
from pathlib import Path
from typing import Any, Mapping
from .theme import THEME_DARK, THEME_LIGHT, apply_application_theme, normalize_theme_name

SCHEMA_VERSION = 1
SETTINGS_KEY = "ui/theme-profile-json"
LIGHT_COLORS = {"text":"#3f3945","muted":"#756d7b","window":"#f6f3f7","surface":"#faf8fb","card":"#fdfcfd","input":"#fffefe","border":"#ded6e2","control":"#eee8f1","hover":"#e5dce9","selection":"#d9cbe1","selectionText":"#352d3a","accent":"#8e70a0","noticeBg":"#f6edd7","noticeBorder":"#d9b864","noticeText":"#4b3d32","noticeBadge":"#efe0b8","noticeBadgeText":"#4b3d32","statusRunning":"#4f8b68","statusStopped":"#8a7355","statusWarning":"#b66b5e","statusUnknown":"#756d7b"}
DARK_COLORS = {"text":"#e8e1ec","muted":"#b8adbe","window":"#211e25","surface":"#27232b","card":"#2d2932","input":"#242128","border":"#443d49","control":"#36303b","hover":"#413949","selection":"#5b4765","selectionText":"#fff7ff","accent":"#b493c4","noticeBg":"#3a3325","noticeBorder":"#8a7745","noticeText":"#f0e3c6","noticeBadge":"#4b402b","noticeBadgeText":"#f4e7c7","statusRunning":"#83c69c","statusStopped":"#c9a978","statusWarning":"#e69a89","statusUnknown":"#b8adbe"}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

@dataclass(frozen=True)
class ThemeProfile:
    name: str
    base: str
    colors: Mapping[str,str]
    font_family: str = ""
    font_size_pt: int = 10
    corner_radius_px: int = 8
    navigation_width_px: int = 224
    def normalized(self) -> "ThemeProfile":
        base = normalize_theme_name(self.base)
        defaults = DARK_COLORS if base == THEME_DARK else LIGHT_COLORS
        colors = dict(defaults)
        for key,value in dict(self.colors).items():
            if key in colors:
                value = str(value).strip().lower()
                if not _HEX.fullmatch(value): raise ValueError(f"Некорректный цвет {key}: {value}; нужен #RRGGBB")
                colors[key] = value
        return ThemeProfile(str(self.name).strip() or "Пользовательская тема", base, colors, str(self.font_family).strip(), max(8,min(18,int(self.font_size_pt))), max(0,min(24,int(self.corner_radius_px))), max(176,min(360,int(self.navigation_width_px))))

def builtin_theme_profile(base: str) -> ThemeProfile:
    base = normalize_theme_name(base); colors = DARK_COLORS if base == THEME_DARK else LIGHT_COLORS
    return ThemeProfile("Тёмная" if base == THEME_DARK else "Светлая", base, dict(colors))

def theme_profile_to_dict(profile: ThemeProfile) -> dict[str,Any]:
    p=profile.normalized(); return {"schemaVersion":SCHEMA_VERSION,"name":p.name,"base":p.base,"colors":dict(p.colors),"font":{"family":p.font_family,"sizePt":p.font_size_pt},"metrics":{"cornerRadiusPx":p.corner_radius_px,"navigationWidthPx":p.navigation_width_px}}

def theme_profile_from_dict(data: Mapping[str,Any]) -> ThemeProfile:
    if int(data.get("schemaVersion",1)) != SCHEMA_VERSION: raise ValueError("Неподдерживаемая версия схемы темы")
    base=normalize_theme_name(data.get("base",THEME_LIGHT)); defaults=DARK_COLORS if base==THEME_DARK else LIGHT_COLORS
    font=data.get("font",{}) if isinstance(data.get("font",{}),Mapping) else {}; metrics=data.get("metrics",{}) if isinstance(data.get("metrics",{}),Mapping) else {}; colors=data.get("colors",defaults) if isinstance(data.get("colors",defaults),Mapping) else defaults
    return ThemeProfile(str(data.get("name","Пользовательская тема")),base,{str(k):str(v) for k,v in dict(colors).items()},str(font.get("family","")),int(font.get("sizePt",10)),int(metrics.get("cornerRadiusPx",8)),int(metrics.get("navigationWidthPx",224))).normalized()

def load_theme_profile(path: Path) -> ThemeProfile:
    data=json.loads(path.read_text(encoding="utf-8"));
    if not isinstance(data,dict): raise ValueError("Файл темы должен содержать JSON object")
    return theme_profile_from_dict(data)

def save_theme_profile(path: Path, profile: ThemeProfile) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(theme_profile_to_dict(profile),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def theme_profile_from_settings(settings: Any) -> ThemeProfile:
    base=normalize_theme_name(settings.value("ui/theme",THEME_LIGHT)); raw=settings.value(SETTINGS_KEY,"")
    if not raw: return builtin_theme_profile(base)
    try: return theme_profile_from_dict(json.loads(str(raw)))
    except Exception: return builtin_theme_profile(base)

def save_theme_profile_to_settings(settings: Any, profile: ThemeProfile) -> ThemeProfile:
    p=profile.normalized(); settings.setValue("ui/theme",p.base); settings.setValue(SETTINGS_KEY,json.dumps(theme_profile_to_dict(p),ensure_ascii=False,separators=(",",":"))); settings.sync(); return p

def clear_theme_profile(settings: Any, base: str) -> ThemeProfile:
    p=builtin_theme_profile(base); settings.setValue("ui/theme",p.base); settings.remove(SETTINGS_KEY); settings.sync(); return p

def custom_stylesheet(profile: ThemeProfile) -> str:
    p=profile.normalized(); c=p.colors; family=f'font-family: "{p.font_family.replace(chr(34),"")}";' if p.font_family else ""
    r=p.corner_radius_px
    return f'''\n/* z2guiflin custom theme profile */
QWidget {{ color:{c['text']}; font-size:{p.font_size_pt}pt; {family} }}
QMainWindow, QWidget#appShell, QStackedWidget#contentStack {{ background:{c['window']}; }}
QFrame#navigationRail {{ background:{c['control']}; border-color:{c['border']}; border-radius:{r}px; }}
QFrame#contentSurface, QGroupBox, QFrame#settingsCard {{ background:{c['card']}; border-color:{c['border']}; border-radius:{r}px; }}
QLabel#brandSubtitle, QLabel#navigationHint, QLabel#pageSubtitle, QLabel#mutedText, QLabel#settingsValueHint {{ color:{c['muted']}; }}
QPushButton, QToolButton {{ color:{c['text']}; background:{c['control']}; border-color:{c['border']}; border-radius:{r}px; }}
QPushButton:hover, QToolButton:hover {{ background:{c['hover']}; }}
QLineEdit,QPlainTextEdit,QTextEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTableView,QTreeView,QListView {{ color:{c['text']}; background:{c['input']}; border-color:{c['border']}; selection-background-color:{c['selection']}; selection-color:{c['selectionText']}; border-radius:{r}px; }}
QTableView::viewport,QTreeView::viewport,QListView::viewport,QComboBox QAbstractItemView {{ background:{c['input']}; color:{c['text']}; selection-background-color:{c['selection']}; selection-color:{c['selectionText']}; }}
QListWidget#navigationList::item:hover {{ background:{c['hover']}; }}
QListWidget#navigationList::item:selected {{ background:{c['selection']}; color:{c['selectionText']}; }}
QHeaderView::section {{ color:{c['text']}; background:{c['control']}; border-color:{c['border']}; }}
QPushButton#primaryRunButton {{ color:{c['accent']}; background:transparent; border:1px solid {c['accent']}; border-radius:{max(8,r)}px; }}
QPushButton#primaryRunButton:hover {{ background:{c['hover']}; }}
QFrame#launchIssueBanner {{ color:{c['noticeText']}; border:1px solid {c['noticeBorder']}; border-radius:{r}px; background:{c['noticeBg']}; }}
QLabel#launchIssueCode {{ color:{c['noticeBadgeText']}; background:{c['noticeBadge']}; border-radius:{max(4,r//2)}px; }}
QLabel#launchIssueMessage {{ color:{c['noticeText']}; }}
QLabel#runtimeStatusIndicator {{ background:transparent; border:0; color:{c['statusUnknown']}; }}
QLabel#runtimeStatusIndicator[state="running"] {{ color:{c['statusRunning']}; }}
QLabel#runtimeStatusIndicator[state="stopped"] {{ color:{c['statusStopped']}; }}
QLabel#runtimeStatusIndicator[state="mismatch"] {{ color:{c['statusWarning']}; }}
QLabel#runtimeStatusIndicator[state="unknown"] {{ color:{c['statusUnknown']}; }}
QGroupBox#discordMachineDiagnosticsBox, QFrame#discordMachineSummaryFrame {{ background:{c['card']}; border:1px solid {c['border']}; border-radius:{r}px; }}
QPushButton#discordMachineProbeButton {{ color:{c['accent']}; background:transparent; border:1px solid {c['accent']}; border-radius:{max(8,r)}px; }}
QPushButton#discordMachineProbeButton:hover {{ background:{c['hover']}; }}
QDialog#discordMachineDiagnosticsDialog {{ background:{c['window']}; }}
QToolButton#discordMachineDetailsToggle {{ color:{c['accent']}; background:transparent; border:0; text-align:left; }}
QLabel#discordMachineSummarySeverity {{ color:{c['statusUnknown']}; font-weight:700; }}
QLabel#discordMachineSummarySeverity[severity="error"] {{ color:{c['statusWarning']}; }}
QLabel#discordMachineSummarySeverity[severity="warning"] {{ color:{c['statusStopped']}; }}
QLabel#discordMachineSummarySeverity[severity="ok"] {{ color:{c['statusRunning']}; }}
'''

def apply_theme_profile(app: Any, profile: ThemeProfile) -> ThemeProfile:
    p=profile.normalized(); apply_application_theme(app,p.base); app.setStyleSheet(app.styleSheet()+custom_stylesheet(p)); return p

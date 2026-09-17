"""各種設定の区分（パネル）定義。"""

from __future__ import annotations

from data.routes import ROUTES

SETTINGS_PANELS: list[dict] = [
    {"id": "staffing", "key": "settings-staffing", "label": "勤務と必要人数", "subtitle": "勤務の名前・記号・時間・配置人数", "section_id": "section-staffing"},
    {"id": "rules", "key": "settings-rules", "label": "休みと夜勤", "subtitle": "公休・連続勤務・夜勤ルール", "section_id": "section-rules"},
    {"id": "display", "key": "settings-display", "label": "表示と印刷", "subtitle": "カレンダーと印刷の見え方", "section_id": "section-display"},
    {"id": "facility", "key": "settings-facility", "label": "施設情報", "subtitle": "施設名・種類・シフトの期間", "section_id": "section-facility"},
]

SETTINGS_PANEL_BY_ID = {panel["id"]: panel for panel in SETTINGS_PANELS}
SETTINGS_PANEL_IDS = frozenset(SETTINGS_PANEL_BY_ID.keys())


def settings_panel_href(panel_id: str) -> str:
    if panel_id == "top":
        return ROUTES["settings"]
    return f"{ROUTES['settings']}?panel={panel_id}"


def resolve_settings_panel(panel: str | None) -> dict:
    aliases = {"auto": "rules", "print": "display", "alert": "display",
               "notify": "facility", "security": "facility", "account": "facility", "top": "staffing"}
    return SETTINGS_PANEL_BY_ID.get(aliases.get(panel, panel), SETTINGS_PANELS[0])


def settings_sidebar_links() -> list[dict]:
    return [
        {
            "label": panel["label"],
            "key": panel["key"],
            "href": settings_panel_href(panel["id"]),
        }
        for panel in SETTINGS_PANELS
    ]

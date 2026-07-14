"""各種設定の区分（パネル）定義。"""

from __future__ import annotations

from data.routes import ROUTES

SETTINGS_PANELS: list[dict] = [
    {
        "id": "top",
        "key": "settings",
        "label": "設定トップ",
        "subtitle": "設定区分を選んでください。",
        "section_id": "section-top",
    },
    {
        "id": "facility",
        "key": "settings-facility",
        "label": "施設情報",
        "subtitle": "施設名・種別・管理者表示名",
        "section_id": "section-facility",
    },
    {
        "id": "display",
        "key": "settings-display",
        "label": "表示ルール",
        "subtitle": "カレンダー・勤務区分・記号",
        "section_id": "section-display",
    },
    {
        "id": "print",
        "key": "settings-print",
        "label": "印刷",
        "subtitle": "用紙・倍率・ヘッダー",
        "section_id": "section-print",
    },
    {
        "id": "staffing",
        "key": "settings-staffing",
        "label": "配置ルール",
        "subtitle": "必要人数・勤務制約",
        "section_id": "section-staffing",
    },
    {
        "id": "alert",
        "key": "settings-alert",
        "label": "アラート",
        "subtitle": "充足率・人員警告",
        "section_id": "section-alert",
    },
    {
        "id": "auto",
        "key": "settings-auto",
        "label": "自動生成",
        "subtitle": "基本設定と詳細設定",
        "section_id": "section-auto",
    },
    {
        "id": "account",
        "key": "settings-account",
        "label": "アカウント",
        "subtitle": "サブスクリプション（準備中）",
        "section_id": "section-account-plan",
    },
    {
        "id": "security",
        "key": "settings-security",
        "label": "セキュリティ",
        "subtitle": "ログ・セッション",
        "section_id": "section-security",
    },
    {
        "id": "notify",
        "key": "settings-notify",
        "label": "通知",
        "subtitle": "締切・リマインド",
        "section_id": "section-notify",
    },
]

SETTINGS_PANEL_BY_ID = {panel["id"]: panel for panel in SETTINGS_PANELS}
SETTINGS_PANEL_IDS = frozenset(SETTINGS_PANEL_BY_ID.keys())


def settings_panel_href(panel_id: str) -> str:
    if panel_id == "top":
        return ROUTES["settings"]
    return f"{ROUTES['settings']}?panel={panel_id}"


def resolve_settings_panel(panel: str | None) -> dict:
    if panel and panel in SETTINGS_PANEL_BY_ID:
        return SETTINGS_PANEL_BY_ID[panel]
    return SETTINGS_PANEL_BY_ID["top"]

from data.routes import ROUTES

# サイドバーは主要画面のみ。設定の細区分は /settings 内サブナビで扱う。
MENU = [
    {"label": "ダッシュボード", "key": "dashboard", "icon": "dashboard"},
    {"label": "シフトカレンダー", "key": "calendar", "icon": "calendar"},
    {"label": "休み希望管理", "key": "leave-request", "icon": "leave"},
    {"label": "職員管理", "key": "staff", "icon": "staff"},
    {"label": "各種設定", "key": "settings", "icon": "settings"},
]


def _with_href(item: dict) -> dict:
    entry = {**item}
    if "href" not in entry and "key" in entry:
        entry["href"] = ROUTES.get(entry["key"], "#")
    return entry


def _is_settings_active(active_key: str) -> bool:
    return active_key == "settings" or active_key.startswith("settings-")


def get_sidebar(active_key: str) -> list[dict]:
    menu = []
    for item in MENU:
        entry = _with_href(item)
        if item.get("key") == "settings":
            entry["active"] = _is_settings_active(active_key)
        else:
            entry["active"] = item.get("key") == active_key
        menu.append(entry)
    return menu

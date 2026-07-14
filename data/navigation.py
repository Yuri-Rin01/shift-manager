from data.routes import ROUTES
from data.settings_panels import settings_sidebar_links

SETTINGS_SECTION_LINKS = settings_sidebar_links()

MENU = [
    {"label": "ダッシュボード", "key": "dashboard"},
    {
        "label": "シフト管理",
        "key": "shift",
        "children": [
            {"label": "シフトカレンダー", "key": "calendar"},
            {"label": "休み希望管理", "key": "leave-request"},
        ],
    },
    {
        "label": "マスタ管理",
        "key": "master",
        "children": [
            {"label": "職員管理", "key": "staff"},
        ],
    },
    {
        "label": "各種設定",
        "key": "settings",
        "children": SETTINGS_SECTION_LINKS,
    },
]


def _with_href(item: dict) -> dict:
    entry = {**item}
    if "href" not in entry and "key" in entry:
        entry["href"] = ROUTES.get(entry["key"], "#")
    return entry


def _is_settings_group_active(active_key: str) -> bool:
    return active_key == "settings" or active_key.startswith("settings-")


def get_sidebar(active_key: str) -> list[dict]:
    menu = []
    for item in MENU:
        entry = _with_href(item)
        if item.get("children"):
            children = []
            for child in item["children"]:
                child_entry = {**_with_href(child), "active": child["key"] == active_key}
                children.append(child_entry)
            entry["children"] = children
            if item.get("key") == "settings":
                entry["active"] = _is_settings_group_active(active_key)
            else:
                entry["active"] = any(child["active"] for child in children)
        else:
            entry["active"] = item.get("key") == active_key
        menu.append(entry)
    return menu

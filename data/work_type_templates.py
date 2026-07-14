"""勤務区分テンプレート（設定画面のプルダウン用）。"""

from __future__ import annotations

DEFAULT_WORK_HOURS: dict[str, tuple[str, str]] = {
    "early": ("07:00", "16:00"),
    "semi_early": ("08:00", "17:00"),
    "day": ("08:30", "17:30"),
    "semi_day": ("09:00", "18:00"),
    "late": ("12:00", "21:00"),
    "semi_late": ("13:00", "22:00"),
    "night": ("16:30", "09:00"),
    "semi_night": ("17:30", "09:00"),
}

WORK_TYPE_TEMPLATES: list[dict] = [
    {
        "id": "standard",
        "label": "標準（早番・日勤・夜勤）",
        "description": "一般的な3区分",
        "keys": ["early", "day", "night"],
    },
    {
        "id": "with_semi",
        "label": "準勤務込み（全8区分）",
        "description": "準早・準日・準遅・準夜を含む",
        "keys": [
            "early",
            "semi_early",
            "day",
            "semi_day",
            "late",
            "semi_late",
            "night",
            "semi_night",
        ],
    },
    {
        "id": "care",
        "label": "介護施設向け",
        "description": "早番・日勤・遅出・夜勤",
        "keys": ["early", "day", "late", "night"],
    },
    {
        "id": "hospital",
        "label": "病院向け",
        "description": "早番・日勤・遅出・夜勤",
        "keys": ["early", "day", "late", "night"],
    },
    {
        "id": "simple",
        "label": "シンプル（日勤・夜勤）",
        "description": "日勤中心の2区分",
        "keys": ["day", "night"],
    },
]

_LABELS: dict[str, str] = {
    "early": "早番",
    "semi_early": "準早",
    "day": "日勤",
    "semi_day": "準日",
    "late": "遅出",
    "semi_late": "準遅",
    "night": "夜勤",
    "semi_night": "準夜",
}


def default_times_for_key(key: str) -> tuple[str, str]:
    return DEFAULT_WORK_HOURS.get(key, ("09:00", "18:00"))


def build_template_options(template_id: str) -> list[dict]:
    template = next((item for item in WORK_TYPE_TEMPLATES if item["id"] == template_id), None)
    if template is None:
        return []
    options: list[dict] = []
    for key in template["keys"]:
        start_time, end_time = default_times_for_key(key)
        options.append(
            {
                "key": key,
                "label": _LABELS.get(key, key),
                "start_time": start_time,
                "end_time": end_time,
            }
        )
    return options


def get_work_type_templates() -> list[dict]:
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "description": item.get("description", ""),
            "options": build_template_options(item["id"]),
        }
        for item in WORK_TYPE_TEMPLATES
    ]

"""配置ルール（最低人数など）の正規化。"""

from __future__ import annotations

import re

from data.staffing_basis import get_staffing_basis_keys, get_staffing_basis_options

LEGACY_MIN_STAFF_KEYS = {
    "early": "min_early_staff",
    "day": "min_day_staff",
    "night": "min_night_staff",
}

DEFAULT_MIN_STAFF_BY_WORK_TYPE: dict[str, int] = {
    "early": 1,
    "day": 2,
    "night": 1,
}

STAFFING_REQUIREMENT_MODES = frozenset({"work_type", "time_slot"})

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULT_TIME_SLOT_STAFFING_RULES: list[dict] = [
    {"label": "早番帯", "start_time": "07:00", "end_time": "16:00", "min_staff": 2},
    {"label": "日勤帯", "start_time": "08:30", "end_time": "17:30", "min_staff": 3},
    {"label": "夜勤帯", "start_time": "16:30", "end_time": "09:00", "min_staff": 1},
]


def get_floor_labels() -> list[str]:
    from data.masters import get_departments

    return [item["label"] for item in get_departments()]


def normalize_staffing_requirement_mode(value: str | None) -> str:
    cleaned = str(value or "work_type").strip()
    return cleaned if cleaned in STAFFING_REQUIREMENT_MODES else "work_type"


def normalize_time_slot_rule(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    label = str(item.get("label", "")).strip()
    start_time = str(item.get("start_time", "")).strip()
    end_time = str(item.get("end_time", "")).strip()
    if not start_time or not end_time:
        return None
    if not _TIME_PATTERN.match(start_time) or not _TIME_PATTERN.match(end_time):
        return None
    if start_time == end_time:
        return None
    try:
        min_staff = int(item.get("min_staff", 0))
    except (TypeError, ValueError):
        return None
    floor = str(item.get("floor", "")).strip()
    allowed_floors = set(get_floor_labels())
    if floor and floor not in allowed_floors:
        return None
    return {
        "label": label[:20],
        "start_time": start_time,
        "end_time": end_time,
        "min_staff": max(0, min(99, min_staff)),
        "floor": floor,
    }


def normalize_time_slot_staffing_rules(raw: list | None) -> list[dict]:
    if not isinstance(raw, list):
        return [dict(item) for item in DEFAULT_TIME_SLOT_STAFFING_RULES]
    normalized: list[dict] = []
    for item in raw:
        rule = normalize_time_slot_rule(item)
        if rule:
            normalized.append(rule)
    return normalized if normalized else [dict(item) for item in DEFAULT_TIME_SLOT_STAFFING_RULES]


def build_time_slots_from_work_types(settings: dict | None = None) -> list[dict]:
    rules: list[dict] = []
    for item in get_staffing_basis_options(settings):
        min_staff = DEFAULT_MIN_STAFF_BY_WORK_TYPE.get(item["key"], 1)
        rules.append(
            {
                "label": item["label"],
                "start_time": item["start_time"],
                "end_time": item["end_time"],
                "min_staff": min_staff,
            }
        )
    return rules if rules else [dict(item) for item in DEFAULT_TIME_SLOT_STAFFING_RULES]


def normalize_min_staff_by_work_type(raw: dict | None, settings: dict | None = None) -> dict[str, int]:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    allowed = get_staffing_basis_keys(cfg)
    result: dict[str, int] = {}

    if isinstance(raw, dict):
        for key, value in raw.items():
            cleaned_key = str(key).strip()
            if cleaned_key not in allowed:
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            result[cleaned_key] = max(0, min(99, count))

    for key in allowed:
        if key in result:
            continue
        legacy_field = LEGACY_MIN_STAFF_KEYS.get(key)
        if legacy_field and legacy_field in cfg:
            try:
                result[key] = max(0, min(99, int(cfg[legacy_field])))
                continue
            except (TypeError, ValueError):
                pass
        if key in DEFAULT_MIN_STAFF_BY_WORK_TYPE:
            result[key] = DEFAULT_MIN_STAFF_BY_WORK_TYPE[key]
        else:
            result[key] = 0

    return {key: result[key] for key in sorted(result)}


def normalize_min_staff_by_floor(raw: dict | None, settings: dict | None = None) -> dict[str, dict[str, int]]:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    floors = get_floor_labels()
    global_defaults = normalize_min_staff_by_work_type(cfg.get("min_staff_by_work_type"), cfg)
    allowed = get_staffing_basis_keys(cfg)
    source = raw if isinstance(raw, dict) else {}
    result: dict[str, dict[str, int]] = {}

    for floor in floors:
        floor_raw = source.get(floor)
        floor_values = floor_raw if isinstance(floor_raw, dict) else {}
        merged: dict[str, int] = {}
        for key in allowed:
            if key in floor_values:
                try:
                    merged[key] = max(0, min(99, int(floor_values[key])))
                    continue
                except (TypeError, ValueError):
                    pass
            if key in global_defaults:
                merged[key] = global_defaults[key]
            elif key in DEFAULT_MIN_STAFF_BY_WORK_TYPE:
                merged[key] = DEFAULT_MIN_STAFF_BY_WORK_TYPE[key]
            else:
                merged[key] = 0
        result[floor] = {key: merged[key] for key in sorted(merged)}

    return result


def validate_min_staff_by_floor(settings: dict) -> None:
    if normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode")) != "work_type":
        return
    raw = settings.get("min_staff_by_floor")
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise ValueError("フロア別必要人数の形式が不正です。")
    allowed_floors = set(get_floor_labels())
    allowed_keys = get_staffing_basis_keys(settings)
    for floor, values in raw.items():
        cleaned_floor = str(floor).strip()
        if cleaned_floor not in allowed_floors:
            raise ValueError(f"未登録のフロアです: {cleaned_floor}")
        if not isinstance(values, dict):
            raise ValueError(f"フロア「{cleaned_floor}」の必要人数形式が不正です。")
        for key, value in values.items():
            cleaned_key = str(key).strip()
            if cleaned_key not in allowed_keys:
                raise ValueError(f"未登録の勤務区分です: {cleaned_key}")
            try:
                count = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"フロア「{cleaned_floor}」の「{cleaned_key}」の必要人数が不正です。") from None
            if count < 0 or count > 99:
                raise ValueError("必要人数は0〜99で入力してください。")


def validate_min_staff_by_work_type(settings: dict) -> None:
    if normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode")) != "work_type":
        return
    raw = settings.get("min_staff_by_work_type")
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise ValueError("区分別最低人数の形式が不正です。")
    allowed = get_staffing_basis_keys(settings)
    for key, value in raw.items():
        cleaned_key = str(key).strip()
        if cleaned_key not in allowed:
            raise ValueError(f"未登録の勤務区分です: {cleaned_key}")
        try:
            count = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"「{cleaned_key}」の最低人数が不正です。") from None
        if count < 0 or count > 99:
            raise ValueError("最低人数は0〜99で入力してください。")


def validate_time_slot_staffing_rules(settings: dict) -> None:
    if normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode")) != "time_slot":
        return
    raw = settings.get("time_slot_staffing_rules")
    if not isinstance(raw, list) or not raw:
        raise ValueError("時間帯ごとの必要人数を1件以上登録してください。")

    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"時間帯ルール {index} 行目の形式が不正です。")
        label = str(item.get("label", "")).strip()
        start_time = str(item.get("start_time", "")).strip()
        end_time = str(item.get("end_time", "")).strip()
        if len(label) > 20:
            raise ValueError(f"時間帯ルール {index} 行目: 名称は20文字以内にしてください。")
        if not start_time or not end_time:
            raise ValueError(f"時間帯ルール {index} 行目: 開始・終了時刻を入力してください。")
        if not _TIME_PATTERN.match(start_time) or not _TIME_PATTERN.match(end_time):
            raise ValueError(f"時間帯ルール {index} 行目: 時刻は HH:MM 形式（例: 08:30）で入力してください。")
        if start_time == end_time:
            raise ValueError(f"時間帯ルール {index} 行目: 開始と終了時刻は異なる値にしてください。")
        floor = str(item.get("floor", "")).strip()
        allowed_floors = set(get_floor_labels())
        if floor and floor not in allowed_floors:
            raise ValueError(f"時間帯ルール {index} 行目: 未登録のフロアです。")
        try:
            min_staff = int(item.get("min_staff", 0))
        except (TypeError, ValueError):
            raise ValueError(f"時間帯ルール {index} 行目: 必要人数が不正です。") from None
        if min_staff < 0 or min_staff > 99:
            raise ValueError("必要人数は0〜99で入力してください。")

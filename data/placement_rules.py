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
]

NIGHT_WORK_KEYS = frozenset({"night", "semi_night"})


def is_overnight_time_range(start_time: str, end_time: str) -> bool:
    """終了が開始より前＝日跨ぎ（夜勤帯）。"""
    start = str(start_time or "").strip()
    end = str(end_time or "").strip()
    return bool(start and end and end < start)


def is_overnight_time_slot_rule(rule: dict | None) -> bool:
    if not isinstance(rule, dict):
        return False
    return is_overnight_time_range(rule.get("start_time", ""), rule.get("end_time", ""))


def is_night_work_key(key: str | None) -> bool:
    return str(key or "").strip() in NIGHT_WORK_KEYS


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
    # 夜勤は人数固定の別枠のため、時間帯ルールから除外する
    if is_overnight_time_range(start_time, end_time):
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


def extract_overnight_night_requirements(raw_rules: list | None) -> dict[str, int]:
    """旧・夜勤帯時間帯ルールからフロア別夜勤人数を取り出す（キー空文字＝施設全体）。"""
    result: dict[str, int] = {}
    if not isinstance(raw_rules, list):
        return result
    for item in raw_rules:
        if not isinstance(item, dict) or not is_overnight_time_slot_rule(item):
            continue
        try:
            count = int(item.get("min_staff", 0))
        except (TypeError, ValueError):
            continue
        count = max(0, min(99, count))
        if count <= 0:
            continue
        floor = str(item.get("floor", "")).strip()
        result[floor] = max(result.get(floor, 0), count)
    return result


def apply_overnight_rules_to_night_mins(settings: dict) -> bool:
    """時間帯ルール内の夜勤帯をフロア別夜勤人数へ移し、時間帯からは外す。変更があれば True。"""
    raw_rules = settings.get("time_slot_staffing_rules")
    overnight = extract_overnight_night_requirements(raw_rules if isinstance(raw_rules, list) else None)
    daytime = normalize_time_slot_staffing_rules(raw_rules if isinstance(raw_rules, list) else None)
    changed = settings.get("time_slot_staffing_rules") != daytime
    settings["time_slot_staffing_rules"] = daytime
    if not overnight:
        return changed

    floors = get_floor_labels()
    by_floor = settings.get("min_staff_by_floor")
    if not isinstance(by_floor, dict):
        by_floor = {}
        settings["min_staff_by_floor"] = by_floor
        changed = True

    global_count = overnight.get("", 0)
    for floor in floors:
        floor_count = max(overnight.get(floor, 0), global_count)
        if floor_count <= 0:
            continue
        floor_values = by_floor.get(floor)
        if not isinstance(floor_values, dict):
            floor_values = {}
            by_floor[floor] = floor_values
            changed = True
        current = floor_values.get("night")
        try:
            current_int = int(current) if current is not None else 0
        except (TypeError, ValueError):
            current_int = 0
        if floor_count > current_int:
            floor_values["night"] = floor_count
            changed = True

    work_type = settings.get("min_staff_by_work_type")
    if not isinstance(work_type, dict):
        work_type = {}
        settings["min_staff_by_work_type"] = work_type
        changed = True
    primary = max([global_count, *[overnight.get(f, 0) for f in floors]], default=0)
    if primary > 0:
        try:
            current = int(work_type.get("night", 0))
        except (TypeError, ValueError):
            current = 0
        if primary > current:
            work_type["night"] = primary
            changed = True
    return changed


def build_time_slots_from_work_types(settings: dict | None = None) -> list[dict]:
    rules: list[dict] = []
    for item in get_staffing_basis_options(settings):
        key = str(item.get("key", "")).strip()
        if is_night_work_key(key):
            continue
        min_staff = DEFAULT_MIN_STAFF_BY_WORK_TYPE.get(key, 1)
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
    # 勤務区分モードでは全体、時間帯モードでは夜勤人数固定枠として常に検証する
    raw = settings.get("min_staff_by_floor")
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise ValueError("フロア別必要人数の形式が不正です。")
    allowed_floors = set(get_floor_labels())
    allowed_keys = get_staffing_basis_keys(settings)
    mode = normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode"))
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
            if mode == "time_slot" and not is_night_work_key(cleaned_key):
                # 時間帯モードでは日中は時間帯ルール側。フロア表の夜勤以外は無視してよいが形式は許可。
                pass
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
        if is_overnight_time_range(start_time, end_time):
            raise ValueError(
                f"時間帯ルール {index} 行目: 夜勤は時間帯ではなく下の「夜勤（人数固定）」で設定してください。"
            )
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


DEFAULT_NIGHT_LEADER_GROUPS: list[dict] = [
    {"label": "1・2階", "floors": ["1F", "2F"], "min_leaders": 1},
    {"label": "2・3階", "floors": ["2F", "3F"], "min_leaders": 1},
]


def normalize_night_leader_group(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    label = str(item.get("label", "")).strip()[:20]
    raw_floors = item.get("floors")
    if not isinstance(raw_floors, list):
        return None
    allowed = set(get_floor_labels())
    order = {floor: index for index, floor in enumerate(get_floor_labels())}
    floors = sorted(
        dict.fromkeys(
            floor
            for floor in (str(value).strip() for value in raw_floors)
            if floor and floor in allowed
        ),
        key=lambda floor: order.get(floor, 999),
    )
    if not floors:
        return None
    try:
        min_leaders = int(item.get("min_leaders", 1))
    except (TypeError, ValueError):
        return None
    return {
        "label": label or "・".join(floors),
        "floors": floors,
        "min_leaders": max(1, min(99, min_leaders)),
    }


def normalize_night_leader_groups(raw: list | None) -> list[dict]:
    """空リストは施設全体1人の従来動作。Noneはデフォルト（1・2階 / 2・3階）。"""
    if raw is None:
        return [dict(item) for item in DEFAULT_NIGHT_LEADER_GROUPS]
    if not isinstance(raw, list):
        return [dict(item) for item in DEFAULT_NIGHT_LEADER_GROUPS]
    normalized: list[dict] = []
    for item in raw:
        group = normalize_night_leader_group(item)
        if group:
            normalized.append(group)
    return normalized


def validate_night_leader_groups(settings: dict) -> None:
    if not settings.get("require_leader_on_night", True):
        return
    raw = settings.get("night_leader_groups")
    if raw is None:
        return
    if not isinstance(raw, list):
        raise ValueError("夜勤リーダー配置グループの形式が不正です。")
    allowed = set(get_floor_labels())
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"夜勤リーダー配置 {index} 行目の形式が不正です。")
        label = str(item.get("label", "")).strip()
        if len(label) > 20:
            raise ValueError(f"夜勤リーダー配置 {index} 行目: 名称は20文字以内にしてください。")
        floors = item.get("floors")
        if not isinstance(floors, list) or not floors:
            raise ValueError(f"夜勤リーダー配置 {index} 行目: フロアを1つ以上選んでください。")
        for floor in floors:
            cleaned = str(floor).strip()
            if cleaned not in allowed:
                raise ValueError(f"夜勤リーダー配置 {index} 行目: 未登録のフロアです（{cleaned}）。")
        try:
            min_leaders = int(item.get("min_leaders", 1))
        except (TypeError, ValueError):
            raise ValueError(f"夜勤リーダー配置 {index} 行目: 必要人数が不正です。") from None
        if min_leaders < 1 or min_leaders > 99:
            raise ValueError("夜勤リーダー必要人数は1〜99で入力してください。")

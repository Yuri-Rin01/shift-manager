"""勤務区分（勤務割合）マスタ。設定で追加・編集可能。"""

from __future__ import annotations

import re

from data.work_type_templates import default_times_for_key

DEFAULT_STAFFING_BASIS_CATALOG: list[dict] = [
    {"key": "early", "label": "早番", **dict(zip(("start_time", "end_time"), default_times_for_key("early")))},
    {"key": "semi_early", "label": "準早", **dict(zip(("start_time", "end_time"), default_times_for_key("semi_early")))},
    {"key": "day", "label": "日勤", **dict(zip(("start_time", "end_time"), default_times_for_key("day")))},
    {"key": "semi_day", "label": "準日", **dict(zip(("start_time", "end_time"), default_times_for_key("semi_day")))},
    {"key": "late", "label": "遅出", **dict(zip(("start_time", "end_time"), default_times_for_key("late")))},
    {"key": "semi_late", "label": "準遅", **dict(zip(("start_time", "end_time"), default_times_for_key("semi_late")))},
    {"key": "night", "label": "夜勤", **dict(zip(("start_time", "end_time"), default_times_for_key("night")))},
    {"key": "semi_night", "label": "準夜", **dict(zip(("start_time", "end_time"), default_times_for_key("semi_night")))},
]

REMOVED_STAFFING_BASIS_KEYS = frozenset({"special", "leader"})

DEFAULT_STAFFING_BASIS_KEYS = ["early", "day", "night"]

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,19}$")
_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _catalog_by_key() -> dict[str, dict]:
    return {item["key"]: item for item in DEFAULT_STAFFING_BASIS_CATALOG}


def normalize_staffing_basis_option(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    key = str(item.get("key", "")).strip()
    label = str(item.get("label", "")).strip()
    if not key or not label or key in REMOVED_STAFFING_BASIS_KEYS:
        return None
    catalog = _catalog_by_key().get(key, {})
    start_time = str(item.get("start_time") or catalog.get("start_time") or "").strip()
    end_time = str(item.get("end_time") or catalog.get("end_time") or "").strip()
    if not start_time or not end_time:
        start_time, end_time = default_times_for_key(key)
    return {
        "key": key,
        "label": label,
        "start_time": start_time,
        "end_time": end_time,
    }


def format_work_hours(start_time: str, end_time: str) -> str:
    if start_time and end_time and end_time < start_time:
        return f"{start_time}〜翌{end_time}"
    if start_time and end_time:
        return f"{start_time}〜{end_time}"
    return ""


def get_staffing_basis_hours_map(settings: dict | None = None) -> dict[str, str]:
    return {
        item["key"]: format_work_hours(item["start_time"], item["end_time"])
        for item in get_staffing_basis_options(settings)
    }


def _catalog_order_map() -> dict[str, int]:
    return {item["key"]: index for index, item in enumerate(DEFAULT_STAFFING_BASIS_CATALOG)}


def sort_staffing_basis_options(options: list[dict]) -> list[dict]:
    order = _catalog_order_map()
    return sorted(
        options,
        key=lambda item: (order.get(str(item.get("key", "")).strip(), 999), str(item.get("key", ""))),
    )


def get_staffing_basis_options(settings: dict | None = None) -> list[dict]:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    stored = cfg.get("staffing_basis_options")
    if not isinstance(stored, list) or not stored:
        return [dict(item) for item in DEFAULT_STAFFING_BASIS_CATALOG]

    options: list[dict] = []
    for item in stored:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        label = str(item.get("label", "")).strip()
        if key and label and key not in REMOVED_STAFFING_BASIS_KEYS:
            normalized = normalize_staffing_basis_option(item)
            if normalized:
                options.append(normalized)
    return sort_staffing_basis_options(options) if options else [dict(item) for item in DEFAULT_STAFFING_BASIS_CATALOG]


def get_staffing_basis_keys(settings: dict | None = None) -> set[str]:
    return {item["key"] for item in get_staffing_basis_options(settings)}


def get_default_staffing_basis_keys(settings: dict | None = None) -> list[str]:
    allowed = get_staffing_basis_keys(settings)
    selected = [key for key in DEFAULT_STAFFING_BASIS_KEYS if key in allowed]
    if selected:
        return selected
    return list(allowed)[:3] or list(allowed)[:1]


def equal_split_ratios(keys: list[str]) -> dict[str, int]:
    if not keys:
        return {}
    count = len(keys)
    base = 100 // count
    remainder = 100 - base * count
    ratios: dict[str, int] = {}
    for index, key in enumerate(keys):
        ratios[key] = base + (1 if index < remainder else 0)
    return ratios


def get_default_staffing_basis_ratios(settings: dict | None = None) -> dict[str, int]:
    return equal_split_ratios(get_default_staffing_basis_keys(settings))


def parse_staffing_basis_raw(raw: str | None, settings: dict | None = None) -> dict[str, int]:
    default = get_default_staffing_basis_ratios(settings)
    if not raw:
        return default
    try:
        import json

        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default

    if isinstance(parsed, list):
        keys = [str(item).strip() for item in parsed if str(item).strip()]
        return equal_split_ratios(keys) if keys else default

    if isinstance(parsed, dict):
        ratios: dict[str, int] = {}
        for key, value in parsed.items():
            cleaned_key = str(key).strip()
            if not cleaned_key or cleaned_key in REMOVED_STAFFING_BASIS_KEYS:
                continue
            try:
                ratio = int(value)
            except (TypeError, ValueError):
                continue
            ratios[cleaned_key] = max(1, min(100, ratio))
        return ratios if ratios else default

    return default


def normalize_staffing_basis_ratios(ratios: dict[str, int]) -> dict[str, int]:
    cleaned: dict[str, int] = {}
    for key, value in ratios.items():
        cleaned_key = str(key).strip()
        if not cleaned_key or cleaned_key in REMOVED_STAFFING_BASIS_KEYS:
            continue
        cleaned[cleaned_key] = max(1, min(100, int(value)))

    if not cleaned:
        return {}

    total = sum(cleaned.values())
    if total == 100:
        return cleaned

    keys = list(cleaned.keys())
    scaled: dict[str, int] = {}
    allocated = 0
    for index, key in enumerate(keys):
        if index == len(keys) - 1:
            scaled[key] = max(1, 100 - allocated)
        else:
            value = max(1, round(cleaned[key] * 100 / total))
            scaled[key] = value
            allocated += value
    return scaled


def validate_staffing_basis_ratios(
    staffing_basis: dict[str, int],
    settings: dict | None = None,
) -> dict[str, int]:
    allowed = get_staffing_basis_keys(settings)
    if not staffing_basis:
        raise ValueError("勤務割合を1つ以上選択してください。")

    cleaned: dict[str, int] = {}
    for key, value in staffing_basis.items():
        cleaned_key = str(key).strip()
        if not cleaned_key or cleaned_key in REMOVED_STAFFING_BASIS_KEYS:
            continue
        try:
            ratio = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"勤務割合「{cleaned_key}」の割合が不正です。") from None
        if ratio < 1 or ratio > 100:
            raise ValueError("各割合は1〜100%で入力してください。")
        cleaned[cleaned_key] = ratio

    if not cleaned:
        raise ValueError("勤務割合を1つ以上選択してください。")

    invalid = [key for key in cleaned if key not in allowed]
    if invalid:
        raise ValueError(f"無効な勤務割合です: {', '.join(invalid)}")

    total = sum(cleaned.values())
    if total != 100:
        raise ValueError(f"勤務割合の合計は100%にしてください（現在{total}%）。")

    return cleaned


def validate_staffing_basis_options(settings: dict) -> None:
    options = settings.get("staffing_basis_options")
    if not isinstance(options, list) or not options:
        raise ValueError("勤務区分を1件以上登録してください。")

    keys: list[str] = []
    labels: list[str] = []
    for index, item in enumerate(options, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"勤務区分 {index} 行目の形式が不正です。")
        key = str(item.get("key", "")).strip()
        label = str(item.get("label", "")).strip()
        if not key:
            raise ValueError(f"勤務区分 {index} 行目: キーを入力してください。")
        if not _KEY_PATTERN.match(key):
            raise ValueError(
                f"勤務区分 {index} 行目: キーは英小文字始まりの a-z, 0-9, _ のみ（20文字以内）にしてください。"
            )
        if not label:
            raise ValueError(f"勤務区分 {index} 行目: 表示名を入力してください。")
        if len(label) > 20:
            raise ValueError(f"勤務区分 {index} 行目: 表示名は20文字以内にしてください。")
        start_time = str(item.get("start_time", "")).strip()
        end_time = str(item.get("end_time", "")).strip()
        if not start_time or not end_time:
            raise ValueError(f"勤務区分 {index} 行目: 開始・終了時刻を入力してください。")
        if not _TIME_PATTERN.match(start_time) or not _TIME_PATTERN.match(end_time):
            raise ValueError(f"勤務区分 {index} 行目: 時刻は HH:MM 形式（例: 08:30）で入力してください。")
        if start_time == end_time:
            raise ValueError(f"勤務区分 {index} 行目: 開始と終了時刻は異なる値にしてください。")
        keys.append(key)
        labels.append(label)

    if len(keys) != len(set(keys)):
        raise ValueError("勤務区分のキーが重複しています。")
    if len(labels) != len(set(labels)):
        raise ValueError("勤務区分の表示名が重複しています。")


def validate_staffing_basis(staffing_basis: list[str], settings: dict | None = None) -> None:
    allowed = get_staffing_basis_keys(settings)
    invalid = [key for key in staffing_basis if key not in allowed]
    if invalid:
        raise ValueError(f"無効な勤務割合です: {', '.join(invalid)}")


def normalize_staffing_basis_options(raw: list[dict] | None) -> list[dict]:
    if not isinstance(raw, list):
        return [dict(item) for item in DEFAULT_STAFFING_BASIS_CATALOG]
    normalized: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        label = str(item.get("label", "")).strip()
        if key and label and key not in REMOVED_STAFFING_BASIS_KEYS:
            option = normalize_staffing_basis_option(item)
            if option:
                normalized.append(option)
    return sort_staffing_basis_options(normalized) if normalized else [dict(item) for item in DEFAULT_STAFFING_BASIS_CATALOG]


def filter_visible_staffing_basis_options(
    options: list[dict] | None = None,
    settings: dict | None = None,
) -> list[dict]:
    from data.shift_symbols import is_work_type_visible

    rows = options if options is not None else get_staffing_basis_options(settings)
    return [item for item in rows if is_work_type_visible(item["key"], settings)]


def night_shift_day_weight(settings: dict | None = None) -> int:
    """夜勤1回あたりの日数換算（人員基準用）。"""
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    return 2 if cfg.get("night_shift_counts_as_two_days", True) else 1

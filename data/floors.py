"""施設フロアの定義（安定ID＋表示名）。

運用データ（職員・配置・必要人数）は表示名を参照する現行互換を保ちつつ、
設定上は id で同一性を保つ。改名時は参照箇所を一括更新する。
"""

from __future__ import annotations

import re
from typing import Any

DEFAULT_FLOORS: list[dict[str, str]] = [
    {"id": "1f", "label": "1F"},
    {"id": "2f", "label": "2F"},
    {"id": "3f", "label": "3F"},
    {"id": "4f", "label": "4F"},
]

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,19}$")
_LABEL_PATTERN = re.compile(r"^.{1,20}$")


def default_floors() -> list[dict[str, str]]:
    return [dict(item) for item in DEFAULT_FLOORS]


def normalize_floors(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        return default_floors()
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        floor_id = str(item.get("id", "")).strip().lower()
        label = str(item.get("label", "")).strip()
        if not floor_id or not label:
            continue
        if not _ID_PATTERN.match(floor_id):
            continue
        if floor_id in seen_ids or label in seen_labels:
            continue
        seen_ids.add(floor_id)
        seen_labels.add(label)
        result.append({"id": floor_id, "label": label})
    return result if result else default_floors()


def validate_floors(floors: list[dict]) -> list[dict[str, str]]:
    normalized = normalize_floors(floors)
    if len(normalized) < 1:
        raise ValueError("フロアを1件以上登録してください。")
    ids = [item["id"] for item in normalized]
    labels = [item["label"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("フロアIDが重複しています。")
    if len(labels) != len(set(labels)):
        raise ValueError("フロア名が重複しています。")
    for index, item in enumerate(normalized, start=1):
        if not _ID_PATTERN.match(item["id"]):
            raise ValueError(f"フロア {index} 行目: IDは英小文字・数字・_ のみ（20文字以内）にしてください。")
        if not _LABEL_PATTERN.match(item["label"]):
            raise ValueError(f"フロア {index} 行目: 表示名は1〜20文字にしてください。")
    return normalized


def get_floors(settings: dict | None = None) -> list[dict[str, str]]:
    if settings is None:
        try:
            from db.settings_repository import get_settings

            settings = get_settings()
        except Exception:
            return default_floors()
    return normalize_floors(settings.get("floors"))


def get_floor_labels(settings: dict | None = None) -> list[str]:
    return [item["label"] for item in get_floors(settings)]


def floor_id_by_label(label: str, settings: dict | None = None) -> str | None:
    for item in get_floors(settings):
        if item["label"] == label:
            return item["id"]
    return None


def floor_label_by_id(floor_id: str, settings: dict | None = None) -> str | None:
    for item in get_floors(settings):
        if item["id"] == floor_id:
            return item["label"]
    return None


def allocate_floor_id(existing: list[dict[str, str]], preferred: str | None = None) -> str:
    used = {item["id"] for item in existing}
    if preferred:
        candidate = re.sub(r"[^a-z0-9_]", "", preferred.strip().lower())
        if candidate and _ID_PATTERN.match(candidate) and candidate not in used:
            return candidate
    for index in range(1, 1000):
        candidate = f"f{index}"
        if candidate not in used:
            return candidate
    raise ValueError("フロアIDを割り当てられません。")


def floor_usage(label: str) -> dict:
    """表示名がどこで使われているか。"""
    from db.database import get_connection

    with get_connection() as conn:
        staff_count = conn.execute(
            "SELECT COUNT(*) AS c FROM staff_floors WHERE floor = ?",
            (label,),
        ).fetchone()["c"]
        primary_count = conn.execute(
            "SELECT COUNT(*) AS c FROM staff WHERE department = ?",
            (label,),
        ).fetchone()["c"]
        placement_count = conn.execute(
            "SELECT COUNT(*) AS c FROM shift_placements WHERE floor = ?",
            (label,),
        ).fetchone()["c"]
    from db.settings_repository import get_settings

    settings = get_settings()
    min_by_floor = settings.get("min_staff_by_floor") or {}
    in_min = label in min_by_floor if isinstance(min_by_floor, dict) else False
    slot_count = 0
    for rule in settings.get("time_slot_staffing_rules") or []:
        if isinstance(rule, dict) and str(rule.get("floor", "")).strip() == label:
            slot_count += 1
    return {
        "label": label,
        "staff_floors": int(staff_count),
        "staff_primary": int(primary_count),
        "placements": int(placement_count),
        "min_staff_rules": 1 if in_min else 0,
        "time_slot_rules": slot_count,
        "in_use": bool(staff_count or primary_count or placement_count or in_min or slot_count),
    }


def rename_floor_label(old_label: str, new_label: str, settings: dict, conn=None) -> dict:
    """表示名を変更し、参照データを一括更新。id は維持。"""
    old_label = str(old_label or "").strip()
    new_label = str(new_label or "").strip()
    if not old_label or not new_label:
        raise ValueError("フロア名を入力してください。")
    if old_label == new_label:
        return settings
    if not _LABEL_PATTERN.match(new_label):
        raise ValueError("フロア名は1〜20文字にしてください。")

    floors = get_floors(settings)
    target = next((item for item in floors if item["label"] == old_label), None)
    if target is None:
        raise ValueError(f"フロア「{old_label}」が見つかりません。")
    if any(item["label"] == new_label for item in floors if item["id"] != target["id"]):
        raise ValueError(f"フロア名「{new_label}」は既に使われています。")

    def _apply(connection) -> None:
        connection.execute("UPDATE staff_floors SET floor = ? WHERE floor = ?", (new_label, old_label))
        connection.execute("UPDATE staff SET department = ? WHERE department = ?", (new_label, old_label))
        connection.execute(
            "UPDATE shift_placements SET floor = ? WHERE floor = ?",
            (new_label, old_label),
        )

    if conn is not None:
        _apply(conn)
    else:
        from db.database import get_connection

        with get_connection() as connection:
            _apply(connection)
            connection.commit()

    updated_floors = []
    for item in floors:
        if item["id"] == target["id"]:
            updated_floors.append({"id": item["id"], "label": new_label})
        else:
            updated_floors.append(dict(item))
    settings = dict(settings)
    settings["floors"] = updated_floors

    min_by_floor = settings.get("min_staff_by_floor")
    if isinstance(min_by_floor, dict) and old_label in min_by_floor:
        next_map = dict(min_by_floor)
        next_map[new_label] = next_map.pop(old_label)
        settings["min_staff_by_floor"] = next_map

    rules = settings.get("time_slot_staffing_rules")
    if isinstance(rules, list):
        settings["time_slot_staffing_rules"] = [
            {**rule, "floor": new_label}
            if isinstance(rule, dict) and str(rule.get("floor", "")).strip() == old_label
            else rule
            for rule in rules
        ]
    return settings


def assert_floor_deletable(label: str) -> None:
    usage = floor_usage(label)
    if usage["in_use"]:
        parts = []
        if usage["staff_floors"] or usage["staff_primary"]:
            parts.append("職員の担当")
        if usage["placements"]:
            parts.append("勤務表の配置")
        if usage["min_staff_rules"] or usage["time_slot_rules"]:
            parts.append("必要人数の設定")
        raise ValueError(
            f"フロア「{label}」は使用中のため削除できません（{'・'.join(parts)}）。"
            "先に担当・配置・人数設定を変更してください。"
        )

"""自動生成の共通初期値・説明文（画面とロジックで共有）。"""

from __future__ import annotations

# 施設の標準夜勤体制（毎日）
# 1F夜勤1名・2F夜勤1名・リーダー1名（1F/2Fを統括）
FACILITY_NIGHT_FLOOR_MINS: dict[str, int] = {
    "1F": 1,
    "2F": 1,
}

DEFAULT_NIGHT_LEADER_GROUP: dict = {
    "label": "1・2階",
    "floors": ["1F", "2F"],
    "min_leaders": 1,
}

# 初めての利用でも生成できる標準初期値
AUTO_GENERATE_DEFAULTS: dict = {
    "max_consecutive_days": 5,
    "max_night_per_week": 2,
    "require_leader_on_night": True,
    "night_leader_groups": [dict(DEFAULT_NIGHT_LEADER_GROUP)],
    "prioritize_leave_requests": True,
    "consider_night_eligibility": True,
    # balance = 偏りを抑える / off = オフ
    "fairness_mode": "balance",
    "confirm_after_generate": True,
    "auto_fill_holidays": False,
    "block_work_after_night": True,
    "morning_off_after_night": True,
    "night_shift_counts_as_two_days": True,
    # 基本は勤務区分ごとのフロア人数（時間帯は詳細）
    "staffing_requirement_mode": "work_type",
}

AUTO_GENERATE_SETTING_HELP: dict[str, str] = {
    "off_days_per_period": "自動生成で割り当てる休み（公休）の標準日数です。空欄だと表示期間内の土日数を使います。職員ごとに違う場合は職員管理で上書きできます。",
    "min_staff_by_floor": "各フロア・各勤務帯で1日に必要な人数です。",
    "night_1f": "1階の夜勤に必要な人数です（標準は1人）。",
    "night_2f": "2階の夜勤に必要な人数です（標準は1人）。",
    "require_leader_on_night": "夜勤のたびに、夜勤リーダー可の職員を1人以上置くかどうかを決めます。",
    "max_consecutive_days": "連続して勤務できる最大日数です。大きいほど緩く、小さいほど厳しくなります。",
    "max_night_per_week": "1週間に割り当てる夜勤の上限回数です。",
    "fairness_mode": "勤務回数や夜勤が一部の職員に偏らないように調整します。",
    "consider_night_eligibility": "「夜勤に入れる」がOFFの職員には夜勤を割り当てません。",
    "prioritize_leave_requests": "承認済みの希望休は必ず守ります（自動生成で上書きしません）。",
    "staffing_requirement_mode": "通常は勤務区分ごとの人数で十分です。時間帯モードは上級者向けです。",
    "night_leader_groups": "リーダーが必要なフロアの組み合わせです。初めての利用では標準の「1・2階で1人」のままで問題ありません。",
    "can_work_night": "夜勤シフトに入れる職員です。",
    "can_be_night_leader": "夜勤リーダーとして配置できる職員です。リーダー可の人は夜勤にも入ります（役職とは別です）。",
    "night_floor_1f": "1階の夜勤に入れる職員です（配置可能フロアに1Fがある夜勤可能者）。",
    "night_floor_2f": "2階の夜勤に入れる職員です（配置可能フロアに2Fがある夜勤可能者）。",
    "night_shift_count": "1か月に割り当てる夜勤回数の上限・固定値です。空欄なら自動で均等に近づきます。",
}

FAIRNESS_UI_OPTIONS: list[dict] = [
    {"value": "balance", "label": "勤務の偏りを抑える"},
    {"value": "off", "label": "偏りの調整をしない"},
]


def apply_facility_night_mins_to_floor_map(min_staff_by_floor: dict | None) -> dict[str, dict[str, int]]:
    """夜勤フロア最小人数の施設標準を既存マップへマージする。"""
    from data.placement_rules import normalize_min_staff_by_floor

    merged = normalize_min_staff_by_floor(min_staff_by_floor)
    for floor, night_min in FACILITY_NIGHT_FLOOR_MINS.items():
        bucket = dict(merged.get(floor) or {})
        if "night" not in bucket or bucket.get("night") is None:
            bucket["night"] = night_min
        merged[floor] = bucket
    return merged


def auto_generate_defaults_for_settings() -> dict:
    """DEFAULT_SETTINGS にマージする自動生成関連キー。"""
    return dict(AUTO_GENERATE_DEFAULTS)

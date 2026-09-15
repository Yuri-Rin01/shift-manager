"""夜勤・夜勤リーダーの必要枠から、登録すべき人数の目安を算出する。"""

from __future__ import annotations


def nights_per_person_capacity(period_days: int, max_night_per_week: int) -> int:
    """1人が期間内にこなせる夜勤の目安回数。

    週上限と、夜勤→明け→休みで約3日かかる制約の小さい方を使う。
    """
    days = max(0, int(period_days or 0))
    if days <= 0:
        return 1
    chain_cap = max(1, days // 3)
    week_cap = int(max_night_per_week or 0)
    if week_cap <= 0:
        return chain_cap
    weeks = max(1, (days + 6) // 7)
    return max(1, min(week_cap * weeks, chain_cap))


def recommend_headcount(period_slots: int, period_days: int, max_night_per_week: int) -> int:
    """期間の夜勤枠に対する登録人数の目安。"""
    slots = max(0, int(period_slots or 0))
    if slots <= 0:
        return 0
    per_person = nights_per_person_capacity(period_days, max_night_per_week)
    return max(1, (slots + per_person - 1) // per_person)


def build_night_staffing_guidance(
    *,
    period_days: int,
    night_mins_by_floor: dict[str, int],
    night_floor_counts: dict[str, int],
    night_capable_count: int,
    night_leader_count: int,
    max_night_per_week: int,
    require_leader_on_night: bool,
    night_leader_groups: list[dict] | None = None,
) -> dict:
    """設定画面・確認画面向けの夜勤／リーダー必要人数ガイダンス。"""
    mins = {str(floor): int(value or 0) for floor, value in (night_mins_by_floor or {}).items()}
    actual_floors = {
        str(floor): int(value or 0) for floor, value in (night_floor_counts or {}).items()
    }
    daily_total = sum(mins.values())
    period_slots = daily_total * max(0, period_days)
    per_person = nights_per_person_capacity(period_days, max_night_per_week)

    recommended_by_floor: dict[str, int] = {}
    for floor, daily in mins.items():
        if daily <= 0:
            recommended_by_floor[floor] = 0
            continue
        # フロア単体枠＋毎日置ける最低人数（daily）の大きい方
        recommended_by_floor[floor] = max(
            daily,
            recommend_headcount(daily * period_days, period_days, max_night_per_week),
        )

    # フロア専任が多い施設向けにフロア別目安の合計を優先し、
    # 共有プールで足りる場合は期間枠からの算出も下限として使う。
    floor_need_sum = sum(recommended_by_floor.values())
    recommended_capable = max(
        daily_total,
        recommend_headcount(period_slots, period_days, max_night_per_week),
        floor_need_sum,
    )

    # リーダー
    leader_daily = 0
    if require_leader_on_night and period_slots > 0:
        groups = night_leader_groups or []
        if groups:
            leader_daily = sum(max(1, int(group.get("min_leaders") or 1)) for group in groups)
        else:
            leader_daily = 1
    leader_period_slots = leader_daily * max(0, period_days)
    recommended_leaders = (
        max(
            leader_daily,
            recommend_headcount(leader_period_slots, period_days, max_night_per_week),
        )
        if leader_daily > 0
        else 0
    )

    floor_lines = []
    for floor in sorted(mins.keys()):
        daily = mins[floor]
        if daily <= 0:
            continue
        actual = actual_floors.get(floor, 0)
        need = recommended_by_floor.get(floor, 0)
        status = "足りています" if actual >= need else "不足しています"
        floor_lines.append(
            f"{floor}は1日{daily}人 → 期間およそ{daily * period_days}枠。"
            f"目安の夜勤対応者は{need}人以上（いま{actual}人・{status}）。"
        )

    night_summary = (
        f"いまの設定では1日あたり夜勤{daily_total}人（期間{period_days}日で約{period_slots}枠）が必要です。"
        f"週上限{max_night_per_week or 'なし'}・明け休みを踏まえると、"
        f"夜勤可能者の目安は合計{recommended_capable}人以上です"
        f"（1人あたりおおよそ{per_person}回まで。いま{night_capable_count}人）。"
    )

    if recommended_leaders > 0:
        leader_ok = night_leader_count >= recommended_leaders
        leader_summary = (
            f"夜勤リーダーは1日{leader_daily}人（期間約{leader_period_slots}枠）必要です。"
            f"目安のリーダー可能者は{recommended_leaders}人以上です"
            f"（いま{night_leader_count}人・{'足りています' if leader_ok else '不足しています'}）。"
        )
    else:
        leader_summary = "夜勤リーダーの毎日配置はオフです。"

    return {
        "period_days": period_days,
        "max_night_per_week": int(max_night_per_week or 0),
        "nights_per_person": per_person,
        "daily_by_floor": mins,
        "daily_total": daily_total,
        "period_slots": period_slots,
        "recommended_capable_total": recommended_capable,
        "recommended_by_floor": recommended_by_floor,
        "actual_capable_total": int(night_capable_count or 0),
        "actual_by_floor": actual_floors,
        "capable_sufficient": int(night_capable_count or 0) >= recommended_capable,
        "leader_daily": leader_daily,
        "leader_period_slots": leader_period_slots,
        "recommended_leaders": recommended_leaders,
        "actual_leaders": int(night_leader_count or 0),
        "leader_sufficient": (
            True if recommended_leaders <= 0 else int(night_leader_count or 0) >= recommended_leaders
        ),
        "floor_lines": floor_lines,
        "night_summary": night_summary,
        "leader_summary": leader_summary,
    }

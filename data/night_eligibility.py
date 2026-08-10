"""夜勤可否の共通ルール。"""

from __future__ import annotations


def resolve_night_flags(*, can_work_night: bool, can_be_night_leader: bool) -> tuple[bool, bool]:
    """夜勤リーダー可なら夜勤にも入れる。"""
    leader = bool(can_be_night_leader)
    night = bool(can_work_night) or leader
    return night, leader


def staff_can_work_night(staff: dict | None) -> bool:
    """職員が夜勤シフトに入れるか（リーダー可も含む）。"""
    if not staff:
        return False
    return bool(staff.get("can_work_night") or staff.get("can_be_night_leader"))


def staff_can_be_night_leader(staff: dict | None) -> bool:
    """職員が夜勤リーダーになれるか。"""
    if not staff:
        return False
    return bool(staff.get("can_be_night_leader")) and staff_can_work_night(staff)

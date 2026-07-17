"""初期投入用のテスト職員データ（介護施設向け）。

テスト要因は 1F / 2F のみに配置する。
職員名はテストA・テストB・テストC…（識別しやすい連番）とする。
"""

from __future__ import annotations


def test_staff_label(index: int) -> str:
    """0→テストA … 25→テストZ / 26→テストAA …"""
    n = int(index)
    if n < 0:
        raise ValueError("index must be >= 0")
    letters: list[str] = []
    n += 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "テスト" + "".join(reversed(letters))


# 旧シード名（同順）。既存DBのリネーム用。
LEGACY_SEED_NAMES: list[str] = [
    "渡辺",
    "山本",
    "中村",
    "井上",
    "松本",
    "石川",
    "森田",
    "阿部",
    "池田",
    "橋本",
    "斉藤",
    "吉田",
    "清水",
    "藤田",
    "岡田",
    "長谷川",
    "山崎",
    "石井",
    "前田",
    "田中",
    "佐藤",
    "山田",
    "鈴木",
    "伊藤",
    "加藤",
    "木村",
    "斎藤",
    "村上",
]

_SEED_STAFF_BASE: list[dict] = [
    # --- 1F 介護 ---
    {"department": "1F", "job_type": "介護士", "position": "主任", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False, "placement_floors": ["1F", "2F"]},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    # --- 2F 介護 ---
    {"department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "2F", "job_type": "介護士", "position": "リーダー", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    {"department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    # --- 看護 ---
    {"department": "1F", "job_type": "看護師", "position": "主任", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    {"department": "1F", "job_type": "看護師", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"department": "1F", "job_type": "看護師", "position": "リーダー", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    {"department": "2F", "job_type": "看護師", "position": "一般", "can_work_night": True, "can_be_night_leader": False, "placement_floors": ["1F", "2F"]},
    {"department": "2F", "job_type": "看護師", "position": "リーダー", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    # --- 日勤中心（夜勤不可） ---
    {"department": "1F", "job_type": "理学療法士", "position": "一般", "can_work_night": False, "can_be_night_leader": False},
    {"department": "2F", "job_type": "作業療法士", "position": "一般", "can_work_night": False, "can_be_night_leader": False},
    {"department": "1F", "job_type": "ケアマネ", "position": "一般", "can_work_night": False, "can_be_night_leader": False},
    {"department": "2F", "job_type": "相談員", "position": "一般", "can_work_night": False, "can_be_night_leader": False},
]

SEED_STAFF: list[dict] = [
    {**row, "name": test_staff_label(index)} for index, row in enumerate(_SEED_STAFF_BASE)
]

assert len(SEED_STAFF) == len(LEGACY_SEED_NAMES)

LEGACY_SEED_NAME_MAP: dict[str, str] = {
    legacy: seed["name"] for legacy, seed in zip(LEGACY_SEED_NAMES, SEED_STAFF, strict=True)
}

"""初期投入用のテスト職員データ（介護施設向け）。

テスト要因は 1F / 2F のみに配置する。
"""

SEED_STAFF: list[dict] = [
    # --- 1F 介護 ---
    {"name": "渡辺", "department": "1F", "job_type": "介護士", "position": "主任", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    {"name": "山本", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "中村", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "井上", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "松本", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False, "placement_floors": ["1F", "2F"]},
    {"name": "石川", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "森田", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "阿部", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "池田", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "橋本", "department": "1F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    # --- 2F 介護 ---
    {"name": "斉藤", "department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "吉田", "department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "清水", "department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "藤田", "department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "岡田", "department": "2F", "job_type": "介護士", "position": "リーダー", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    {"name": "長谷川", "department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "山崎", "department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "石井", "department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "前田", "department": "2F", "job_type": "介護士", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    # --- 看護 ---
    {"name": "田中", "department": "1F", "job_type": "看護師", "position": "主任", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    {"name": "佐藤", "department": "1F", "job_type": "看護師", "position": "一般", "can_work_night": True, "can_be_night_leader": False},
    {"name": "山田", "department": "1F", "job_type": "看護師", "position": "リーダー", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    {"name": "鈴木", "department": "2F", "job_type": "看護師", "position": "一般", "can_work_night": True, "can_be_night_leader": False, "placement_floors": ["1F", "2F"]},
    {"name": "伊藤", "department": "2F", "job_type": "看護師", "position": "リーダー", "can_work_night": True, "can_be_night_leader": True, "placement_floors": ["1F", "2F"]},
    # --- 日勤中心（夜勤不可） ---
    {"name": "加藤", "department": "1F", "job_type": "理学療法士", "position": "一般", "can_work_night": False, "can_be_night_leader": False},
    {"name": "木村", "department": "2F", "job_type": "作業療法士", "position": "一般", "can_work_night": False, "can_be_night_leader": False},
    {"name": "斎藤", "department": "1F", "job_type": "ケアマネ", "position": "一般", "can_work_night": False, "can_be_night_leader": False},
    {"name": "村上", "department": "2F", "job_type": "相談員", "position": "一般", "can_work_night": False, "can_be_night_leader": False},
]

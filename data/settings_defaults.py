DEFAULT_SETTINGS: dict = {
    # 施設
    "facility_name": "○○施設",
    "facility_type": "care",
    "admin_name": "管理者",    # 表示ルール
    "calendar_sort_mode": "dept",
    "default_color_cells": True,
    "default_show_job_column": True,
    "default_show_dept_column": True,
    "default_show_summary": True,
    "show_shift_legend": True,
    "default_table_zoom": 100,
    "week_start": "sunday",
    "calendar_start_day": 1,
    "off_days_per_period": None,
    "highlight_today": False,
    "show_week_number": False,
    "cell_flick_input_enabled": True,
    "cell_long_press_ms": 450,
    # 印刷
    "print_paper": "A4 横",
    "print_scale": "100%",
    "print_color_cells": True,
    "print_header_footer": True,
    "print_page_numbers": True,
    # 配置ルール
    "staffing_basis_options": [
        {"key": "early", "label": "早番", "start_time": "07:00", "end_time": "16:00"},
        {"key": "semi_early", "label": "準早", "start_time": "08:00", "end_time": "17:00"},
        {"key": "day", "label": "日勤", "start_time": "08:30", "end_time": "17:30"},
        {"key": "semi_day", "label": "準日", "start_time": "09:00", "end_time": "18:00"},
        {"key": "late", "label": "遅出", "start_time": "12:00", "end_time": "21:00"},
        {"key": "semi_late", "label": "準遅", "start_time": "13:00", "end_time": "22:00"},
        {"key": "night", "label": "夜勤", "start_time": "16:30", "end_time": "09:00"},
        {"key": "semi_night", "label": "準夜", "start_time": "17:30", "end_time": "09:00"},
    ],
    "min_early_staff": 1,
    "min_day_staff": 2,
    "min_night_staff": 1,
    "min_staff_by_work_type": {
        "early": 1,
        "day": 2,
        "night": 1,
    },
    "min_staff_by_floor": {},
    "staffing_requirement_mode": "time_slot",
    "time_slot_staffing_rules": [
        {"label": "早番帯", "start_time": "07:00", "end_time": "16:00", "min_staff": 2, "floor": "1F"},
        {"label": "日勤帯", "start_time": "08:30", "end_time": "17:30", "min_staff": 3, "floor": "1F"},
        {"label": "夜勤帯", "start_time": "16:30", "end_time": "09:00", "min_staff": 1, "floor": "1F"},
    ],
    "block_work_after_night": True,
    "morning_off_after_night": True,
    "night_shift_counts_as_two_days": True,
    "max_consecutive_days": 5,
    "max_night_per_week": 2,
    "require_leader_on_night": True,
    # アラート
    "leave_alert_threshold": 72,
    "leave_fulfill_target": 90,
    "warn_overstaffing": True,
    "warn_understaffing": True,
    "show_status_bar": True,
    # 自動生成
    "prioritize_leave_requests": True,
    "consider_night_eligibility": True,
    "fairness_mode": "balance",
    "confirm_after_generate": True,
    "auto_fill_holidays": False,
    # セキュリティ
    "log_retention_days": 90,
    "session_timeout_minutes": 60,
    "require_password_change_days": 0,
    # 通知
    "notify_shift_update": True,
    "notify_alerts": True,
    "notify_deadline": True,
    "deadline_day_of_month": 20,
    # 休み希望ポータル連携
    "leave_request_visible_types": {
        "off": True,
        "paid_leave": True,
        "half_leave": True,
    },
    "leave_request_max_total": None,
    "leave_request_max_by_type": {
        "off": 0,
        "paid_leave": 0,
        "half_leave": 0,
    },
    "leave_request_over_limit_message": (
        "希望数が上限（{max}件）を超えています。現在 {count} 件です。"
        "内容を見直すか、管理者にお問い合わせください。"
    ),
    # シフト記号
    "allow_paid_leave_half": True,
    "show_training_mark": True,
    "visible_work_types": {
        "early": True,
        "day": True,
        "late": True,
        "special": True,
        "night": True,
        "morning_off": True,
        "paid_leave": True,
        "half_leave": True,
        "off": True,
        "training": True,
        "semi_early": True,
        "semi_day": True,
        "semi_late": True,
        "semi_night": True,
    },
    "shift_symbols": {
        "early": "●",
        "day": "○",
        "late": "◎",
        "special": "★",
        "night": "夜",
        "morning_off": "明",
        "paid_leave": "有休",
        "half_leave": "半休",
        "off": "×",
        "training": "研",
        "semi_early": "半早",
        "semi_day": "半日",
        "semi_late": "半遅",
        "semi_night": "準夜",
    },
}

FACILITY_TYPE_OPTIONS = [
    {"value": "care", "label": "介護施設"},
    {"value": "hospital", "label": "病院"},
    {"value": "all", "label": "病院・介護施設（統合）"},
]

FACILITY_LABELS = {
    "care": "介護施設",
    "hospital": "病院",
    "all": "病院・介護施設（統合）",
}

WEEK_START_OPTIONS = [
    {"value": "sunday", "label": "日曜始まり"},
    {"value": "monday", "label": "月曜始まり"},
]

CALENDAR_SORT_OPTIONS = [
    {"value": "position", "label": "役職順"},
    {"value": "dept", "label": "フロア順"},
    {"value": "job", "label": "職種順"},
    {"value": "name", "label": "名前順"},
]

STAFF_SORT_OPTIONS = [
    {"value": "dept", "label": "フロア順"},
    {"value": "name", "label": "名前順"},
    {"value": "position", "label": "役職順"},
    {"value": "job", "label": "職種順"},
]

TABLE_ZOOM_OPTIONS = [50, 70, 80, 90, 100, 110, 120, 130, 150, 200]

FAIRNESS_OPTIONS = [
    {"value": "balance", "label": "均等配分"},
    {"value": "experience", "label": "経験者優先"},
    {"value": "newcomer", "label": "新人配慮"},
]

PRINT_PAPER_OPTIONS = ["A4 横", "A4 縦", "A3 横"]
PRINT_SCALE_OPTIONS = ["100%", "90%", "80%", "70%"]

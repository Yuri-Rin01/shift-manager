"""アプリ全体のURL定義。ナビの href はここだけを参照する。"""

ROUTES: dict[str, str] = {
    "dashboard": "/dashboard",
    "calendar": "/",
    "leave-request": "/leave-requests",
    "auto-shift": "/auto-shift",
    "confirm-shift": "/shift/confirm",
    "staff": "/staff",
    "department": "/departments",
    "job-type": "/job-types",
    "qualification": "/qualifications",
    "work-type": "/work-types",
    "display-group": "/display-groups",
    "settings": "/settings",
    "users": "/users",
}

STUB_PAGES: dict[str, tuple[str, str]] = {
    "auto-shift": ("シフト自動生成", "条件に基づくシフトの自動作成"),
    "confirm-shift": ("シフト確定・調整", "シフトの確定と調整"),
    "department": ("フロア管理", "フロア（1F〜4F）マスタの管理"),
    "job-type": ("職種管理", "職種マスタの管理"),
    "qualification": ("資格管理", "資格マスタの管理"),
    "work-type": ("勤務区分管理", "勤務区分マスタの管理"),
    "display-group": ("表示グループ管理", "カレンダー表示グループの管理"),
    "users": ("ユーザー管理", "ログインユーザーの管理"),
}

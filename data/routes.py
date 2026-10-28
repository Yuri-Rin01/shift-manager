"""アプリ全体のURL定義。ナビの href はここだけを参照する。"""

ROUTES: dict[str, str] = {
    "dashboard": "/dashboard",
    "calendar": "/",
    "daily-duties": "/daily-duties",
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

# 仮ページから実機能のある画面への案内（行き止まりにしないためのもの）
STUB_GUIDES: dict[str, tuple[str, str, str]] = {
    "auto-shift": ("シフトの自動生成は、カレンダーの「自動生成」から行います。", "/", "カレンダーを開く"),
    "confirm-shift": ("シフトの確定と調整は、カレンダー上で行います。", "/", "カレンダーを開く"),
    "department": ("フロアの設定は、設定の「勤務と必要人数」で行います。", "/settings?panel=staffing", "設定を開く"),
    "job-type": ("職種の設定は、設定の「勤務と必要人数」で行います。職員への割り当ては職員管理から行います。", "/settings?panel=staffing", "設定を開く"),
    "qualification": ("資格は、職員管理の職員編集で取り扱います。", "/staff", "職員管理を開く"),
    "work-type": ("勤務区分の設定は、設定の「勤務と必要人数」で行います。", "/settings?panel=staffing", "設定を開く"),
    "display-group": ("表示の設定は、設定の「表示と印刷」で行います。", "/settings?panel=display", "設定を開く"),
    "users": ("ユーザー管理の専用画面は未実装です。管理者アカウントは初回セットアップ（/setup）で作成し、職員のポータル用 PIN は職員管理で設定します。", "/staff", "職員管理を開く"),
}

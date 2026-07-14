"""アカウント・サブスクリプション（将来実装用の定義のみ。課金・認証は未実装）。"""

from __future__ import annotations

# 現状ポリシー
AUTH_STATUS = {
    "login_implemented": False,
    "portal_login_planned": False,
    "admin_login_planned": True,
    "subscription_scope": "admin_only",
}

SUBSCRIPTION_STATUS_LABELS = {
    "not_implemented": "未実装（ローカル利用）",
    "planned": "実装予定",
    "active": "有効",
    "trial": "トライアル",
    "expired": "期限切れ",
}

# 管理者向けプラン定義（UI表示・将来の課金連携用）
ADMIN_PLAN_CATALOG: list[dict] = [
    {
        "id": "local",
        "label": "ローカル利用",
        "description": "現行モード。ログイン・課金なし。",
        "status": "not_implemented",
        "features": ["シフト作成", "休み希望管理", "職員マスタ"],
    },
    {
        "id": "standard",
        "label": "スタンダード（予定）",
        "description": "管理者アカウントのサブスクリプション。施設1件・標準機能。",
        "status": "planned",
        "features": ["クラウド同期（予定）", "バックアップ（予定）", "メール通知（予定）"],
    },
    {
        "id": "pro",
        "label": "プロ（予定）",
        "description": "複数拠点・高度な分析（将来）。",
        "status": "planned",
        "features": ["複数施設（予定）", "監査ログ（予定）", "API連携（予定）"],
    },
]

CURRENT_ADMIN_PLAN_ID = "local"


def get_account_plan_context() -> dict:
    current = next(
        (plan for plan in ADMIN_PLAN_CATALOG if plan["id"] == CURRENT_ADMIN_PLAN_ID),
        ADMIN_PLAN_CATALOG[0],
    )
    return {
        "auth_status": AUTH_STATUS,
        "subscription_status_labels": SUBSCRIPTION_STATUS_LABELS,
        "admin_plan_catalog": ADMIN_PLAN_CATALOG,
        "current_admin_plan": current,
        "portal_auth_note": "職員向け休み希望ポータルはログインなし（名前入力で本人確認）。",
        "admin_auth_note": "管理者向けログイン・サブスクリプションは今後、管理アカウントのみに追加予定。",
    }

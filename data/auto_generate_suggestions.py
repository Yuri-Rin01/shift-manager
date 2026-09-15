"""自動生成の警告・エラーに対する改善提案。"""

from __future__ import annotations

# code → 改善提案（利用者向け・専門用語なし）
GENERATE_SUGGESTIONS: dict[str, dict[str, str]] = {
    "no_staff": {
        "suggestion": "職員管理で職員を登録するか、「人員に含めない」のチェックを外してください。",
        "href": "/staff",
        "action_label": "職員管理を開く",
    },
    "empty_scope": {
        "suggestion": "カレンダーの年月や開始日の設定を確認し、表示期間に日が含まれるようにしてください。",
        "href": "/settings?panel=display",
        "action_label": "表示ルールを開く",
    },
    "save_failed": {
        "suggestion": "もう一度生成を試してください。繰り返す場合は手動入力セルを確認するか、管理者に問い合わせてください。",
        "href": "/",
        "action_label": "カレンダーへ戻る",
    },
    "staff_capacity_low": {
        "suggestion": "配置可能フロアに職員を増やすか、そのフロアの必要人数を減らしてください。",
        "href": "/settings?panel=staffing",
        "action_label": "配置ルールを開く",
    },
    "understaffed": {
        "suggestion": "必要人数を下げる、公休数を減らす、連勤上限を緩める（大きくする）、配置可能職員を増やす、のいずれかで改善できます。",
        "href": "/settings?panel=auto",
        "action_label": "自動生成設定を開く",
    },
    "time_slot_understaffed": {
        "suggestion": "時間帯の必要人数を下げるか、対象フロアの配置可能職員を増やしてください。通常は勤務区分ごとの人数設定の方が分かりやすいです。",
        "href": "/settings?panel=staffing",
        "action_label": "配置ルールを開く",
    },
    "time_slot_rules_empty": {
        "suggestion": "時間帯の必要人数を登録するか、配置方式を「勤務区分ごと」に切り替えてください。",
        "href": "/settings?panel=staffing",
        "action_label": "配置ルールを開く",
    },
    "leader_on_night_missing": {
        "suggestion": "職員管理で「夜勤リーダー可」を増やすか、自動生成設定で「夜勤リーダーを毎日置く」を見直してください。リーダー可能者の夜勤回数上限が厳しすぎないかも確認してください。",
        "href": "/staff",
        "action_label": "職員管理を開く",
    },
    "night_count_shortfall": {
        "suggestion": "夜勤の固定回数が多すぎるか、夜勤可能者が足りません。回数固定を外す／減らす、週の夜勤上限を上げる、夜勤可能者を増やす、のいずれかを検討してください。",
        "href": "/staff",
        "action_label": "職員管理を開く",
    },
    "night_quota_capped": {
        "suggestion": "期間の夜勤枠に対して固定回数が多めです。固定回数を下げるか、フロアの夜勤必要人数を見直してください。",
        "href": "/settings?panel=auto",
        "action_label": "自動生成設定を開く",
    },
    "staff_ratio_shortfall": {
        "suggestion": "日勤・早番の目標回数に対し、夜勤・公休・明けの影響で枠が足りていません。勤務割合の目標を下げる、夜勤回数を減らす、連勤上限を緩める、のいずれかが有効です。",
        "href": "/staff",
        "action_label": "職員の勤務割合を見直す",
    },
    "empty_cells_unfilled": {
        "suggestion": "連勤上限や夜勤明けなど制約で埋められない日があります。連勤上限を緩める（大きくする）、希望休の集中日を見直す、必要人数を下げる、を検討してください。",
        "href": "/settings?panel=auto",
        "action_label": "詳細設定（連勤）を開く",
    },
    "off_count_shortfall": {
        "suggestion": "必要人数や夜勤明け優先のため公休が足りません。月間公休数を減らすか、フロアの必要人数を下げてください。",
        "href": "/settings?panel=auto",
        "action_label": "公休数・必要人数を見直す",
    },
    "off_count_excess": {
        "suggestion": "手動の休みや希望休が多く、公休目標より休みが多くなっています。手動休み・希望休を見直すか、月間公休数を実態に合わせてください。",
        "href": "/",
        "action_label": "カレンダーで休みを確認",
    },
    "leave_priority_off": {
        "suggestion": "希望休はロックとして残ります。休み日数の上乗せを強化したい場合は自動生成設定を確認してください。",
        "href": "/settings?panel=auto",
        "action_label": "自動生成設定を開く",
    },
    "night_floor_short": {
        "suggestion": "そのフロアの「夜勤に入れる」＋配置可能フロアが不足しています。職員管理で対象階にチェックを入れてください。",
        "href": "/staff",
        "action_label": "職員管理を開く",
    },
    "no_night_capable": {
        "suggestion": "職員管理で「夜勤に入れる」にチェックを入れてください。",
        "href": "/staff",
        "action_label": "職員管理を開く",
    },
    "no_night_leader": {
        "suggestion": "職員管理で「夜勤リーダー可」を設定するか、自動生成設定でリーダー必須をオフにしてください。",
        "href": "/staff",
        "action_label": "職員管理を開く",
    },
    "few_night_leaders": {
        "suggestion": "リーダー可能者を追加するか、リーダーの夜勤回数上限を上げて負荷を分散してください。",
        "href": "/staff",
        "action_label": "職員管理を開く",
    },
    "night_cap_insufficient": {
        "suggestion": "週の夜勤上限を上げる、夜勤可能者を増やす、フロアの夜勤必要人数を減らす、のいずれかにしてください。",
        "href": "/settings?panel=auto",
        "action_label": "自動生成設定を開く",
    },
    "off_days_impossible": {
        "suggestion": "月間公休数を表示期間より少ない日数に設定してください。",
        "href": "/settings?panel=auto",
        "action_label": "公休数を見直す",
    },
    "many_leave_requests": {
        "suggestion": "希望休が集中している日は、承認前に分散するか、生成後に手動で必要人数を補ってください。",
        "href": "/leave-requests",
        "action_label": "希望休一覧を開く",
    },
    "missing_placement_floors": {
        "suggestion": "職員管理で配置可能フロア（1F/2Fなど）を設定してください。",
        "href": "/staff",
        "action_label": "職員管理を開く",
    },
    "floor_capacity_low": {
        "suggestion": "配置可能フロアに職員を増やすか、必要人数を減らしてください。",
        "href": "/settings?panel=staffing",
        "action_label": "配置ルールを開く",
    },
}


def suggestion_for_code(code: str | None) -> dict[str, str] | None:
    if not code:
        return None
    item = GENERATE_SUGGESTIONS.get(str(code))
    return dict(item) if item else None


def enrich_warning(item: dict) -> dict:
    """警告dictに suggestion / href / action_label を付与する。"""
    enriched = dict(item)
    tip = suggestion_for_code(enriched.get("code"))
    if not tip:
        return enriched
    enriched.setdefault("suggestion", tip["suggestion"])
    enriched.setdefault("href", tip.get("href", ""))
    enriched.setdefault("action_label", tip.get("action_label", "設定を開く"))
    return enriched


def enrich_warnings(warnings: list[dict] | None) -> list[dict]:
    return [enrich_warning(item) for item in (warnings or [])]


def unique_suggestions(warnings: list[dict] | None) -> list[dict]:
    """画面用に重複を除いた改善提案一覧。"""
    seen: set[str] = set()
    result: list[dict] = []
    for item in enrich_warnings(warnings):
        text = (item.get("suggestion") or "").strip()
        if not text or text in seen:
            continue
        if item.get("level") == "info" and item.get("code") == "leave_priority_off":
            continue
        seen.add(text)
        result.append(
            {
                "code": item.get("code") or "",
                "level": item.get("level") or "warn",
                "message": item.get("message") or "",
                "suggestion": text,
                "href": item.get("href") or "",
                "action_label": item.get("action_label") or "開く",
            }
        )
    return result

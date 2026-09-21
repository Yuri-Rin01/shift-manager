"""ユーザー追加のシフト表シート設定。"""

from __future__ import annotations

import re

from data.sheet_view_colors import normalize_sheet_color

_ID_RE = re.compile(r"^custom-[a-z0-9][a-z0-9-]{0,23}$")
MAX_CUSTOM_SHEETS = 8


def normalize_custom_sheet_views(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []

    result: list[dict] = []
    used_ids: set[str] = set()
    for raw in value:
        if len(result) >= MAX_CUSTOM_SHEETS:
            break
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or "").strip()[:20]
        jobs_raw = raw.get("job_types")
        if not label or not isinstance(jobs_raw, list):
            continue
        job_types = list(
            dict.fromkeys(
                str(job).strip()[:50]
                for job in jobs_raw
                if isinstance(job, str) and str(job).strip()
            )
        )
        if not job_types:
            continue

        sheet_id = str(raw.get("id") or "").strip().lower()
        if not _ID_RE.fullmatch(sheet_id) or sheet_id in used_ids:
            number = len(result) + 1
            while f"custom-{number}" in used_ids:
                number += 1
            sheet_id = f"custom-{number}"
        used_ids.add(sheet_id)
        result.append(
            {
                "id": sheet_id,
                "label": label,
                "job_types": job_types,
                "color": normalize_sheet_color(raw.get("color"), "#64748B"),
            }
        )
    return result

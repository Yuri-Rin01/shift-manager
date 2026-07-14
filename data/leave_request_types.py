"""休み希望の種別定義。"""

from __future__ import annotations

LEAVE_REQUEST_TYPES = frozenset({"off", "paid_leave", "half_leave"})

LEAVE_REQUEST_TYPE_META: dict[str, dict[str, str]] = {
    "off": {"label": "希望休", "short_label": "休", "symbol_key": "off"},
    "paid_leave": {"label": "有休", "short_label": "有", "symbol_key": "paid_leave"},
    "half_leave": {"label": "半休", "short_label": "半", "symbol_key": "half_leave"},
}

LEAVE_REQUEST_STATUSES = frozenset({"pending", "approved", "rejected", "cancelled"})

DEFAULT_LEAVE_REQUEST_VISIBLE_TYPES: dict[str, bool] = {
    "off": True,
    "paid_leave": True,
    "half_leave": True,
}

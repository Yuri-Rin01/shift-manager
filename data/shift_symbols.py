"""シフト種別と表示記号の定義・解決。"""

from __future__ import annotations

SHIFT_TYPE_CATALOG: list[dict] = [
    {
        "key": "early",
        "label": "早番",
        "class": "shift-early",
        "default_symbol": "●",
        "summary_label": "早番人数",
        "order": 1,
    },
    {
        "key": "day",
        "label": "日勤",
        "class": "shift-day",
        "default_symbol": "○",
        "summary_label": "日勤人数",
        "order": 2,
    },
    {
        "key": "late",
        "label": "遅出",
        "class": "shift-late",
        "default_symbol": "◎",
        "summary_label": "遅出人数",
        "order": 3,
    },
    {
        "key": "special",
        "label": "当直",
        "class": "shift-special",
        "default_symbol": "★",
        "summary_label": "当直人数",
        "order": 4,
        "facility_types": ("hospital", "all"),
    },
    {
        "key": "night",
        "label": "夜勤",
        "class": "shift-night",
        "default_symbol": "夜",
        "summary_label": "夜勤人数",
        "order": 5,
    },
    {
        "key": "morning_off",
        "label": "明け",
        "class": "shift-morning-off",
        "default_symbol": "明",
        "order": 6,
    },
    {
        "key": "paid_leave",
        "label": "有休",
        "class": "shift-paid-leave",
        "default_symbol": "有休",
        "order": 7,
    },
    {
        "key": "half_leave",
        "label": "半日有休",
        "class": "shift-half-leave",
        "default_symbol": "半休",
        "order": 8,
        "setting_flag": "allow_paid_leave_half",
    },
    {
        "key": "off",
        "label": "休み",
        "class": "shift-off",
        "default_symbol": "×",
        "order": 9,
    },
    {
        "key": "training",
        "label": "研修",
        "class": "shift-training",
        "default_symbol": "研",
        "order": 10,
        "setting_flag": "show_training_mark",
    },
]

DEFAULT_SHIFT_SYMBOLS: dict[str, str] = {
    item["key"]: item["default_symbol"] for item in SHIFT_TYPE_CATALOG
}

# 旧「公休」種別（統合前）のデフォルト記号
LEGACY_PUBLIC_SYMBOL = "-"

CATALOG_BY_KEY: dict[str, dict] = {item["key"]: item for item in SHIFT_TYPE_CATALOG}

SEMI_SHIFT_TYPES: list[dict] = [
    {
        "key": "semi_early",
        "label": "準早",
        "class": "shift-semi-early",
        "default_symbol": "半早",
        "base_key": "early",
        "order": 15,
    },
    {
        "key": "semi_day",
        "label": "準日",
        "class": "shift-semi-day",
        "default_symbol": "半日",
        "base_key": "day",
        "order": 25,
    },
    {
        "key": "semi_late",
        "label": "準遅",
        "class": "shift-semi-late",
        "default_symbol": "半遅",
        "base_key": "late",
        "order": 35,
    },
    {
        "key": "semi_night",
        "label": "準夜",
        "class": "shift-semi-night",
        "default_symbol": "準夜",
        "base_key": "night",
        "order": 55,
    },
]

SEMI_BY_KEY: dict[str, dict] = {item["key"]: item for item in SEMI_SHIFT_TYPES}

WORK_TYPE_SETTING_GROUPS: list[dict] = [
    {"id": "early", "label": "早朝・早番", "keys": ["early", "semi_early"]},
    {"id": "day", "label": "日勤", "keys": ["day", "semi_day"]},
    {"id": "late", "label": "遅出", "keys": ["late", "semi_late"]},
    {"id": "night", "label": "夜勤・当直", "keys": ["night", "semi_night", "special"]},
    {"id": "morning_off", "label": "明け", "keys": ["morning_off"]},
    {"id": "leave", "label": "休暇・その他", "keys": ["paid_leave", "half_leave", "off", "training"]},
]


def default_visible_work_types(settings: dict | None = None) -> dict[str, bool]:
    from data.staffing_basis import get_staffing_basis_options

    result = {item["key"]: True for item in SHIFT_TYPE_CATALOG}
    for item in get_staffing_basis_options(settings):
        result.setdefault(item["key"], True)
    return result


def normalize_visible_work_types(settings: dict | None = None) -> dict[str, bool]:
    cfg = settings or {}
    merged = default_visible_work_types(cfg)
    stored = cfg.get("visible_work_types")
    if isinstance(stored, dict):
        for key, value in stored.items():
            cleaned = str(key).strip()
            if cleaned in merged:
                merged[cleaned] = bool(value)
    if not isinstance(stored, dict) or "half_leave" not in stored:
        merged["half_leave"] = bool(cfg.get("allow_paid_leave_half", merged["half_leave"]))
    if not isinstance(stored, dict) or "training" not in stored:
        merged["training"] = bool(cfg.get("show_training_mark", merged["training"]))
    # 夜勤明け固定ルールのため、明けは常に表示
    merged["morning_off"] = True
    return merged


def is_work_type_visible(key: str, settings: dict | None = None) -> bool:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    visibility = normalize_visible_work_types(cfg)
    return bool(visibility.get(key, True))


def get_work_type_visibility_options(settings: dict | None = None) -> list[dict]:
    from data.staffing_basis import get_staffing_basis_options

    cfg = settings or {}
    visibility = normalize_visible_work_types(cfg)
    labels: dict[str, str] = {}
    order: dict[str, int] = {}
    for item in SHIFT_TYPE_CATALOG:
        labels[item["key"]] = item["label"]
        order[item["key"]] = item["order"]
    for index, item in enumerate(get_staffing_basis_options(cfg)):
        labels.setdefault(item["key"], item["label"])
        order.setdefault(item["key"], 100 + index)
    return [
        {
            "key": key,
            "label": labels[key],
            "visible": visibility.get(key, True),
        }
        for key in sorted(labels, key=lambda item: (order.get(item, 999), item))
    ]


def get_work_type_setting_groups(settings: dict | None = None) -> list[dict]:
    from data.staffing_basis import format_work_hours, get_staffing_basis_options
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    visibility = normalize_visible_work_types(cfg)
    symbols = get_shift_symbols(cfg)
    basis_options = get_staffing_basis_options(cfg)
    labels: dict[str, str] = {}
    hours: dict[str, str] = {}
    for item in SHIFT_TYPE_CATALOG:
        labels[item["key"]] = item["label"]
    for item in basis_options:
        key = item["key"]
        labels.setdefault(key, item["label"])
        hours[key] = format_work_hours(item.get("start_time", ""), item.get("end_time", ""))

    def _row_for_key(key: str) -> dict | None:
        if key not in labels:
            return None
        catalog = CATALOG_BY_KEY.get(key)
        semi = SEMI_BY_KEY.get(key)
        if catalog and not _type_allowed_for_facility(catalog, cfg):
            return None
        has_symbol = catalog is not None and _type_allowed_for_facility(catalog, cfg)
        if semi is not None:
            has_symbol = True
        symbol = symbols.get(key, "") if has_symbol else ""
        css_class = ""
        if semi:
            css_class = semi.get("class", "")
        elif catalog:
            css_class = catalog.get("class", "")
        visibility_fixed = key == "morning_off"
        return {
            "key": key,
            "label": labels[key],
            "visible": True if visibility_fixed else visibility.get(key, True),
            "visibility_fixed": visibility_fixed,
            "symbol": symbol,
            "has_symbol": has_symbol,
            "staffing_only": catalog is None and key not in SEMI_BY_KEY,
            "hours": hours.get(key, ""),
            "css_class": css_class,
        }

    groups: list[dict] = []
    covered_keys: set[str] = set()
    for group in WORK_TYPE_SETTING_GROUPS:
        items: list[dict] = []
        for key in group["keys"]:
            row = _row_for_key(key)
            if row is None:
                continue
            items.append(row)
            covered_keys.add(key)
        if items:
            groups.append({"id": group["id"], "label": group["label"], "rows": items})

    extra_items: list[dict] = []
    for item in basis_options:
        key = str(item.get("key", "")).strip()
        if not key or key in covered_keys:
            continue
        row = _row_for_key(key)
        if row is None:
            continue
        extra_items.append(row)
        covered_keys.add(key)
    if extra_items:
        groups.append({"id": "registered", "label": "登録済み勤務区分", "rows": extra_items})

    return groups


def _legacy_public_symbols(settings: dict) -> set[str]:
    """統合前の公休記号（設定で上書きされていた場合も含む）。"""
    symbols = {LEGACY_PUBLIC_SYMBOL}
    stored = settings.get("shift_symbols") or {}
    if isinstance(stored, dict):
        legacy = stored.get("public")
        if isinstance(legacy, str) and legacy.strip():
            symbols.add(legacy.strip())
    return symbols


def _resolve_symbol_key(symbol: str, settings: dict) -> str | None:
    key = _symbol_key_map(settings).get(symbol)
    if key == "public":
        return "off"
    if key is None and symbol in _legacy_public_symbols(settings):
        return "off"
    return key


def _type_allowed_for_facility(type_def: dict, settings: dict) -> bool:
    facility = settings.get("facility_type", "all")
    allowed = type_def.get("facility_types")
    if allowed and facility not in allowed:
        return False
    return True


def _type_enabled(type_def: dict, settings: dict) -> bool:
    if not _type_allowed_for_facility(type_def, settings):
        return False
    if not is_work_type_visible(type_def["key"], settings):
        return False
    return True


def get_shift_symbol_types(settings: dict | None = None) -> list[dict]:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    return sorted(
        [item for item in SHIFT_TYPE_CATALOG if _type_allowed_for_facility(item, cfg)],
        key=lambda item: item["order"],
    )


def get_configurable_shift_types(settings: dict | None = None) -> list[dict]:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    return sorted(
        [item for item in SHIFT_TYPE_CATALOG if _type_enabled(item, cfg)],
        key=lambda item: item["order"],
    )


def get_shift_symbols(settings: dict | None = None) -> dict[str, str]:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    symbols = dict(DEFAULT_SHIFT_SYMBOLS)
    for item in SEMI_SHIFT_TYPES:
        symbols.setdefault(item["key"], item["default_symbol"])
    overrides = cfg.get("shift_symbols") or {}
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if key == "public":
                continue
            if (key in CATALOG_BY_KEY or key in SEMI_BY_KEY) and isinstance(value, str) and value.strip():
                symbols[key] = value.strip()
    return symbols


def _symbol_key_map(settings: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key, default_symbol in DEFAULT_SHIFT_SYMBOLS.items():
        mapping[default_symbol] = key
    for key, symbol in get_shift_symbols(settings).items():
        mapping[symbol] = key
    stored = settings.get("shift_symbols") or {}
    if isinstance(stored, dict):
        for key, symbol in stored.items():
            if key == "public":
                continue
            if (key in CATALOG_BY_KEY or key in SEMI_BY_KEY) and isinstance(symbol, str) and symbol.strip():
                mapping[symbol.strip()] = key
    for legacy in _legacy_public_symbols(settings):
        mapping[legacy] = "off"
    return mapping


def symbol_to_key(symbol: str, settings: dict | None = None) -> str | None:
    from db.settings_repository import get_settings

    if not symbol:
        return None
    return _resolve_symbol_key(symbol, settings or get_settings())


def normalize_symbol(symbol: str, settings: dict | None = None) -> str:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    key = symbol_to_key(symbol, cfg)
    if key:
        return get_shift_symbols(cfg)[key]
    return symbol


def get_class_for_symbol(symbol: str, settings: dict | None = None) -> str:
    key = symbol_to_key(symbol, settings)
    if key and key in CATALOG_BY_KEY:
        return CATALOG_BY_KEY[key]["class"]
    if key and key in SEMI_BY_KEY:
        return SEMI_BY_KEY[key]["class"]
    return "shift-off"


def _semi_legend_items(cfg: dict, symbols: dict[str, str]) -> list[dict]:
    items: list[dict] = []
    for semi in SEMI_SHIFT_TYPES:
        if not is_work_type_visible(semi["key"], cfg):
            continue
        items.append(
            {
                "key": semi["key"],
                "symbol": symbols[semi["key"]],
                "label": semi["label"],
                "class": semi["class"],
            }
        )
    return items


def build_symbol_class_map(settings: dict | None = None) -> dict[str, str]:
    """表示オン/オフに関わらず、セル着色用の記号→CSSクラス対応。"""
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    symbols = get_shift_symbols(cfg)
    mapping: dict[str, str] = {}
    for type_def in SHIFT_TYPE_CATALOG:
        symbol = symbols.get(type_def["key"], "")
        if symbol:
            mapping[symbol] = type_def["class"]
    for semi in SEMI_SHIFT_TYPES:
        symbol = symbols.get(semi["key"], "")
        if symbol:
            mapping[symbol] = semi["class"]
    return mapping


def build_shift_legend(settings: dict | None = None) -> list[dict]:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    symbols = get_shift_symbols(cfg)
    legend = []
    for type_def in get_configurable_shift_types(cfg):
        legend.append(
            {
                "key": type_def["key"],
                "symbol": symbols[type_def["key"]],
                "label": type_def["label"],
                "class": type_def["class"],
            }
        )
    legend.extend(_semi_legend_items(cfg, symbols))
    return legend


def build_daily_summary_rows(settings: dict | None = None) -> list[dict]:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    symbols = get_shift_symbols(cfg)
    rows = []
    for type_def in get_configurable_shift_types(cfg):
        summary_label = type_def.get("summary_label")
        if not summary_label:
            continue
        rows.append(
            {
                "key": type_def["key"],
                "label": summary_label,
                "symbol": symbols[type_def["key"]],
            }
        )
    return rows


def get_valid_symbols(settings: dict | None = None) -> set[str]:
    return {item["symbol"] for item in build_shift_legend(settings)}


def validate_shift_symbols(settings: dict) -> None:
    symbols = get_shift_symbols(settings)
    enabled = get_shift_symbol_types(settings)
    values: list[str] = []
    for type_def in enabled:
        value = symbols.get(type_def["key"], "")
        if not value:
            raise ValueError(f"「{type_def['label']}」の表示記号を入力してください。")
        if len(value) > 10:
            raise ValueError(f"「{type_def['label']}」の表示記号は10文字以内にしてください。")
        values.append(value)
    for semi in SEMI_SHIFT_TYPES:
        if not is_work_type_visible(semi["key"], settings):
            continue
        value = symbols.get(semi["key"], "")
        if not value:
            raise ValueError(f"「{semi['label']}」の表示記号を入力してください。")
        if len(value) > 10:
            raise ValueError(f"「{semi['label']}」の表示記号は10文字以内にしてください。")
        values.append(value)
    if len(values) != len(set(values)):
        raise ValueError("表示記号が重複しています。種別ごとに異なる記号を設定してください。")

from data.settings_defaults import FACILITY_LABELS
from db.settings_repository import get_settings


def get_facility_context() -> dict:
    settings = get_settings()
    facility_type = settings.get("facility_type", "all")
    return {
        "facility_name": settings.get("facility_name", "○○病院"),
        "facility_type": facility_type,
        "facility_label": FACILITY_LABELS.get(facility_type, FACILITY_LABELS["all"]),
        "admin_name": settings.get("admin_name", "管理者"),
        "app_settings": settings,
    }

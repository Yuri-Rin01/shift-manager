from config import FACILITY_TYPE
from data.shift_symbols import build_daily_summary_rows, build_shift_legend
from db.settings_repository import get_settings


def _active_facility_type() -> str:
    return get_settings().get("facility_type", FACILITY_TYPE)


FLOOR_DEPARTMENTS = [
    {"id": "1f", "label": "1F"},
    {"id": "2f", "label": "2F"},
    {"id": "3f", "label": "3F"},
    {"id": "4f", "label": "4F"},
]

# 勤務割合は data/staffing_basis.py で設定連動

# 旧部署名 → フロアへの移行用
LEGACY_DEPARTMENT_TO_FLOOR = {
    "看護": "1F",
    "リハビリ": "3F",
    "内科": "1F",
    "外科": "2F",
    "整形外科": "2F",
    "小児科": "3F",
    "産婦人科": "3F",
    "救急": "1F",
    "ICU": "4F",
    "NICU": "4F",
    "外来": "1F",
    "手術室": "2F",
    "薬局": "1F",
    "検査科": "2F",
    "放射線科": "2F",
    "看護部": "1F",
    "リハビリテーション科": "3F",
}

CARE_JOB_TYPES = [
    {"id": "care", "label": "介護士"},
    {"id": "nurse", "label": "看護師"},
    {"id": "pt", "label": "理学療法士"},
    {"id": "ot", "label": "作業療法士"},
    {"id": "st", "label": "言語聴覚士"},
    {"id": "care_manager", "label": "ケアマネ"},
    {"id": "counselor", "label": "相談員"},
    {"id": "office_staff", "label": "事務員"},
    {"id": "trainee", "label": "研修中"},
    {"id": "intern", "label": "留学生"},
    {"id": "part", "label": "パート"},
]

HOSPITAL_JOB_TYPES = [
    {"id": "doctor", "label": "医師"},
    {"id": "resident", "label": "研修医"},
    {"id": "nurse", "label": "看護師"},
    {"id": "lpn", "label": "准看護師"},
    {"id": "pharmacist", "label": "薬剤師"},
    {"id": "pt", "label": "理学療法士"},
    {"id": "ot", "label": "作業療法士"},
    {"id": "st", "label": "言語聴覚士"},
    {"id": "radiology_tech", "label": "放射線技師"},
    {"id": "lab_tech", "label": "臨床検査技師"},
    {"id": "msw", "label": "医療ソーシャルワーカー"},
    {"id": "care_manager", "label": "ケアマネ"},
    {"id": "counselor", "label": "相談員"},
    {"id": "office_staff", "label": "事務員"},
    {"id": "clerk", "label": "事務"},
    {"id": "trainee", "label": "研修中"},
    {"id": "intern", "label": "留学生"},
    {"id": "part", "label": "パート"},
]

CARE_POSITIONS = [
    {"id": "director", "label": "施設長"},
    {"id": "manager", "label": "管理者"},
    {"id": "chief", "label": "主任"},
    {"id": "leader", "label": "リーダー"},
    {"id": "sub_leader", "label": "サブリーダー"},
    {"id": "staff", "label": "一般"},
]

HOSPITAL_POSITIONS = [
    {"id": "director", "label": "院長"},
    {"id": "vice_director", "label": "副院長"},
    {"id": "chief", "label": "部長"},
    {"id": "head_nurse", "label": "師長"},
    {"id": "manager", "label": "管理者"},
    {"id": "chief_staff", "label": "主任"},
    {"id": "leader", "label": "リーダー"},
    {"id": "sub_leader", "label": "サブリーダー"},
    {"id": "staff", "label": "一般"},
]


def _merge_by_label(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for item in items:
        if item["label"] in seen:
            continue
        seen.add(item["label"])
        merged.append(item)
    return merged


def get_departments() -> list[dict]:
    return list(FLOOR_DEPARTMENTS)


def get_staffing_basis_options() -> list[dict]:
    from data.staffing_basis import get_staffing_basis_options as _get_options

    return _get_options()


def get_staffing_basis_keys() -> set[str]:
    from data.staffing_basis import get_staffing_basis_keys as _get_keys

    return _get_keys()


def validate_staffing_basis(staffing_basis: dict[str, int]) -> None:
    from data.staffing_basis import validate_staffing_basis_ratios as _validate

    _validate(staffing_basis)


def get_job_types() -> list[dict]:
    facility_type = _active_facility_type()
    if facility_type == "care":
        return CARE_JOB_TYPES
    if facility_type == "hospital":
        return HOSPITAL_JOB_TYPES
    return _merge_by_label(CARE_JOB_TYPES + HOSPITAL_JOB_TYPES)


def get_positions() -> list[dict]:
    facility_type = _active_facility_type()
    if facility_type == "care":
        return CARE_POSITIONS
    if facility_type == "hospital":
        return HOSPITAL_POSITIONS
    return _merge_by_label(CARE_POSITIONS + HOSPITAL_POSITIONS)


def get_facility_type() -> str:
    return _active_facility_type()


def get_shift_legend() -> list[dict]:
    return build_shift_legend()


def get_active_shift_legend(settings: dict | None = None) -> list[dict]:
    return build_shift_legend(settings)


def get_daily_summary_rows(settings: dict | None = None) -> list[dict]:
    return build_daily_summary_rows(settings)


def get_status_summary(
    settings: dict | None = None,
    year: int | None = None,
    month: int | None = None,
) -> list[dict]:
    from datetime import date

    from data.dashboard import build_dashboard

    today = date.today()
    resolved_year = year or today.year
    resolved_month = month or today.month
    return build_dashboard(resolved_year, resolved_month)["checks"]


def get_calendar_title(mode: str | None = None) -> str:
    from db.settings_repository import get_settings

    titles = {
        "position": "シフトカレンダー（役職順）",
        "dept": "シフトカレンダー（フロア順）",
        "job": "シフトカレンダー（職種順）",
        "name": "シフトカレンダー（名前順）",
    }
    resolved = mode or get_settings().get("calendar_sort_mode", "dept")
    return titles.get(resolved, titles["dept"])


def sort_staff_by_job(staff_list: list[dict]) -> list[dict]:
    job_order = {item["label"]: index for index, item in enumerate(get_job_types())}

    def sort_key(person: dict) -> tuple[int, str]:
        job = person.get("job") or person.get("job_type", "")
        return (job_order.get(job, 999), person.get("name", ""))

    return sorted(staff_list, key=sort_key)


def sort_staff_by_name(staff_list: list[dict]) -> list[dict]:
    return sorted(staff_list, key=lambda person: person.get("name", ""))


def sort_staff_by_position(staff_list: list[dict]) -> list[dict]:
    position_order = {item["label"]: index for index, item in enumerate(get_positions())}

    def sort_key(person: dict) -> tuple[int, str]:
        position = (person.get("position") or "").strip()
        rank = 999 if not position else position_order.get(position, 998)
        return (rank, person.get("name", ""))

    return sorted(staff_list, key=sort_key)


def sort_staff_for_calendar(staff_list: list[dict], mode: str | None = None) -> list[dict]:
    from db.settings_repository import get_settings

    resolved = mode or get_settings().get("calendar_sort_mode", "dept")
    if resolved == "position":
        return sort_staff_by_position(staff_list)
    if resolved == "job":
        return sort_staff_by_job(staff_list)
    if resolved == "name":
        return sort_staff_by_name(staff_list)
    return sort_staff_by_department(staff_list)


def sort_staff_by_department(staff_list: list[dict]) -> list[dict]:
    dept_order = {d["label"]: i for i, d in enumerate(get_departments())}

    def sort_key(person: dict) -> tuple[int, str]:
        dept = person.get("dept") or person.get("department", "")
        if not dept:
            depts = person.get("departments") or []
            dept = depts[0] if depts else ""
        return (dept_order.get(dept, 999), person.get("name", ""))

    return sorted(staff_list, key=sort_key)


def _allowed_job_labels() -> set[str]:
    return {item["label"] for item in get_job_types()}


def _allowed_department_labels() -> set[str]:
    return {item["label"] for item in get_departments()}


def filter_staff_for_facility(staff_list: list[dict]) -> list[dict]:
    if _active_facility_type() == "all":
        return staff_list

    allowed_jobs = _allowed_job_labels()
    allowed_depts = _allowed_department_labels()
    filtered: list[dict] = []
    for row in staff_list:
        job = row.get("job_type") or row.get("job", "")
        floors = row.get("departments") or [row.get("department") or row.get("dept", "")]
        floors = [floor for floor in floors if floor]
        if job in allowed_jobs and any(floor in allowed_depts for floor in floors):
            filtered.append(row)
    return filtered


def validate_staff_for_facility(job_type: str, departments: list[str]) -> None:
    if _active_facility_type() == "all":
        return

    from data.settings_defaults import FACILITY_LABELS

    facility_label = FACILITY_LABELS.get(_active_facility_type(), "現在の施設")
    allowed_jobs = _allowed_job_labels()
    allowed_depts = _allowed_department_labels()

    if job_type not in allowed_jobs:
        raise ValueError(
            f"職種「{job_type}」は{facility_label}向けの設定では使用できません。"
            f"各種設定の施設種別を確認してください。"
        )
    for department in departments:
        if department not in allowed_depts:
            raise ValueError(
                f"フロア「{department}」は{facility_label}向けの設定では使用できません。"
                f"各種設定の施設種別を確認してください。"
            )

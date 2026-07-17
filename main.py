from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app_paths import resource_root
from data.facility import get_facility_context
from data.masters import get_departments, get_job_types, get_positions
from data.staffing_basis import (
    filter_ratio_staffing_basis_options,
    get_default_staffing_basis_ratios,
    get_staffing_basis_hours_map,
)
from data.work_type_templates import get_work_type_templates
from data.navigation import get_sidebar
from data.dashboard import build_dashboard
from data.sample import build_calendar
from data.settings_defaults import (
    CALENDAR_SORT_OPTIONS,
    FACILITY_TYPE_OPTIONS,
    FAIRNESS_OPTIONS,
    PRINT_PAPER_OPTIONS,
    PRINT_SCALE_OPTIONS,
    STAFF_SORT_OPTIONS,
    TABLE_ZOOM_OPTIONS,
    WEEK_START_OPTIONS,
)
from data.calendar_period import (
    calendar_start_day_options,
    format_period_label,
    period_bounds,
    resolve_configured_period_off_days,
)
from data.account_plan import get_account_plan_context
from data.settings_panels import SETTINGS_PANELS, resolve_settings_panel
from data.shift_symbols import get_work_type_setting_groups
from data.routes import ROUTES, STUB_PAGES
from db.database import init_db
from db.settings_repository import get_settings
from routers.leave_requests import router as leave_requests_router
from routers.settings import router as settings_router
from routers.shifts import router as shifts_router
from routers.staff import router as staff_router

BASE_DIR = resource_root()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="シフト作成システム",
    description="病院・介護施設向けシフト管理",
    lifespan=lifespan,
)
app.include_router(staff_router)
app.include_router(settings_router)
app.include_router(shifts_router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _base_context(**extra) -> dict:
    return {**get_facility_context(), **extra}


def _page_context(active_key: str, **extra) -> dict:
    context = {
        "sidebar_menu": get_sidebar(active_key),
        "departments": get_departments(),
        "job_types": get_job_types(),
        "positions": get_positions(),
    }
    context.update(extra)
    return _base_context(**context)


def _staff_editor_context() -> dict:
    """職員編集モーダル（ホーム・職員管理で共有）用のテンプレート変数。"""
    today = date.today()
    app_settings = get_settings()
    calendar_start_day = app_settings.get("calendar_start_day", 1)
    period_start, period_end = period_bounds(today.year, today.month, calendar_start_day)
    period_days, default_off_days, working_days = resolve_configured_period_off_days(
        app_settings, today.year, today.month, calendar_start_day
    )
    return {
        "staffing_basis_options": filter_ratio_staffing_basis_options(settings=app_settings),
        "default_staffing_basis": get_default_staffing_basis_ratios(),
        "staffing_period_days": period_days,
        "staffing_period_off_days": default_off_days,
        "staffing_period_working_days": working_days,
        "staffing_period_label": format_period_label(
            period_start, period_end, year=today.year, month=today.month, start_day=calendar_start_day
        ),
        "default_staff_sort": app_settings.get("calendar_sort_mode", "dept"),
        "night_shift_counts_as_two_days": app_settings.get("night_shift_counts_as_two_days", True),
        "staffing_basis_hours": get_staffing_basis_hours_map(app_settings),
    }


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    display: str | None = None,
):
    today = date.today()
    resolved_year = year or today.year
    resolved_month = month or today.month
    if resolved_month < 1 or resolved_month > 12:
        resolved_month = today.month
    context = _base_context(
        **build_calendar(resolved_year, resolved_month, display_group=display),
        **_staff_editor_context(),
        positions=get_positions(),
    )
    return templates.TemplateResponse(request, "index.html", context)


def _adjacent_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    year: int | None = None,
    month: int | None = None,
):
    today = date.today()
    resolved_year = year or today.year
    resolved_month = month or today.month
    if resolved_month < 1 or resolved_month > 12:
        resolved_year = today.year
        resolved_month = today.month
    prev_year, prev_month = _adjacent_month(resolved_year, resolved_month, -1)
    next_year, next_month = _adjacent_month(resolved_year, resolved_month, 1)
    context = _page_context(
        "dashboard",
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        **build_dashboard(resolved_year, resolved_month),
    )
    return templates.TemplateResponse(request, "dashboard/index.html", context)


@app.get("/staff", response_class=HTMLResponse)
async def staff_page(request: Request):
    context = _page_context(
        "staff",
        **_staff_editor_context(),
        staff_sort_options=STAFF_SORT_OPTIONS,
    )
    return templates.TemplateResponse(request, "staff/index.html", context)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, panel: str | None = None):
    current_panel = resolve_settings_panel(panel)
    context = _page_context(
        current_panel["key"],
        facility_type_options=FACILITY_TYPE_OPTIONS,
        calendar_sort_options=CALENDAR_SORT_OPTIONS,
        week_start_options=WEEK_START_OPTIONS,
        calendar_start_day_options=calendar_start_day_options(),
        fairness_options=FAIRNESS_OPTIONS,
        print_paper_options=PRINT_PAPER_OPTIONS,
        print_scale_options=PRINT_SCALE_OPTIONS,
        table_zoom_options=TABLE_ZOOM_OPTIONS,
        work_type_setting_groups=get_work_type_setting_groups(),
        work_type_templates=get_work_type_templates(),
        settings_panels=SETTINGS_PANELS,
        settings_panel=current_panel["id"],
        settings_panel_meta=current_panel,
        **get_account_plan_context(),
    )
    return templates.TemplateResponse(request, "settings/index.html", context)


def _register_stub_pages() -> None:
    skip_keys = frozenset({"leave-request"})
    for key, (title, subtitle) in STUB_PAGES.items():
        if key in skip_keys:
            continue
        path = ROUTES[key]

        async def page(
            request: Request,
            active_key: str = key,
            page_title: str = title,
            page_subtitle: str = subtitle,
        ):
            context = _page_context(
                active_key,
                page_title=page_title,
                page_subtitle=page_subtitle,
            )
            return templates.TemplateResponse(request, "pages/stub.html", context)

        app.add_api_route(
            path,
            page,
            methods=["GET"],
            response_class=HTMLResponse,
            name=f"stub_{key}",
        )


_register_stub_pages()
app.include_router(leave_requests_router)

"""追加シート設定の保存と画面。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from data.settings_defaults import DEFAULT_SETTINGS
from data.sheet_views import normalize_custom_sheet_views, normalize_sheet_tab_order
from db.database import init_db
from db.settings_repository import get_settings, save_settings
from schemas.settings import AppSettings


def test_normalize_drops_incomplete_and_caps_count():
    raw = [{"label": "", "job_types": ["看護師"]}]
    raw.append({"label": "看護", "job_types": ["看護師", "看護師", " 准看護師 "]})
    raw.extend(
        {"id": f"custom-{index}", "label": f"シート{index}", "job_types": ["介護士"], "color": "not-a-color"}
        for index in range(2, 12)
    )
    result = normalize_custom_sheet_views(raw)
    assert result[0]["label"] == "看護"
    assert result[0]["job_types"] == ["看護師", "准看護師"]
    assert len(result) == 8
    assert result[1]["color"] == "#64748B"
    assert normalize_custom_sheet_views("bad") == []


def test_custom_sheet_round_trip():
    with TemporaryDirectory() as directory:
        db_path = Path(directory) / "sheets.db"
        with patch("db.database.DB_PATH", db_path):
            init_db()
            settings = get_settings()
            settings["custom_sheet_views"] = [
                {"id": "custom-3", "label": "看護", "job_types": ["看護師"], "color": "#0f766e"}
            ]
            saved = save_settings(settings)
            loaded = get_settings()
            assert saved["custom_sheet_views"] == loaded["custom_sheet_views"]
            assert loaded["custom_sheet_views"][0]["id"] == "custom-3"
            assert loaded["custom_sheet_views"][0]["color"] == "#0F766E"


def test_schema_keeps_builtin_defaults_without_custom_sheets():
    payload = AppSettings(**DEFAULT_SETTINGS).model_dump()
    assert payload["custom_sheet_views"] == []
    assert payload["sheet_tab_order"] == ["foreign-students"]


def test_sheet_tab_order_keeps_all_pinned_and_appends_missing():
    custom_ids = ["custom-2", "custom-1"]
    assert normalize_sheet_tab_order(["all", "custom-1", "missing", "foreign-students"], custom_ids) == [
        "custom-1",
        "foreign-students",
        "custom-2",
    ]
    assert normalize_sheet_tab_order(None, custom_ids) == ["foreign-students", "custom-2", "custom-1"]


def test_sheet_tab_order_round_trip():
    payload = AppSettings(
        **{
            **DEFAULT_SETTINGS,
            "custom_sheet_views": [
                {"id": "custom-1", "label": "看護", "job_types": ["看護師"], "color": "#0f766e"}
            ],
            "sheet_tab_order": ["custom-1", "foreign-students"],
        }
    ).model_dump()
    assert payload["sheet_tab_order"] == ["custom-1", "foreign-students"]


def test_display_settings_page_has_custom_sheet_editor():
    import importlib

    import main as main_module
    from fastapi.testclient import TestClient

    with TemporaryDirectory() as directory:
        db_path = Path(directory) / "sheets-ui.db"
        with patch("db.database.DB_PATH", db_path):
            init_db()
            importlib.reload(main_module)
            client = TestClient(main_module.app)
            response = client.get("/settings?panel=display")
            assert response.status_code == 200
            html = response.text
            assert "追加シート" in html
            assert 'id="custom-sheet-list"' in html
            assert 'id="btn-add-custom-sheet"' in html
            assert "JOB_TYPES" in html
            home = client.get("/")
            assert home.status_code == 200
            home_html = home.text
            assert 'id="btn-add-sheet-tab"' in home_html
            assert home_html.index('data-sheet-view="foreign-students"') < home_html.index("btn-add-sheet-tab")
            assert 'id="sheet-add-popover"' in home_html
            assert home_html.index('id="student-labor-panel"') < home_html.index('id="sheet-flip-viewport"')

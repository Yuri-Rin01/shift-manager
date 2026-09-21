"""フリック方向の割り当て設定。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from data.flick_directions import normalize_cell_flick_directions
from data.settings_defaults import DEFAULT_SETTINGS
from db.database import init_db
from db.settings_repository import get_settings, save_settings
from schemas.settings import AppSettings


def test_normalize_empty_means_auto():
    assert normalize_cell_flick_directions(None) == []
    assert normalize_cell_flick_directions([]) == []
    assert normalize_cell_flick_directions(["", "", "", "", "", "", "", ""]) == []
    assert normalize_cell_flick_directions("not-a-list") == []


def test_normalize_pads_and_trims_eight_directions():
    result = normalize_cell_flick_directions([" ● ", "○"])
    assert result == ["●", "○", "", "", "", "", "", ""]
    assert len(result) == 8


def test_schema_accepts_custom_flick_map():
    payload = dict(DEFAULT_SETTINGS)
    payload["cell_flick_directions"] = ["夜", "明", "×", "", "○", "", "", "有休"]
    saved = AppSettings(**payload).model_dump()
    assert saved["cell_flick_directions"] == ["夜", "明", "×", "", "○", "", "", "有休"]


def test_flick_directions_round_trip():
    with TemporaryDirectory() as directory:
        db_path = Path(directory) / "flick.db"
        with patch("db.database.DB_PATH", db_path):
            init_db()
            settings = get_settings()
            settings["cell_flick_directions"] = ["●", "○", "◎", "夜", "明", "×", "有休", ""]
            saved = save_settings(settings)
            loaded = get_settings()
            assert saved["cell_flick_directions"] == ["●", "○", "◎", "夜", "明", "×", "有休", ""]
            assert loaded["cell_flick_directions"] == saved["cell_flick_directions"]


def test_display_settings_page_has_flick_details_next_to_time():
    import importlib

    import main as main_module
    from fastapi.testclient import TestClient

    with TemporaryDirectory() as directory:
        db_path = Path(directory) / "flick-ui.db"
        with patch("db.database.DB_PATH", db_path):
            init_db()
            importlib.reload(main_module)
            client = TestClient(main_module.app)
            response = client.get("/settings?panel=display")
            assert response.status_code == 200
            html = response.text
            assert "長押し時間" in html
            assert "詳細設定" in html
            assert "flick-details-summary" in html
            assert "flick-assign-grid" in html
            assert html.count("flick-assign-select") == 8
            assert html.index("cell_long_press_ms") < html.index("flick-details-summary")
            assert html.index("flick-details-summary") < html.index("flick-assign-grid")

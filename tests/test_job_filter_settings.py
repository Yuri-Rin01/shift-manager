"""ホームの職種絞り込み候補設定のテスト。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from data.masters import get_job_filter_types, get_job_types
from db.database import init_db
from db.settings_repository import get_settings, save_settings


def test_job_filter_visibility_round_trip():
    with TemporaryDirectory() as directory:
        db_path = Path(directory) / "job-filter.db"
        with patch("db.database.DB_PATH", db_path):
            init_db()
            settings = get_settings()
            all_jobs = get_job_types()
            assert len(get_job_filter_types(settings)) == len(all_jobs)

            settings["job_filter_visibility"] = {
                item["label"]: item["label"] == "看護師"
                for item in all_jobs
            }
            saved = save_settings(settings)

            assert saved["job_filter_visibility"]["看護師"] is True
            assert [item["label"] for item in get_job_filter_types(saved)] == ["看護師"]

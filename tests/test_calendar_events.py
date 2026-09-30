from data.calendar_events import normalize_calendar_events
from schemas.settings import AppSettings


def test_normalize_keeps_dated_labels_and_drops_blanks():
    events = normalize_calendar_events(
        [
            {"date": "2026-10-09", "label": "  フロア会議  "},
            {"date": "2026-10-09", "label": "重複"},
            {"date": "bad", "label": "無効"},
            {"label": "日付なし"},
        ]
    )
    assert events == [{"date": "2026-10-09", "label": "フロア会議"}]


def test_settings_round_trip_events():
    payload = AppSettings(calendar_events=[{"date": "2026-10-16", "label": "1階会議"}]).model_dump()
    assert payload["highlight_event_days"] is True
    assert payload["calendar_events"] == [{"date": "2026-10-16", "label": "1階会議"}]

from datetime import datetime, timezone

from app.core.time import local_day_bounds_utc, local_date


def test_sao_paulo_local_day_bounds_cover_utc_day_boundary() -> None:
    instant = datetime(2026, 1, 15, 3, 30, tzinfo=timezone.utc)

    start, end = local_day_bounds_utc(instant)

    assert start == datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 1, 16, 3, 0, tzinfo=timezone.utc)
    assert local_date(instant).isoformat() == "2026-01-15"


def test_sao_paulo_local_day_bounds_include_last_instant_before_midnight() -> None:
    instant = datetime(2026, 1, 15, 2, 59, 59, tzinfo=timezone.utc)

    start, end = local_day_bounds_utc(instant)

    assert start == datetime(2026, 1, 14, 3, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)

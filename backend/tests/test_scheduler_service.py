import pytest

from app.workers import scheduler_service


def test_create_scheduler_registers_one_minute_worker() -> None:
    scheduler = scheduler_service.create_scheduler()
    jobs = scheduler.get_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "flashpost-loop-and-token-worker"
    assert jobs[0].trigger.interval.total_seconds() == 60
    assert jobs[0].max_instances == 1
    assert jobs[0].coalesce is True


@pytest.mark.anyio
async def test_scheduler_tick_uses_existing_database_without_postgres_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        class dialect:
            name = "sqlite"

    calls = 0

    async def fake_tick() -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr(scheduler_service, "get_engine", lambda: FakeEngine())
    monkeypatch.setattr(scheduler_service, "run_loop_scheduler_tick", fake_tick)

    await scheduler_service._run_tick_with_database_lock()

    assert calls == 1


@pytest.mark.anyio
async def test_scheduler_tick_logs_failure_and_remains_available_for_next_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        class dialect:
            name = "sqlite"

    calls = 0

    async def failing_tick() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        return 0

    monkeypatch.setattr(scheduler_service, "get_engine", lambda: FakeEngine())
    monkeypatch.setattr(scheduler_service, "run_loop_scheduler_tick", failing_tick)

    await scheduler_service._run_tick_with_database_lock()
    await scheduler_service._run_tick_with_database_lock()

    assert calls == 2

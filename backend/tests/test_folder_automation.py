import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.instagram.folder_automation import automate_account, matches, normalize_prefixes
from app.models import InstagramLoopAccount, InstagramProfileFolder

from tests.test_loops import _active_account, _csrf, _login


def test_prefix_rules_are_case_insensitive_and_cleaned() -> None:
    assert normalize_prefixes([" @Alice ", "alic", "ALIC", "", "ali."]) == ["alice", "alic", "ali."]
    assert matches("Alice.reels", ["ali"]) and matches("@alii_x", ["alii"])
    assert not matches("malice", ["ali"])
    assert not matches("anything", [])


@pytest.mark.anyio
async def test_new_account_is_filed_by_prefix_and_joins_the_folders_loop(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    existing = _active_account(workspace.id, "base_account")
    db_session.add(existing)
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    headers = {"X-CSRF-Token": token}

    folder = await client.post(
        "/api/instagram/folders",
        headers=headers,
        json={"name": "Alices", "color": "#ff3399", "auto_prefixes": ["Alice", "alic", "ali."]},
    )
    assert folder.status_code == 201, folder.text
    assert folder.json()["auto_prefixes"] == ["alice", "alic", "ali."]
    assert folder.json()["auto_enabled"] is True
    folder_id = folder.json()["id"]

    loop = await client.post(
        "/api/loops",
        headers=headers,
        json={
            "name": "Loop das Alices",
            "interval_min_minutes": 20,
            "interval_max_minutes": 40,
            "account_ids": [str(existing.id)],
            "auto_folder_ids": [folder_id],
        },
    )
    assert loop.status_code == 201, loop.text
    assert loop.json()["auto_folder_ids"] == [folder_id]
    loop_id = uuid.UUID(loop.json()["id"])

    new_account = _active_account(workspace.id, "alice.novinha")
    other = _active_account(workspace.id, "bruna")
    db_session.add_all([new_account, other])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    await automate_account(db_session, new_account, now)
    await automate_account(db_session, other, now)
    await db_session.commit()

    assert new_account.profile_folder_id == uuid.UUID(folder_id)
    assert other.profile_folder_id is None
    members = set(
        (await db_session.scalars(select(InstagramLoopAccount.account_id).where(InstagramLoopAccount.loop_id == loop_id))).all()
    )
    assert new_account.id in members and other.id not in members


@pytest.mark.anyio
async def test_switch_off_stops_auto_filing_and_loop_takes_folder_accounts(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    _user, workspace = owner
    await _login(client, "owner@example.com", "correct horse battery staple")
    token = await _csrf(client)
    headers = {"X-CSRF-Token": token}
    folder = await client.post(
        "/api/instagram/folders",
        headers=headers,
        json={"name": "Mimis", "color": "#00c9d8", "auto_prefixes": ["mimi"], "auto_enabled": False},
    )
    folder_id = folder.json()["id"]
    off = _active_account(workspace.id, "mimi_oficial")
    db_session.add(off)
    await db_session.flush()
    await automate_account(db_session, off, datetime.now(timezone.utc))
    assert off.profile_folder_id is None

    # Turned back on through the update route.
    update = await client.patch(
        f"/api/instagram/folders/{folder_id}",
        headers=headers,
        json={"name": "Mimis", "color": "#00c9d8", "auto_prefixes": ["mimi"], "auto_enabled": True},
    )
    assert update.status_code == 200 and update.json()["auto_enabled"] is True
    on = _active_account(workspace.id, "mimi_dois")
    db_session.add(on)
    await db_session.flush()
    await automate_account(db_session, on, datetime.now(timezone.utc))
    assert str(on.profile_folder_id) == folder_id

    # A loop that watches the folder starts with the folder's accounts, no manual pick.
    await db_session.commit()
    loop = await client.post(
        "/api/loops",
        headers=headers,
        json={
            "name": "Só pasta",
            "interval_min_minutes": 5,
            "interval_max_minutes": 9,
            "account_ids": [],
            "auto_folder_ids": [folder_id],
        },
    )
    assert loop.status_code == 201, loop.text
    assert [item["username"] for item in loop.json()["accounts"]] == ["mimi_dois"]

    empty = await client.post(
        "/api/loops",
        headers=headers,
        json={"name": "x", "interval_min_minutes": 5, "interval_max_minutes": 9, "account_ids": []},
    )
    assert empty.status_code == 422

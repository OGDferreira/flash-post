"""Funnel export/import (file) and conversion stats."""

import json

import pytest
from sqlalchemy import select

from app.models import TgMedia, TgOrder
from tests.test_flashbot_v2 import _media as _upload, _pay
from tests.test_telegram_bots import GROUP_ID, _flow, _login, _send, _setup, _start, _tap, apis  # noqa: F401


@pytest.mark.anyio
async def test_export_then_import_rebuilds_the_funnel_with_media(client, db_session, owner, apis, monkeypatch) -> None:
    headers = await _login(client)
    media_id = await _upload(client, headers, monkeypatch, "boas-vindas.jpg")
    definition = _flow(welcome=[{"type": "photo", "media_ids": [media_id], "text": "Oi {nome}"}])
    flow = (await client.post("/api/bots/flows", headers=headers, json={"name": "Funil A", "definition": definition})).json()

    exported = await client.get(f"/api/bots/flows/{flow['id']}/export")
    assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
    data = exported.json()
    assert data["format"] == "flashpost-funnel" and data["version"] == 1
    assert data["media"][0]["id"] == media_id and data["media"][0]["data"]
    assert data["definition"]["plans"][0]["delivery"]["group_chat_id"] == 0  # private group ids never leave
    assert "token" not in exported.text.lower()

    imported = await client.post("/api/bots/flows/import", headers=headers, content=json.dumps(data))
    assert imported.status_code == 201, imported.text
    new_media = imported.json()["definition"]["welcome"][0]["media_ids"][0]
    assert new_media != media_id
    await db_session.commit()
    copy = await db_session.get(TgMedia, __import__("uuid").UUID(new_media))
    assert copy is not None and copy.file_name == "boas-vindas.jpg"

    bad = await client.post("/api/bots/flows/import", headers=headers, content=json.dumps({"format": "outro"}))
    assert bad.status_code == 422


@pytest.mark.anyio
async def test_conversion_stats_per_funnel(client, db_session, owner, apis) -> None:
    headers = await _login(client)
    bot, flow = await _setup(client, headers)
    await _send(client, db_session, bot["id"], _start())
    await _send(client, db_session, bot["id"], _tap("plan:vip"))
    await db_session.commit()
    await _pay(client, db_session, await db_session.scalar(select(TgOrder)))
    stats = (await client.get("/api/bots/stats?period=30d")).json()
    assert stats["totals"] == {"leads": 1, "sales": 1, "buyers": 1, "revenue": 19.9, "conversion": 100.0, "ticket": 19.9, "pix_generated": 1, "pix_paid": 1, "commission": 0.0}
    assert stats["flows"][flow["id"]]["conversion"] == 100.0 and stats["bots"][bot["id"]]["sales"] == 1
    assert stats["series"][-1]["sales"] == 1


@pytest.mark.anyio
async def test_import_code_is_short_fbf_and_clones_the_funnel(client, db_session, owner, apis) -> None:
    import re

    from app.bots import portable

    headers = await _login(client)
    flow = (await client.post("/api/bots/flows", headers=headers, json={"name": "Funil Curto", "definition": _flow()})).json()

    made = await client.post(f"/api/bots/flows/{flow['id']}/import-code", headers=headers)
    assert made.status_code == 200, made.text
    code = made.json()["code"]
    assert re.fullmatch(r"FBF-[A-Z0-9]{3}-[A-Z0-9]{3}", code), code

    # the short code imports a clone; a wrong short code is rejected cleanly
    imported = await client.post("/api/bots/flows/import-code", headers=headers, json={"code": code})
    assert imported.status_code == 201, imported.text
    assert imported.json()["name"] == "Funil Curto"
    assert imported.json()["id"] != flow["id"]

    bad = await client.post("/api/bots/flows/import-code", headers=headers, json={"code": "FBF-ZZZ-ZZZ"})
    assert bad.status_code == 422

    # typed loosely (lowercase, spaces) still resolves to the same funnel
    assert portable.normalize_code(" fbf abc xyz ") == "ABCXYZ"

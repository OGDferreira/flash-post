from datetime import datetime, timedelta, timezone

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.instagram import automation
from app.models import (
    InstagramAccount,
    InstagramAutomationEvent,
    InstagramCommentAutomation,
)

IG_USER = "17840000000009999"


async def _csrf(client: AsyncClient) -> str:
    return (await client.get("/api/auth/csrf")).json()["csrf_token"]


async def _login(client: AsyncClient) -> dict:
    token = await _csrf(client)
    await client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    return {"X-CSRF-Token": await _csrf(client)}


async def _account(db, workspace_id) -> InstagramAccount:
    account = InstagramAccount(
        workspace_id=workspace_id,
        instagram_user_id=IG_USER,
        username="flashpost_demo",
        encrypted_access_token=encrypt_value("private-access-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(account)
    await db.flush()
    return account


def _comment_payload(comment_id: str, text: str) -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": IG_USER,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": comment_id,
                            "text": text,
                            "from": {"id": "99887766", "username": "buyer"},
                            "media": {"id": "media-1"},
                        },
                    }
                ],
            }
        ],
    }


@pytest.mark.anyio
async def test_comment_keyword_simulated_when_disabled_then_sent_when_live(
    db_session, owner, monkeypatch
):
    _user, workspace = owner
    account = await _account(db_session, workspace.id)
    rule = InstagramCommentAutomation(
        workspace_id=workspace.id,
        instagram_account_id=account.id,
        name="Promo",
        trigger_type="comment",
        keywords=["quero", "eu quero"],
        public_reply_enabled=True,
        public_replies=["Te chamei no direct! 💌"],
        dm_enabled=True,
        dm_text="Aqui está seu link: ...",
    )
    db_session.add(rule)
    await db_session.commit()

    # A comment that does NOT match is ignored.
    await automation.process_webhook(db_session, _comment_payload("c-nomatch", "que foto linda"))
    assert (await db_session.scalar(select(InstagramAutomationEvent).limit(1))) is None

    # Flag off: a matching comment is logged as "simulated", nothing is sent.
    monkeypatch.setattr(automation.get_settings(), "instagram_automation_enabled", False, raising=False)
    await automation.process_webhook(db_session, _comment_payload("c-1", "eu QUERO!!"))
    event = await db_session.scalar(select(InstagramAutomationEvent))
    assert event is not None and event.status == "simulated"
    await db_session.refresh(rule)
    assert rule.fired_count == 1

    # Flag on + patched Graph: a new comment actually fires (public reply + DM).
    calls: list[str] = []

    async def fake_post(self, url, *args, **kwargs):
        calls.append(url)
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"id": "ok"}, request=request)

    monkeypatch.setattr(automation.get_settings(), "instagram_automation_enabled", True, raising=False)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await automation.process_webhook(db_session, _comment_payload("c-2", "quero sim"))
    sent = await db_session.scalar(
        select(InstagramAutomationEvent).where(InstagramAutomationEvent.object_id == "c-2")
    )
    assert sent is not None and sent.status == "sent"
    assert any("/replies" in url for url in calls) and any("/messages" in url for url in calls)

    # Dedupe: the same comment id delivered again does not fire a second time.
    before = len(calls)
    await automation.process_webhook(db_session, _comment_payload("c-2", "quero sim"))
    assert len(calls) == before


@pytest.mark.anyio
async def test_automation_crud_and_live_flag(client, owner):
    headers = await _login(client)
    created = await client.post(
        "/api/instagram/automations",
        headers=headers,
        json={
            "name": "Comentou QUERO",
            "trigger_type": "comment",
            "keywords": ["quero"],
            "public_reply_enabled": True,
            "public_replies": ["respondi no seu direct!"],
            "dm_enabled": True,
            "dm_text": "segue o link",
            "dm_buttons": [{"label": "Comprar", "url": "https://flashpost.tech/x"}],
        },
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    listing = (await client.get("/api/instagram/automations", headers=headers)).json()
    assert listing["live"] is False  # off until Meta App Review
    assert any(a["id"] == rule_id and a["dm_buttons"][0]["label"] == "Comprar" for a in listing["automations"])

    updated = await client.put(
        f"/api/instagram/automations/{rule_id}", headers=headers,
        json={"name": "Comentou QUERO", "trigger_type": "comment", "keywords": ["quero", "eu quero"], "enabled": False},
    )
    assert updated.status_code == 200 and updated.json()["enabled"] is False

    deleted = await client.delete(f"/api/instagram/automations/{rule_id}", headers=headers)
    assert deleted.status_code == 200
    assert (await client.get("/api/instagram/automations", headers=headers)).json()["automations"] == []

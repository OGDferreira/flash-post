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
    InstagramProfileFolder,
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


@pytest.mark.anyio
async def test_spintax_varies_message():
    from app.instagram.automation import expand_spintax

    picks = {expand_spintax("{oi|olá|opa}, {segue|aqui} o link") for _ in range(40)}
    # Every expansion resolves both groups and leaves no braces behind.
    assert all("{" not in p and "}" not in p for p in picks)
    assert len(picks) > 1  # it actually varies
    assert expand_spintax("sem variação") == "sem variação"


@pytest.mark.anyio
async def test_folder_scope_fires_only_for_accounts_in_folder(db_session, owner, monkeypatch):
    _user, workspace = owner
    folder = InstagramProfileFolder(workspace_id=workspace.id, name="VIP")
    db_session.add(folder)
    await db_session.flush()

    in_folder = await _account(db_session, workspace.id)
    in_folder.profile_folder_id = folder.id
    out_folder = InstagramAccount(
        workspace_id=workspace.id,
        instagram_user_id="17840000000008888",
        username="outra_conta",
        encrypted_access_token=encrypt_value("tok2"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(out_folder)

    rule = InstagramCommentAutomation(
        workspace_id=workspace.id,
        name="Só VIP",
        trigger_type="comment",
        keywords=[],  # qualquer comentário
        scope_folder_ids=[str(folder.id)],
        public_reply_enabled=True,
        public_replies=["{oi|olá} 👋"],
        dm_enabled=False,
    )
    db_session.add(rule)
    await db_session.commit()

    calls: list[str] = []

    async def fake_post(self, url, *args, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={"id": "ok"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(automation.get_settings(), "instagram_automation_enabled", True, raising=False)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # Account outside the folder: nothing fires.
    payload_out = _comment_payload("c-out", "qualquer coisa")
    payload_out["entry"][0]["id"] = "17840000000008888"
    await automation.process_webhook(db_session, payload_out)
    assert calls == []

    # Account inside the folder: fires even with no keyword.
    await automation.process_webhook(db_session, _comment_payload("c-in", "qualquer coisa"))
    assert any("/replies" in url for url in calls)


@pytest.mark.anyio
async def test_db_toggle_turns_automations_live(db_session, owner, monkeypatch):
    from app.instagram.automation import AUTOMATIONS_ENABLED_KEY, automations_live
    from app.models import SystemSetting

    monkeypatch.setattr(automation.get_settings(), "instagram_automation_enabled", False, raising=False)
    assert await automations_live(db_session) is False  # env off, no DB row
    db_session.add(SystemSetting(key=AUTOMATIONS_ENABLED_KEY, value={"enabled": True}))
    await db_session.commit()
    assert await automations_live(db_session) is True  # DB toggle turns it on


@pytest.mark.anyio
async def test_live_toggle_endpoint_super_admin_only(client, owner, super_admin):
    # The owner cannot flip the global live flag.
    owner_headers = await _login(client)
    denied = await client.put("/api/instagram/automations/live", headers=owner_headers, json={"enabled": True})
    assert denied.status_code in (401, 403)

    # The Super Admin can.
    token = (await client.get("/api/auth/csrf")).json()["csrf_token"]
    await client.post("/api/auth/login", headers={"X-CSRF-Token": token},
                      json={"email": "superadmin@example.com", "password": "super admin password"})
    admin_headers = {"X-CSRF-Token": (await client.get("/api/auth/csrf")).json()["csrf_token"]}
    ok = await client.put("/api/instagram/automations/live", headers=admin_headers, json={"enabled": True})
    assert ok.status_code == 200 and ok.json()["live"] is True

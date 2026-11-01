"""Super Admin changes a user's account type: owner, partner (sócio) or collaborator."""

import pytest
from sqlalchemy import select

from app.models import Affiliation, WorkspaceMember
from tests.test_affiliates import PASSWORD, _make_owner
from tests.test_wallet import _as


@pytest.mark.anyio
async def test_super_admin_switches_owner_partner_collaborator_and_back(client, db_session, owner, super_admin) -> None:
    chief, chief_ws = owner
    ana, ana_ws = await _make_owner(db_session, "ana")

    await _as(client, "ana@example.com", PASSWORD)
    assert (await client.get("/api/auth/me")).json()["role"] == "OWNER"
    assert (await client.get("/api/instagram/accounts")).status_code == 200
    ana_cookies = dict(client.cookies)

    admin = await _as(client, "superadmin@example.com", "super admin password")
    options = (await client.get(f"/api/admin/users/{ana.id}/account-type")).json()
    assert str(chief.id) in {c["id"] for c in options["chiefs"]}
    assert str(chief_ws.id) in {w["id"] for w in options["workspaces"]}

    # sócio of the chief: the partnership is active and the commission already agreed
    as_partner = await client.put(f"/api/admin/users/{ana.id}/account-type", headers=admin,
                                  json={"type": "partner", "chief_user_id": str(chief.id), "percent": "10"})
    assert as_partner.status_code == 200, as_partner.text
    link = await db_session.scalar(select(Affiliation).where(Affiliation.affiliate_user_id == ana.id))
    await db_session.refresh(link)
    assert link.chief_user_id == chief.id and link.status == "ACTIVE" and link.accepted_at is not None
    assert str(link.participation_percent) == "10.00"
    bad = await client.put(f"/api/admin/users/{ana.id}/account-type", headers=admin,
                           json={"type": "partner", "chief_user_id": str(ana.id)})
    assert bad.status_code == 422

    # collaborator in the chief's operation: her own operation is kept, suspended
    as_collab = await client.put(f"/api/admin/users/{ana.id}/account-type", headers=admin,
                                 json={"type": "collaborator", "workspace_id": str(chief_ws.id)})
    assert as_collab.status_code == 200, as_collab.text
    assert as_collab.json()["role"] == "COLLABORATOR"
    rows = {m.workspace_id: m for m in await db_session.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id == ana.id))}
    for row in rows.values():
        await db_session.refresh(row)
    assert rows[ana_ws.id].status == "SUSPENDED" and rows[chief_ws.id].role == "COLLABORATOR"
    await db_session.refresh(link)
    assert link.status == "ENDED"

    # her open session follows at once: collaborator panel, the chief's operation
    client.cookies.clear()
    client.cookies.update(ana_cookies)
    me = (await client.get("/api/auth/me")).json()
    assert me["role"] == "COLLABORATOR"
    assert (await client.get("/api/instagram/accounts")).status_code == 200

    # back to an independent owner: her operation is active again
    admin = await _as(client, "superadmin@example.com", "super admin password")
    as_owner = await client.put(f"/api/admin/users/{ana.id}/account-type", headers=admin, json={"type": "owner"})
    assert as_owner.status_code == 200 and as_owner.json()["role"] == "OWNER"
    listing = (await client.get("/api/admin/users", params={"q": "ana@"})).json()["items"][0]
    assert listing["role"] == "OWNER" and listing["hierarchy"] == "independent"

    # the Super Admin's own account is not switched here
    me_admin = await client.put(f"/api/admin/users/{super_admin.id}/account-type", headers=admin, json={"type": "owner"})
    assert me_admin.status_code == 409

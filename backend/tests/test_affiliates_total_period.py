"""Regression: the "Total" period (period=all) left the date filter unbounded,
which raised ArgumentError while building the query and returned a 500 to every
chief who opened the Sócios tab. The window must now be optional, and "Total"
must label the real start of the history instead of only "Todo o histórico".
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.nickname import nickname_key
from app.core.security import hash_password
from app.models import Affiliation, SharkTransaction, User, Workspace, WorkspaceMember
from tests.test_loops import _login

NOW = datetime.now(timezone.utc)
PASSWORD = "another strong password"


async def _make_owner(db: AsyncSession, name: str) -> tuple[User, Workspace]:
    user = User(
        email=f"{name}@example.com", nickname=name, nickname_normalized=nickname_key(name),
        full_name=name.title(), password_hash=hash_password(PASSWORD), platform_role="USER",
        is_active=True, is_verified=True,
    )
    db.add(user)
    await db.flush()
    workspace = Workspace(name=f"{name} ws", slug=f"{name}-ws", owner_id=user.id, status="ACTIVE")
    db.add(workspace)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    await db.commit()
    return user, workspace


@pytest.mark.anyio
async def test_total_period_is_unbounded_and_labels_history_start(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    chief, _ = owner
    friend, friend_ws = await _make_owner(db_session, "friend")
    db_session.add(
        Affiliation(
            chief_user_id=chief.id, affiliate_user_id=friend.id, participation_percent=Decimal("10"),
            created_at=datetime(2025, 3, 9, 12, 0, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        SharkTransaction(
            workspace_id=friend_ws.id, transaction_key="old", status="paid", amount=Decimal("200.00"),
            created_at_source=NOW, paid_at=NOW,
        )
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    listing = await client.get("/api/affiliates", params={"period": "all"})
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["rows"] and Decimal(body["rows"][0]["revenue"]) == Decimal("200.00")
    assert body["period_label"] == "Desde 09/03/2025"

    # The per-partner detail and the sócio's own dashboard must survive "Total" too.
    detail = await client.get(f"/api/affiliates/{body['rows'][0]['id']}", params={"period": "all"})
    assert detail.status_code == 200, detail.text
    me = await client.get("/api/partners/me", params={"period": "all"})
    assert me.status_code == 200, me.text

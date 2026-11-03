import uuid
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import Affiliation, AppNotification, User

from tests.test_sharkbot import _login


def _payment(tx: str, amount: str) -> dict:
    return {
        "timestamp": 1789578257,
        "webhook_id": f"w-{uuid.uuid4()}",
        "event": "payment_approved",
        "data": {
            "customer": {"id": "c1", "first_name": "Ana"},
            "bot": {"id": "b1", "name": "Bot"},
            "transaction": {"id": tx, "amount": amount, "status": "paid"},
        },
    }


@pytest.mark.anyio
async def test_chief_is_told_once_about_a_partners_shark_sale(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    partner, _workspace = owner
    chief = User(
        email="chief@example.com",
        nickname="Chefe",
        nickname_normalized="chefe",
        full_name="Chefe Super",
        password_hash=hash_password("x" * 12),
        platform_role="USER",
        is_active=True,
        is_verified=True,
    )
    db_session.add(chief)
    await db_session.flush()
    db_session.add(
        Affiliation(
            chief_user_id=chief.id,
            affiliate_user_id=partner.id,
            participation_percent=Decimal("30"),
            accepted_percent=Decimal("30"),
            status="ACTIVE",
        )
    )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")
    url = urlparse((await client.get("/api/sharkbot/webhook/config")).json()["webhook_url"]).path

    tx = f"tx-{uuid.uuid4()}"
    first = await client.post(url, json=_payment(tx, "50.00"))
    assert first.status_code == 200, first.text
    again = await client.post(url, json=_payment(tx, "50.00"))  # redelivery
    assert again.status_code == 200

    notices = (
        await db_session.scalars(select(AppNotification).where(AppNotification.user_id == chief.id))
    ).all()
    assert len(notices) == 1
    assert notices[0].kind == "commission"
    assert "R$ 50,00" in notices[0].body and "R$ 15,00" in notices[0].body

    # A second, different sale notifies the chief again.
    await client.post(url, json={**_payment(f"tx-{uuid.uuid4()}", "10.00")})
    # The partner's own sale does not notify the partner through this path (only the chief).
    again_notices = (
        await db_session.scalars(select(AppNotification).where(AppNotification.user_id == chief.id))
    ).all()
    assert len(again_notices) == 2

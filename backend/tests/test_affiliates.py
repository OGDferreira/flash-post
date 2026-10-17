import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.nickname import nickname_key
from app.core.security import hash_password
from app.models import (
    Affiliation,
    InstagramAccount,
    SharkTransaction,
    User,
    Workspace,
    WorkspaceMember,
)
from tests.test_loops import _active_account, _csrf, _login
from datetime import datetime, timezone

NOW = datetime.now(timezone.utc)
PASSWORD = "another strong password"


async def _make_owner(db: AsyncSession, name: str) -> tuple[User, Workspace]:
    user = User(
        email=f"{name}@example.com",
        nickname=name,
        nickname_normalized=nickname_key(name),
        full_name=name.title(),
        password_hash=hash_password(PASSWORD),
        platform_role="USER",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    workspace = Workspace(name=f"{name} ws", slug=f"{name}-ws", owner_id=user.id, status="ACTIVE")
    db.add(workspace)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER", status="ACTIVE"))
    await db.commit()
    return user, workspace


async def _code(client: AsyncClient) -> str:
    response = await client.get("/api/affiliates/invite")
    assert response.status_code == 200, response.text
    return response.json()["code"]


async def _join(client: AsyncClient, code: str):
    return await client.post(
        "/api/affiliates/join", headers={"X-CSRF-Token": await _csrf(client)}, json={"code": code}
    )


@pytest.mark.anyio
async def test_each_chief_gets_own_stable_code_and_cannot_join_self(
    client: AsyncClient, owner
) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")
    first = await _code(client)
    assert first == await _code(client)  # stable until rotated
    assert len(first) == 10
    mine = await _join(client, first)
    assert mine.status_code == 422  # own code
    assert (await client.get("/api/affiliates/me")).json()["has_chief"] is False


@pytest.mark.anyio
async def test_join_links_affiliate_and_chief_sets_percent(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    chief, _ws = owner
    await _login(client, "owner@example.com", "correct horse battery staple")
    code = await _code(client)
    friend, friend_ws = await _make_owner(db_session, "friend")
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})

    await _login(client, "friend@example.com", PASSWORD)
    joined = await _join(client, code.lower())  # case/spacing insensitive
    assert joined.status_code == 200, joined.text
    assert joined.json()["has_chief"] is True
    assert Decimal(joined.json()["participation_percent"]) == 0
    assert (await _join(client, code)).status_code == 409  # one chief only
    # The affiliate cannot use chief-only endpoints.
    assert (await client.get("/api/affiliates")).json() is not None  # own (empty) list
    assert (await client.get("/api/affiliates")).json()["rows"] == []
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})

    await _login(client, "owner@example.com", "correct horse battery staple")
    listing = (await client.get("/api/affiliates", params={"period": "30d"})).json()
    assert [row["user_id"] for row in listing["rows"]] == [str(friend.id)]
    link_id = listing["rows"][0]["id"]
    token = await _csrf(client)
    changed = await client.patch(
        f"/api/affiliates/{link_id}", headers={"X-CSRF-Token": token}, json={"participation_percent": "12.5"}
    )
    assert changed.status_code == 200 and Decimal(changed.json()["participation_percent"]) == Decimal("12.5")
    too_high = await client.patch(
        f"/api/affiliates/{link_id}", headers={"X-CSRF-Token": token}, json={"participation_percent": "101"}
    )
    assert too_high.status_code == 422


@pytest.mark.anyio
async def test_cycles_are_rejected(client: AsyncClient, db_session: AsyncSession, owner) -> None:
    a, _ = owner
    b, _ = await _make_owner(db_session, "bravo")
    c, _ = await _make_owner(db_session, "charlie")

    # b joins a  =>  a <- b. A partner's code never creates a second level.
    await _login(client, "owner@example.com", "correct horse battery staple")
    await _code(client)
    code_a = (await client.get("/api/affiliates/invite")).json()["code"]
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    await _login(client, "bravo@example.com", PASSWORD)
    code_b = await _code(client)
    assert (await _join(client, code_a)).status_code == 200
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})
    await _login(client, "charlie@example.com", PASSWORD)
    partner_code = await _join(client, code_b)
    assert partner_code.status_code == 422 and "sócio" in partner_code.json()["detail"]
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})

    # a tries to join c's chief chain the other way round: a <- b <- a
    await _login(client, "owner@example.com", "correct horse battery staple")
    response = await _join(client, code_b)
    assert response.status_code == 422
    assert await _links(client) == 0


async def _links(client: AsyncClient) -> int:
    return len((await client.get("/api/affiliates/me")).json()["chief_name"] or "")


@pytest.mark.anyio
async def test_register_with_invite_code_links_and_invalid_code_blocks_signup(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    await _login(client, "owner@example.com", "correct horse battery staple")
    code = await _code(client)
    await client.post("/api/auth/logout", headers={"X-CSRF-Token": await _csrf(client)})

    def payload(email: str, nick: str, invite: str) -> dict:
        return {
            "full_name": "Novo Usuario", "email": email, "nickname": nick,
            "password": PASSWORD, "confirm_password": PASSWORD, "invite_code": invite,
        }

    bad = await client.post(
        "/api/auth/register", headers={"X-CSRF-Token": await _csrf(client)},
        json=payload("bad@example.com", "badone", "ZZZZZZZZZZ"),
    )
    assert bad.status_code == 422
    assert await db_session.scalar(select(User.id).where(User.email == "bad@example.com")) is None

    good = await client.post(
        "/api/auth/register", headers={"X-CSRF-Token": await _csrf(client)},
        json=payload("good@example.com", "goodone", code),
    )
    assert good.status_code == 201, good.text
    new_id = uuid.UUID(good.json()["user"]["id"])
    link = await db_session.scalar(select(Affiliation).where(Affiliation.affiliate_user_id == new_id))
    assert link is not None and link.participation_percent == 0


@pytest.mark.anyio
async def test_chief_sees_affiliate_numbers_and_participation_but_not_other_chiefs(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    chief, _ = owner
    friend, friend_ws = await _make_owner(db_session, "friend")
    stranger, stranger_ws = await _make_owner(db_session, "stranger")
    db_session.add(_active_account(friend_ws.id, "friend_ig"))
    db_session.add(Affiliation(chief_user_id=chief.id, affiliate_user_id=friend.id, participation_percent=Decimal("10")))
    db_session.add(Affiliation(chief_user_id=stranger.id, affiliate_user_id=(await _make_owner(db_session, "other"))[0].id))
    for key, amount in (("t1", Decimal("100.00")), ("t2", Decimal("50.00"))):
        db_session.add(
            SharkTransaction(
                workspace_id=friend_ws.id, transaction_key=key, status="paid", amount=amount,
                created_at_source=NOW, paid_at=NOW,
            )
        )
    await db_session.commit()
    await _login(client, "owner@example.com", "correct horse battery staple")

    listing = (await client.get("/api/affiliates", params={"period": "today"})).json()
    row = listing["rows"][0]
    assert Decimal(row["revenue"]) == Decimal("150.00")
    assert Decimal(row["participation_amount"]) == Decimal("15.00")  # 10 % of 150
    assert row["accounts_total"] == 1 and row["purchases"] == 2
    assert "bruto" in listing["basis"]
    detail = (await client.get(f"/api/affiliates/{row['id']}", params={"period": "today"})).json()
    assert detail["accounts"][0]["username"] == "friend_ig"

    foreign = await db_session.scalar(select(Affiliation.id).where(Affiliation.chief_user_id == stranger.id))
    assert (await client.get(f"/api/affiliates/{foreign}")).status_code == 404
    token = await _csrf(client)
    assert (await client.patch(
        f"/api/affiliates/{foreign}", headers={"X-CSRF-Token": token}, json={"participation_percent": "5"}
    )).status_code == 404
    assert (await client.delete(f"/api/affiliates/{foreign}", headers={"X-CSRF-Token": token})).status_code == 404


@pytest.mark.anyio
async def test_affiliate_cannot_read_chief_data(
    client: AsyncClient, db_session: AsyncSession, owner
) -> None:
    chief, chief_ws = owner
    friend, _ = await _make_owner(db_session, "friend")
    db_session.add(_active_account(chief_ws.id, "chief_secret_ig"))
    db_session.add(Affiliation(chief_user_id=chief.id, affiliate_user_id=friend.id))
    await db_session.commit()
    link_id = await db_session.scalar(select(Affiliation.id))
    await _login(client, "friend@example.com", PASSWORD)
    # Own list is empty; the chief's link is not reachable through any endpoint.
    assert (await client.get("/api/affiliates")).json()["rows"] == []
    assert (await client.get(f"/api/affiliates/{link_id}")).status_code == 404
    accounts = (await client.get("/api/instagram/accounts")).json()
    assert "chief_secret_ig" not in str(accounts)
    mine = (await client.get("/api/affiliates/me")).json()
    assert mine["has_chief"] is True and "secret" not in str(mine)


@pytest.mark.anyio
async def test_database_blocks_self_link_and_second_chief(db_session: AsyncSession, owner) -> None:
    from sqlalchemy.exc import IntegrityError

    user, _ = owner
    other, _ = await _make_owner(db_session, "other")
    user_id, other_id = user.id, other.id  # a rollback expires loaded objects
    db_session.add(Affiliation(chief_user_id=user_id, affiliate_user_id=user_id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    db_session.add(Affiliation(chief_user_id=user_id, affiliate_user_id=other_id))
    await db_session.commit()
    db_session.add(Affiliation(chief_user_id=other_id, affiliate_user_id=other_id))
    with pytest.raises(IntegrityError):
        await db_session.commit()

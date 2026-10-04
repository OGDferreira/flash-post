import os
import subprocess
import sys
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.rate_limit import LoginRateLimiter
from app.core.nickname import nickname_key

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_PATH = Path(tempfile.gettempdir()) / f"flashpost-tests-{os.getpid()}.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

os.environ["ENVIRONMENT"] = "test"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SESSION_SECRET"] = "test-only-session-secret-not-for-production"
os.environ["MASTER_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus) -> None:
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        from app.models import (
            CollaboratorPayment,
            InstagramAccount,
            InstagramAppCredential,
            InstagramLoop,
            InstagramLoopAccount,
            InstagramLoopMedia,
            InstagramMedia,
            InstagramProfileFolder,
            InstagramPublicationJob,
            SharkEvent,
            SystemSetting,
            User,
            Workspace,
            WorkspaceMember,
        )

        await connection.execute(delete(CollaboratorPayment))
        await connection.execute(delete(InstagramPublicationJob))
        await connection.execute(delete(SharkEvent))
        await connection.execute(delete(InstagramLoopMedia))
        await connection.execute(delete(InstagramLoopAccount))
        await connection.execute(delete(InstagramLoop))
        await connection.execute(delete(InstagramMedia))
        await connection.execute(delete(InstagramAccount))
        await connection.execute(delete(InstagramProfileFolder))
        await connection.execute(delete(InstagramAppCredential))
        await connection.execute(delete(WorkspaceMember))
        await connection.execute(delete(SystemSetting))
        await connection.execute(delete(Workspace))
        await connection.execute(delete(User))
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession):
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.core.config import get_settings
    from app.main import app, check_database_readiness

    settings = get_settings()
    app.state.registration_rate_limiter = LoginRateLimiter(
        settings.registration_max_attempts,
        settings.registration_window_seconds,
    )
    app.state.nickname_check_rate_limiter = LoginRateLimiter(
        settings.nickname_check_max_attempts,
        settings.nickname_check_window_seconds,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[check_database_readiness] = lambda: True
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(check_database_readiness, None)


@pytest.fixture
async def owner(db_session: AsyncSession):
    from app.core.security import hash_password
    from app.models import User, Workspace, WorkspaceMember

    user = User(
        email="owner@example.com",
        nickname="Gui Ferreira",
        nickname_normalized=nickname_key("Gui Ferreira"),
        full_name="FlashPost Owner",
        password_hash=hash_password("correct horse battery staple"),
        platform_role="USER",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    workspace = Workspace(
        name="Owner Workspace",
        slug="owner-workspace",
        owner_id=user.id,
        status="ACTIVE",
    )
    db_session.add(workspace)
    await db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="OWNER",
            status="ACTIVE",
        )
    )
    await db_session.commit()
    return user, workspace


@pytest.fixture
async def collaborator(db_session: AsyncSession, owner):
    from app.core.security import hash_password
    from app.models import User, WorkspaceMember

    _owner_user, workspace = owner
    user = User(
        email="collaborator@example.com",
        nickname="Colaborador",
        nickname_normalized=nickname_key("Colaborador"),
        full_name="FlashPost Collaborator",
        password_hash=hash_password("collaborator password"),
        platform_role="USER",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="COLLABORATOR",
            status="ACTIVE",
        )
    )
    await db_session.commit()
    return user


@pytest.fixture
async def super_admin(db_session: AsyncSession):
    from app.core.security import hash_password
    from app.models import User

    user = User(
        email="superadmin@example.com",
        nickname="Super Admin",
        nickname_normalized=nickname_key("Super Admin"),
        full_name="FlashPost Super Admin",
        password_hash=hash_password("super admin password"),
        platform_role="SUPER_ADMIN",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user

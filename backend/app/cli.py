import argparse
import asyncio
import getpass
import re
import sys
import unicodedata
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.database import dispose_engine, get_session_factory
from app.core.nickname import nickname_key, normalize_nickname
from app.core.security import PlatformRole, WorkspaceRole, hash_password
from app.models import User, Workspace, WorkspaceMember

def _prompt_email() -> str:
    value = input("Email: ").strip().casefold()
    try:
        from pydantic import EmailStr

        return str(TypeAdapter(EmailStr).validate_python(value))
    except ValidationError as exc:
        raise ValueError("Enter a valid email address.") from exc


def _prompt_nickname() -> str:
    try:
        return normalize_nickname(input("Nickname: "))
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def _prompt_password() -> str:
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if password != confirmation:
        raise ValueError("The passwords did not match.")
    return password


def _slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    if not slug:
        slug = f"workspace-{uuid4().hex[:8]}"
    return slug[:180].rstrip("-")


async def _create_super_admin() -> None:
    async with get_session_factory()() as db:
        existing_count = await db.scalar(
            select(func.count()).select_from(User).where(
                User.platform_role == PlatformRole.SUPER_ADMIN.value
            )
        ) or 0
        if existing_count and input(
            f"{existing_count} SUPER_ADMIN account(s) already exist. Create another? [y/N]: "
        ).strip().casefold() != "y":
            print("No changes made.")
            return

        email = _prompt_email()
        full_name = input("Full name: ").strip()
        if not full_name or len(full_name) > 160:
            raise ValueError("Full name must contain between 1 and 160 characters.")
        nickname = _prompt_nickname()
        password = _prompt_password()
        user = User(
            email=email,
            nickname=nickname,
            nickname_normalized=nickname_key(nickname),
            full_name=full_name,
            password_hash=hash_password(password),
            platform_role=PlatformRole.SUPER_ADMIN.value,
            is_active=True,
            is_verified=True,
            is_approved=True,
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValueError("An account already exists for that email or username.") from exc
        print(f"SUPER_ADMIN created for {user.email}. Password was not displayed.")


async def _create_owner() -> None:
    async with get_session_factory()() as db:
        email = _prompt_email()
        full_name = input("Full name: ").strip()
        workspace_name = input("Workspace name: ").strip()
        if not full_name or len(full_name) > 160:
            raise ValueError("Full name must contain between 1 and 160 characters.")
        if not workspace_name or len(workspace_name) > 160:
            raise ValueError("Workspace name must contain between 1 and 160 characters.")
        nickname = _prompt_nickname()
        password = _prompt_password()
        user = User(
            email=email,
            nickname=nickname,
            nickname_normalized=nickname_key(nickname),
            full_name=full_name,
            password_hash=hash_password(password),
            platform_role=PlatformRole.USER.value,
            is_active=True,
            is_verified=True,
            is_approved=True,
        )
        db.add(user)
        await db.flush()
        workspace = Workspace(
            name=workspace_name,
            slug=_slugify(workspace_name),
            owner_id=user.id,
            status="ACTIVE",
        )
        db.add(workspace)
        await db.flush()
        db.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.OWNER.value,
                status="ACTIVE",
            )
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValueError("An account or workspace with those unique details already exists.") from exc
        print(f"OWNER {user.email} and workspace {workspace.slug} created.")


async def _promote_existing_super_admin(email: str) -> None:
    async with get_session_factory()() as db:
        user = await db.scalar(select(User).where(func.lower(User.email) == email.casefold()))
        if user is None:
            raise ValueError("No existing account was found for that email.")
        if user.platform_role == PlatformRole.SUPER_ADMIN.value:
            print("The existing account is already a SUPER_ADMIN. No changes made.")
            return
        user.platform_role = PlatformRole.SUPER_ADMIN.value
        await db.commit()
        print(f"Existing account {user.email} promoted to SUPER_ADMIN; all other data was preserved.")


async def _run(action: str, email: str | None = None) -> None:
    try:
        if action == "create-super-admin":
            await _create_super_admin()
        elif action == "create-owner":
            await _create_owner()
        elif email is not None:
            await _promote_existing_super_admin(email)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="FlashPost administrative bootstrap CLI.")
    parser.add_subparsers(dest="action", required=True)
    parser.add_parser("create-super-admin", help="Create a platform SUPER_ADMIN account.")
    parser.add_parser("create-owner", help="Create the first OWNER and workspace.")
    promote = parser.add_parser(
        "promote-super-admin",
        help="Promote an existing account without changing its password or relations.",
    )
    promote.add_argument("email", help="Email address of the existing account.")
    args = parser.parse_args()

    try:
        asyncio.run(_run(args.action, getattr(args, "email", None)))
    except (ValueError, RuntimeError) as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

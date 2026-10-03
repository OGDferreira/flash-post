import logging
import secrets
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.auth.dependencies import (
    DbSession,
    OwnerAccess,
    WorkspaceMemberAccess,
    require_csrf,
)
from app.core.config import get_settings
from app.core.crypto import decrypt_value, encrypt_value
from app.core.security import WorkspaceRole
from app.instagram.oauth import (
    InstagramOAuthError,
    build_authorization_url,
    exchange_instagram_authorization_code,
    revoke_instagram_permissions,
)
from app.models import (
    InstagramAccount,
    InstagramAppCredential,
    User,
    Workspace,
    WorkspaceMember,
)
from app.schemas.instagram import (
    InstagramAccountResponse,
    InstagramAccountsResponse,
    InstagramAppSettingsRequest,
    InstagramAppSettingsResponse,
    InstagramConnectResponse,
    InstagramDisconnectResponse,
)

router = APIRouter(prefix="/api/instagram", tags=["Instagram accounts"])
logger = logging.getLogger(__name__)
_OAUTH_SESSION_KEY = "instagram_oauth"
_OAUTH_STATE_MAX_AGE_SECONDS = 600


def _redirect_uri() -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/instagram/callback"


def _accounts_page(outcome: str) -> str:
    return (
        f"{get_settings().public_base_url.rstrip('/')}/feature/accounts?"
        f"{urlencode({'instagram': outcome})}"
    )


@router.get("/accounts", response_model=InstagramAccountsResponse)
async def list_accounts(
    access: WorkspaceMemberAccess,
    db: DbSession,
) -> InstagramAccountsResponse:
    accounts = (
        await db.scalars(
            select(InstagramAccount)
            .where(InstagramAccount.workspace_id == access.workspace.id)
            .order_by(InstagramAccount.connected_at, InstagramAccount.id)
        )
    ).all()
    return InstagramAccountsResponse(
        can_manage=access.membership.role == WorkspaceRole.OWNER.value,
        accounts=[
            InstagramAccountResponse(
                id=account.id,
                username=account.username,
                token_expires_at=account.token_expires_at,
                connected_at=account.connected_at,
            )
            for account in accounts
        ],
    )


async def _workspace_app_credential(
    workspace_id: uuid.UUID,
    db: DbSession,
) -> InstagramAppCredential | None:
    return await db.get(InstagramAppCredential, workspace_id)


def _app_settings_response(
    credential: InstagramAppCredential | None,
) -> InstagramAppSettingsResponse:
    encryption_configured = get_settings().master_encryption_key is not None
    return InstagramAppSettingsResponse(
        configured=credential is not None and encryption_configured,
        app_id=credential.app_id if credential is not None else None,
        app_secret_configured=credential is not None,
    )


@router.get("/app-settings", response_model=InstagramAppSettingsResponse)
async def get_instagram_app_settings(
    access: OwnerAccess,
    db: DbSession,
) -> InstagramAppSettingsResponse:
    credential = await _workspace_app_credential(access.workspace.id, db)
    return _app_settings_response(credential)


@router.put(
    "/app-settings",
    response_model=InstagramAppSettingsResponse,
    dependencies=[Depends(require_csrf)],
)
async def save_instagram_app_settings(
    payload: InstagramAppSettingsRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramAppSettingsResponse:
    if get_settings().master_encryption_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure credential storage is not configured for this environment.",
        )

    credential = await _workspace_app_credential(access.workspace.id, db)
    if payload.app_id != (credential.app_id if credential is not None else None):
        has_accounts = await db.scalar(
            select(InstagramAccount.id)
            .where(InstagramAccount.workspace_id == access.workspace.id)
            .limit(1)
        )
        if has_accounts is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Disconnect all Instagram accounts before changing the App ID.",
            )

    if payload.app_secret is None and credential is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enter the Instagram App Secret to configure this workspace.",
        )

    try:
        encrypted_secret = (
            encrypt_value(payload.app_secret)
            if payload.app_secret is not None
            else None
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure credential storage is unavailable.",
        ) from None

    if credential is None:
        credential = InstagramAppCredential(
            workspace_id=access.workspace.id,
            app_id=payload.app_id,
            encrypted_app_secret=encrypted_secret or "",
            revision=uuid.uuid4(),
        )
        db.add(credential)
    else:
        credential.app_id = payload.app_id
        if encrypted_secret is not None:
            credential.encrypted_app_secret = encrypted_secret
        credential.revision = uuid.uuid4()
    await db.commit()
    return _app_settings_response(credential)


@router.delete(
    "/app-settings",
    response_model=InstagramAppSettingsResponse,
    dependencies=[Depends(require_csrf)],
)
async def delete_instagram_app_settings(
    access: OwnerAccess,
    db: DbSession,
) -> InstagramAppSettingsResponse:
    has_accounts = await db.scalar(
        select(InstagramAccount.id)
        .where(InstagramAccount.workspace_id == access.workspace.id)
        .limit(1)
    )
    if has_accounts is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Disconnect all Instagram accounts before removing the Meta app settings.",
        )
    credential = await _workspace_app_credential(access.workspace.id, db)
    if credential is not None:
        await db.delete(credential)
        await db.commit()
    return _app_settings_response(None)


@router.post(
    "/connect",
    response_model=InstagramConnectResponse,
    dependencies=[Depends(require_csrf)],
)
async def connect_account(
    request: Request,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramConnectResponse:
    settings = get_settings()
    credential = await _workspace_app_credential(access.workspace.id, db)
    if credential is None or settings.master_encryption_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The workspace Meta App ID and App Secret must be configured, and "
                "secure credential storage must be enabled."
            ),
        )
    try:
        app_secret = decrypt_value(credential.encrypted_app_secret)
    except (RuntimeError, ValueError) as exc:
        logger.error("Instagram App Secret could not be decrypted (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The workspace Meta App Secret cannot be read securely.",
        ) from None

    state = secrets.token_urlsafe(32)
    request.session[_OAUTH_SESSION_KEY] = {
        "state": state,
        "user_id": request.session["user_id"],
        "workspace_id": str(access.workspace.id),
        "credential_revision": str(credential.revision),
        "created_at": int(time.time()),
    }
    return InstagramConnectResponse(
        authorization_url=build_authorization_url(
            credential.app_id,
            _redirect_uri(),
            state,
        )
    )


@router.get("/callback", name="instagram_callback")
async def instagram_callback(
    request: Request,
    db: DbSession,
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=256),
    error: str | None = Query(default=None, max_length=128),
) -> Response:
    pending = request.session.get(_OAUTH_SESSION_KEY)
    if not isinstance(pending, dict):
        return RedirectResponse(_accounts_page("error"), status_code=303)
    expected_state = pending.get("state")
    created_at = pending.get("created_at")
    if (
        not isinstance(state, str)
        or not isinstance(expected_state, str)
        or not secrets.compare_digest(state, expected_state)
        or not isinstance(created_at, int)
        or int(time.time()) - created_at > _OAUTH_STATE_MAX_AGE_SECONDS
        or request.session.get("user_id") != pending.get("user_id")
    ):
        return RedirectResponse(_accounts_page("error"), status_code=303)
    request.session.pop(_OAUTH_SESSION_KEY, None)

    if error:
        outcome = "cancelled" if error == "access_denied" else "error"
        return RedirectResponse(_accounts_page(outcome), status_code=303)
    if not code:
        return RedirectResponse(_accounts_page("error"), status_code=303)

    try:
        user_id = uuid.UUID(str(pending.get("user_id")))
        workspace_id = uuid.UUID(str(pending.get("workspace_id")))
    except (ValueError, TypeError, AttributeError):
        return RedirectResponse(_accounts_page("error"), status_code=303)

    user = await db.scalar(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    workspace = await db.scalar(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.status == "ACTIVE",
        )
    )
    membership = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.status == "ACTIVE",
            WorkspaceMember.role == WorkspaceRole.OWNER.value,
        )
    )
    if user is None or workspace is None or membership is None:
        return RedirectResponse(_accounts_page("error"), status_code=303)

    credential = await _workspace_app_credential(workspace_id, db)
    if (
        credential is None
        or str(credential.revision) != pending.get("credential_revision")
    ):
        return RedirectResponse(_accounts_page("error"), status_code=303)
    try:
        app_secret = decrypt_value(credential.encrypted_app_secret)
    except (RuntimeError, ValueError) as exc:
        logger.error("Instagram App Secret could not be decrypted (%s).", type(exc).__name__)
        return RedirectResponse(_accounts_page("error"), status_code=303)

    try:
        instagram_user_id, username, access_token, expires_at = (
            await exchange_instagram_authorization_code(
                code,
                _redirect_uri(),
                credential.app_id,
                app_secret,
            )
        )
    except (httpx.HTTPError, InstagramOAuthError, RuntimeError, ValueError) as exc:
        logger.warning("Instagram OAuth callback failed (%s).", type(exc).__name__)
        return RedirectResponse(_accounts_page("error"), status_code=303)

    try:
        encrypted_token = encrypt_value(access_token)
    except RuntimeError as exc:
        logger.error("Instagram token encryption failed (%s).", type(exc).__name__)
        return RedirectResponse(_accounts_page("error"), status_code=303)

    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.workspace_id == workspace_id,
            InstagramAccount.instagram_user_id == instagram_user_id,
        )
    )
    if account is None:
        account = InstagramAccount(
            workspace_id=workspace_id,
            instagram_user_id=instagram_user_id,
            username=username,
            encrypted_access_token=encrypted_token,
            token_expires_at=expires_at,
        )
        db.add(account)
    else:
        account.username = username
        account.encrypted_access_token = encrypted_token
        account.token_expires_at = expires_at
        account.connected_at = datetime.now(timezone.utc)
    await db.commit()
    return RedirectResponse(_accounts_page("connected"), status_code=303)


@router.delete(
    "/accounts/{account_id}",
    response_model=InstagramDisconnectResponse,
    dependencies=[Depends(require_csrf)],
)
async def disconnect_account(
    account_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramDisconnectResponse:
    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.id == account_id,
            InstagramAccount.workspace_id == access.workspace.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instagram account not found.")
    try:
        access_token = decrypt_value(account.encrypted_access_token)
    except (RuntimeError, ValueError) as exc:
        logger.warning("Instagram token could not be decrypted for revocation (%s).", type(exc).__name__)
        access_token = None
    await db.delete(account)
    await db.commit()

    meta_revoked = False
    if access_token is not None:
        try:
            meta_revoked = await revoke_instagram_permissions(access_token)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Instagram permission revocation failed (%s).", type(exc).__name__)
    if not meta_revoked:
        logger.warning("Instagram account was removed locally without confirmed Meta revocation.")
    return InstagramDisconnectResponse(meta_revoked=meta_revoked)

import logging
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update

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
    fetch_meta_app_info,
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
    InstagramMetaAppActionResponse,
    InstagramMetaAppCreateRequest,
    InstagramMetaAppResponse,
    InstagramMetaAppsResponse,
    InstagramMetaAppUpdateRequest,
    InstagramConnectResponse,
    InstagramDisconnectResponse,
    InstagramAccountFeedResponse,
    InstagramAccountHighlightsRequest,
    InstagramFeedMediaResponse,
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


def _connection_result_page(return_to: str, outcome: str) -> str:
    if return_to == "/dashboard":
        return (
            f"{get_settings().public_base_url.rstrip('/')}/dashboard?"
            f"{urlencode({'instagram': outcome})}"
        )
    return _accounts_page(outcome)


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


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
        can_connect=access.membership.role
        in {WorkspaceRole.OWNER.value, WorkspaceRole.COLLABORATOR.value},
        accounts=[
            InstagramAccountResponse(
                id=account.id,
                profile_folder_id=account.profile_folder_id,
                has_highlights=account.has_highlights,
                username=account.username,
                profile_picture_url=account.profile_picture_url,
                follower_count=account.follower_count,
                media_count=account.media_count,
                token_expires_at=_utc_datetime(account.token_expires_at),
                connected_at=_utc_datetime(account.connected_at),
                error_at=(
                    _utc_datetime(account.updated_at)
                    if account.status == "error"
                    else None
                ),
                status=account.status,
            )
            for account in accounts
        ],
    )


@router.patch(
    "/accounts/{account_id}/highlights",
    response_model=InstagramAccountResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_account_highlights(
    account_id: uuid.UUID,
    payload: InstagramAccountHighlightsRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramAccountResponse:
    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.id == account_id,
            InstagramAccount.workspace_id == access.workspace.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instagram account not found.")
    account.has_highlights = payload.has_highlights
    await db.commit()
    await db.refresh(account)
    return InstagramAccountResponse(
        id=account.id,
        profile_folder_id=account.profile_folder_id,
        has_highlights=account.has_highlights,
        username=account.username,
        profile_picture_url=account.profile_picture_url,
        follower_count=account.follower_count,
        media_count=account.media_count,
        token_expires_at=_utc_datetime(account.token_expires_at),
        connected_at=_utc_datetime(account.connected_at),
        error_at=(
            _utc_datetime(account.updated_at)
            if account.status == "error"
            else None
        ),
        status=account.status,
    )


@router.get(
    "/accounts/{account_id}/feed",
    response_model=InstagramAccountFeedResponse,
)
async def get_account_feed(
    account_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramAccountFeedResponse:
    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.id == account_id,
            InstagramAccount.workspace_id == access.workspace.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instagram account not found.")
    if account.encrypted_access_token is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta conta não possui uma autorização ativa. Reconecte-a no Hub de Contas.",
        )
    try:
        access_token = decrypt_value(account.encrypted_access_token)
    except (RuntimeError, ValueError) as exc:
        logger.error("Instagram token could not be decrypted for feed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível ler a autorização salva desta conta com segurança.",
        ) from None

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"https://graph.instagram.com/v25.0/{account.instagram_user_id}/media",
                params={
                    "fields": (
                        "id,media_type,media_url,thumbnail_url,permalink,timestamp,"
                        "caption,like_count,comments_count"
                    ),
                    "limit": "25",
                    "access_token": access_token,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Instagram feed request was rejected for account %s (HTTP %s).",
            account.id,
            exc.response.status_code,
        )
        if exc.response.status_code in {401, 403}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O Instagram recusou a autorização desta conta. Reconecte-a no Hub de Contas.",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="O Instagram não conseguiu carregar as mídias recentes. Tente novamente.",
        ) from None
    except httpx.HTTPError as exc:
        logger.warning(
            "Instagram feed request failed for account %s (%s).",
            account.id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível conectar ao Instagram para carregar as mídias recentes.",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="O Instagram retornou uma resposta inválida para as mídias recentes.",
        ) from None

    raw_media = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_media, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="O Instagram retornou uma lista de mídias inválida.",
        )
    media = []
    for item in raw_media:
        if not isinstance(item, dict):
            continue
        media_id = item.get("id")
        if not isinstance(media_id, (str, int)) or not str(media_id):
            continue
        values: dict[str, object] = {}
        for field in ("media_url", "thumbnail_url", "permalink"):
            value = item.get(field)
            values[field] = (
                value
                if isinstance(value, str) and value.startswith("https://")
                else None
            )
        timestamp = item.get("timestamp")
        try:
            parsed_timestamp = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            ) if isinstance(timestamp, str) else None
        except ValueError:
            parsed_timestamp = None
        media.append(
            InstagramFeedMediaResponse(
                id=str(media_id),
                media_type=item.get("media_type")
                if isinstance(item.get("media_type"), str)
                else "UNKNOWN",
                media_url=values["media_url"],
                thumbnail_url=values["thumbnail_url"],
                permalink=values["permalink"],
                timestamp=parsed_timestamp,
                caption=item.get("caption") if isinstance(item.get("caption"), str) else None,
                like_count=item.get("like_count")
                if isinstance(item.get("like_count"), int)
                and not isinstance(item.get("like_count"), bool)
                else None,
                comments_count=item.get("comments_count")
                if isinstance(item.get("comments_count"), int)
                and not isinstance(item.get("comments_count"), bool)
                else None,
            )
        )
    return InstagramAccountFeedResponse(
        account_id=account.id,
        username=account.username,
        followers_count=account.follower_count,
        media_count=account.media_count,
        follows_count=None,
        media=media,
    )


def _meta_app_response(app: InstagramAppCredential) -> InstagramMetaAppResponse:
    return InstagramMetaAppResponse(
        id=app.id,
        display_name=app.display_name,
        meta_app_name=app.meta_app_name,
        app_id=app.app_id,
        category=app.category,
        app_link=app.app_link,
        is_selected=app.is_selected,
        app_secret_configured=True,
    )


async def _workspace_meta_app(
    workspace_id: uuid.UUID,
    app_id: uuid.UUID,
    db: DbSession,
) -> InstagramAppCredential | None:
    return await db.scalar(
        select(InstagramAppCredential).where(
            InstagramAppCredential.id == app_id,
            InstagramAppCredential.workspace_id == workspace_id,
        )
    )


async def _fetch_and_validate_meta_app(
    app_id: str,
    app_secret: str,
) -> tuple[str, str | None, str | None]:
    try:
        return await fetch_meta_app_info(app_id, app_secret)
    except httpx.HTTPStatusError as exc:
        logger.warning("Meta app lookup was rejected (HTTP %s).", exc.response.status_code)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Meta could not validate this App ID and App Secret.",
        ) from None
    except (httpx.HTTPError, InstagramOAuthError) as exc:
        logger.warning("Meta app lookup failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve app information from Meta. Try again later.",
        ) from None


@router.get("/apps", response_model=InstagramMetaAppsResponse)
async def list_meta_apps(
    access: OwnerAccess,
    db: DbSession,
) -> InstagramMetaAppsResponse:
    apps = (
        await db.scalars(
            select(InstagramAppCredential)
            .where(InstagramAppCredential.workspace_id == access.workspace.id)
            .order_by(InstagramAppCredential.display_name, InstagramAppCredential.id)
        )
    ).all()
    selected = next((app.id for app in apps if app.is_selected), None)
    return InstagramMetaAppsResponse(
        can_manage=True,
        selected_app_id=selected,
        apps=[_meta_app_response(app) for app in apps],
    )


@router.post(
    "/apps",
    response_model=InstagramMetaAppActionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_meta_app(
    payload: InstagramMetaAppCreateRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramMetaAppActionResponse:
    settings = get_settings()
    if settings.master_encryption_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure credential storage is not configured for this environment.",
        )

    existing = await db.scalar(
        select(InstagramAppCredential.id).where(
            InstagramAppCredential.workspace_id == access.workspace.id,
            InstagramAppCredential.app_id == payload.app_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Meta App ID is already registered in this workspace.",
        )

    meta_name, category, app_link = await _fetch_and_validate_meta_app(
        payload.app_id,
        payload.app_secret,
    )

    existing_selected = await db.scalar(
        select(InstagramAppCredential.id).where(
            InstagramAppCredential.workspace_id == access.workspace.id,
            InstagramAppCredential.is_selected.is_(True),
        )
    )
    try:
        encrypted_secret = encrypt_value(payload.app_secret)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure credential storage is unavailable.",
        ) from None

    app = InstagramAppCredential(
        workspace_id=access.workspace.id,
        display_name=payload.display_name,
        meta_app_name=meta_name,
        app_id=payload.app_id,
        category=category,
        app_link=app_link,
        encrypted_app_secret=encrypted_secret,
        is_selected=existing_selected is None,
        revision=uuid.uuid4(),
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return InstagramMetaAppActionResponse(
        selected_app_id=app.id if app.is_selected else existing_selected,
        app=_meta_app_response(app),
    )


@router.put(
    "/apps/{app_id}/select",
    response_model=InstagramMetaAppActionResponse,
    dependencies=[Depends(require_csrf)],
)
async def select_meta_app(
    app_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramMetaAppActionResponse:
    app = await _workspace_meta_app(access.workspace.id, app_id, db)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta app not found.")
    await db.execute(
        update(InstagramAppCredential)
        .where(InstagramAppCredential.workspace_id == access.workspace.id)
        .values(is_selected=False)
    )
    app.is_selected = True
    await db.commit()
    return InstagramMetaAppActionResponse(
        selected_app_id=app.id,
        app=_meta_app_response(app),
    )


@router.patch(
    "/apps/{app_id}",
    response_model=InstagramMetaAppResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_meta_app(
    app_id: uuid.UUID,
    payload: InstagramMetaAppUpdateRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramMetaAppResponse:
    app = await _workspace_meta_app(access.workspace.id, app_id, db)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta app not found.")

    if payload.display_name is not None:
        app.display_name = payload.display_name
    if payload.app_secret is not None:
        if get_settings().master_encryption_key is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Secure credential storage is not configured for this environment.",
            )
        meta_name, category, app_link = await _fetch_and_validate_meta_app(
            app.app_id,
            payload.app_secret,
        )
        try:
            app.encrypted_app_secret = encrypt_value(payload.app_secret)
        except RuntimeError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Secure credential storage is unavailable.",
            ) from None
        app.meta_app_name = meta_name
        app.category = category
        app.app_link = app_link
        app.revision = uuid.uuid4()

    await db.commit()
    await db.refresh(app)
    return _meta_app_response(app)


@router.delete(
    "/apps/{app_id}",
    response_model=InstagramMetaAppsResponse,
    dependencies=[Depends(require_csrf)],
)
async def delete_meta_app(
    app_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramMetaAppsResponse:
    app = await _workspace_meta_app(access.workspace.id, app_id, db)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta app not found.")

    linked_account = await db.scalar(
        select(InstagramAccount.id)
        .where(InstagramAccount.app_credential_id == app.id)
        .limit(1)
    )
    if linked_account is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Disconnect the Instagram accounts connected with this app before removing it.",
        )

    was_selected = app.is_selected
    await db.delete(app)
    if was_selected:
        replacement = await db.scalar(
            select(InstagramAppCredential)
            .where(
                InstagramAppCredential.workspace_id == access.workspace.id,
                InstagramAppCredential.id != app_id,
            )
            .order_by(InstagramAppCredential.display_name, InstagramAppCredential.id)
            .limit(1)
        )
        if replacement is not None:
            replacement.is_selected = True
    await db.commit()
    return await list_meta_apps(access, db)


@router.post(
    "/connect",
    response_model=InstagramConnectResponse,
    dependencies=[Depends(require_csrf)],
)
async def connect_account(
    request: Request,
    access: WorkspaceMemberAccess,
    db: DbSession,
    return_to: Literal["/dashboard", "/feature/accounts"] = "/feature/accounts",
) -> InstagramConnectResponse:
    settings = get_settings()
    credential = await db.scalar(
        select(InstagramAppCredential).where(
            InstagramAppCredential.workspace_id == access.workspace.id,
            InstagramAppCredential.is_selected.is_(True),
        )
    )
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
        "meta_app_id": str(credential.id),
        "credential_revision": str(credential.revision),
        "created_at": int(time.time()),
        "return_to": return_to,
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
    return_to = pending.get("return_to")
    if return_to not in {"/dashboard", "/feature/accounts"}:
        return_to = "/feature/accounts"
    request.session.pop(_OAUTH_SESSION_KEY, None)

    if error:
        outcome = "cancelled" if error == "access_denied" else "error"
        return RedirectResponse(_connection_result_page(return_to, outcome), status_code=303)
    if not code:
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)

    try:
        user_id = uuid.UUID(str(pending.get("user_id")))
        workspace_id = uuid.UUID(str(pending.get("workspace_id")))
    except (ValueError, TypeError, AttributeError):
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)

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
            WorkspaceMember.role.in_(
                (WorkspaceRole.OWNER.value, WorkspaceRole.COLLABORATOR.value)
            ),
        )
    )
    if user is None or workspace is None or membership is None:
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)

    try:
        meta_app_id = uuid.UUID(str(pending.get("meta_app_id")))
    except (ValueError, TypeError, AttributeError):
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)
    credential = await _workspace_meta_app(workspace_id, meta_app_id, db)
    if (
        credential is None
        or str(credential.revision) != pending.get("credential_revision")
    ):
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)
    try:
        app_secret = decrypt_value(credential.encrypted_app_secret)
    except (RuntimeError, ValueError) as exc:
        logger.error("Instagram App Secret could not be decrypted (%s).", type(exc).__name__)
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)

    try:
        (
            instagram_user_id,
            username,
            profile_picture_url,
            follower_count,
            media_count,
            access_token,
            expires_at,
        ) = (
            await exchange_instagram_authorization_code(
                code,
                _redirect_uri(),
                credential.app_id,
                app_secret,
            )
        )
    except InstagramOAuthError as exc:
        logger.warning("Instagram OAuth validation failed: %s", exc)
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Instagram OAuth token exchange was rejected by Meta (HTTP %s).",
            exc.response.status_code,
        )
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        logger.warning("Instagram OAuth callback failed (%s).", type(exc).__name__)
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)

    try:
        encrypted_token = encrypt_value(access_token)
    except RuntimeError as exc:
        logger.error("Instagram token encryption failed (%s).", type(exc).__name__)
        return RedirectResponse(_connection_result_page(return_to, "error"), status_code=303)

    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.workspace_id == workspace_id,
            InstagramAccount.instagram_user_id == instagram_user_id,
        )
    )
    if account is None:
        account = InstagramAccount(
            workspace_id=workspace_id,
            app_credential_id=credential.id,
            instagram_user_id=instagram_user_id,
            username=username,
            profile_picture_url=profile_picture_url,
            follower_count=follower_count,
            media_count=media_count,
            encrypted_access_token=encrypted_token,
            token_expires_at=expires_at,
            status="connected",
            connected_by_user_id=user.id,
            first_connected_at=datetime.now(timezone.utc),
            collaborator_rate_at_connection=(
                membership.rate_per_connection
                if membership.role == WorkspaceRole.COLLABORATOR.value
                else None
            ),
        )
        db.add(account)
    else:
        account.app_credential_id = credential.id
        account.username = username
        account.profile_picture_url = profile_picture_url
        account.follower_count = follower_count
        account.media_count = media_count
        account.encrypted_access_token = encrypted_token
        account.token_expires_at = expires_at
        account.status = "connected"
        account.connected_at = datetime.now(timezone.utc)
    await db.commit()
    return RedirectResponse(_connection_result_page(return_to, "connected"), status_code=303)


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
        access_token = (
            decrypt_value(account.encrypted_access_token)
            if account.encrypted_access_token is not None
            else None
        )
    except (RuntimeError, ValueError) as exc:
        logger.warning("Instagram token could not be decrypted for revocation (%s).", type(exc).__name__)
        access_token = None
    account.encrypted_access_token = None
    account.status = "disconnected"
    account.app_credential_id = None
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


@router.delete(
    "/accounts/{account_id}/remove",
    response_model=InstagramDisconnectResponse,
    dependencies=[Depends(require_csrf)],
)
async def remove_error_account(
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
    if account.status != "error":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only accounts marked with an error can be removed here.",
        )
    try:
        access_token = (
            decrypt_value(account.encrypted_access_token)
            if account.encrypted_access_token is not None
            else None
        )
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
        logger.warning("Errored Instagram account was removed locally without confirmed Meta revocation.")
    return InstagramDisconnectResponse(meta_revoked=meta_revoked)

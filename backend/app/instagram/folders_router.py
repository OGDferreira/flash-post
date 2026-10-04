import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update

from app.auth.dependencies import DbSession, OwnerAccess, require_csrf
from app.models import InstagramAccount, InstagramProfileFolder
from app.schemas.instagram_folders import (
    InstagramProfileFolderAccount,
    InstagramProfileFolderAccountsRequest,
    InstagramProfileFolderCreateRequest,
    InstagramProfileFolderResponse,
    InstagramProfileFoldersResponse,
    InstagramProfileFolderUpdateRequest,
)

router = APIRouter(prefix="/api/instagram/folders", tags=["Instagram profile folders"])


def _account_response(account: InstagramAccount) -> InstagramProfileFolderAccount:
    return InstagramProfileFolderAccount(
        id=account.id,
        profile_folder_id=account.profile_folder_id,
        username=account.username,
        profile_picture_url=account.profile_picture_url,
        status=account.status,
    )


async def _folder_response(
    folder: InstagramProfileFolder,
    db: DbSession,
) -> InstagramProfileFolderResponse:
    accounts = (
        await db.scalars(
            select(InstagramAccount)
            .where(
                InstagramAccount.workspace_id == folder.workspace_id,
                InstagramAccount.profile_folder_id == folder.id,
            )
            .order_by(InstagramAccount.username)
        )
    ).all()
    created_at = (
        folder.created_at.replace(tzinfo=timezone.utc)
        if folder.created_at.tzinfo is None
        else folder.created_at
    )
    return InstagramProfileFolderResponse(
        id=folder.id,
        name=folder.name,
        color=folder.color,
        created_at=created_at,
        accounts=[_account_response(account) for account in accounts],
    )


async def _workspace_folder(
    workspace_id: uuid.UUID,
    folder_id: uuid.UUID,
    db: DbSession,
) -> InstagramProfileFolder | None:
    return await db.scalar(
        select(InstagramProfileFolder).where(
            InstagramProfileFolder.id == folder_id,
            InstagramProfileFolder.workspace_id == workspace_id,
        )
    )


@router.get("", response_model=InstagramProfileFoldersResponse)
async def list_profile_folders(
    access: OwnerAccess,
    db: DbSession,
) -> InstagramProfileFoldersResponse:
    folders = (
        await db.scalars(
            select(InstagramProfileFolder)
            .where(InstagramProfileFolder.workspace_id == access.workspace.id)
            .order_by(InstagramProfileFolder.name, InstagramProfileFolder.id)
        )
    ).all()
    accounts = (
        await db.scalars(
            select(InstagramAccount)
            .where(InstagramAccount.workspace_id == access.workspace.id)
            .order_by(InstagramAccount.username)
        )
    ).all()
    return InstagramProfileFoldersResponse(
        folders=[await _folder_response(folder, db) for folder in folders],
        accounts=[_account_response(account) for account in accounts],
    )


@router.post(
    "",
    response_model=InstagramProfileFolderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_profile_folder(
    payload: InstagramProfileFolderCreateRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramProfileFolderResponse:
    existing = await db.scalar(
        select(InstagramProfileFolder.id).where(
            InstagramProfileFolder.workspace_id == access.workspace.id,
            InstagramProfileFolder.name == payload.name,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma pasta com esse nome.",
        )
    folder = InstagramProfileFolder(
        workspace_id=access.workspace.id,
        name=payload.name,
        color=payload.color,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return await _folder_response(folder, db)


@router.patch(
    "/{folder_id}",
    response_model=InstagramProfileFolderResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_profile_folder(
    folder_id: uuid.UUID,
    payload: InstagramProfileFolderUpdateRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramProfileFolderResponse:
    folder = await _workspace_folder(access.workspace.id, folder_id, db)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada.")
    duplicate = await db.scalar(
        select(InstagramProfileFolder.id).where(
            InstagramProfileFolder.workspace_id == access.workspace.id,
            InstagramProfileFolder.name == payload.name,
            InstagramProfileFolder.id != folder.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma pasta com esse nome.",
        )
    folder.name = payload.name
    folder.color = payload.color
    await db.commit()
    await db.refresh(folder)
    return await _folder_response(folder, db)


@router.put(
    "/{folder_id}/accounts",
    response_model=InstagramProfileFolderResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_profile_folder_accounts(
    folder_id: uuid.UUID,
    payload: InstagramProfileFolderAccountsRequest,
    access: OwnerAccess,
    db: DbSession,
) -> InstagramProfileFolderResponse:
    folder = await _workspace_folder(access.workspace.id, folder_id, db)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada.")
    valid_account_ids = set(
        (
            await db.scalars(
                select(InstagramAccount.id).where(
                    InstagramAccount.workspace_id == access.workspace.id,
                    InstagramAccount.id.in_(payload.account_ids),
                )
            )
        ).all()
    ) if payload.account_ids else set()
    if valid_account_ids != set(payload.account_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uma ou mais contas não pertencem a este workspace.",
        )
    if payload.account_ids:
        await db.execute(
            update(InstagramAccount)
            .where(
                InstagramAccount.workspace_id == access.workspace.id,
                InstagramAccount.profile_folder_id == folder.id,
            )
            .values(profile_folder_id=None)
        )
        await db.execute(
            update(InstagramAccount)
            .where(
                InstagramAccount.workspace_id == access.workspace.id,
                InstagramAccount.id.in_(payload.account_ids),
            )
            .values(profile_folder_id=folder.id)
        )
    else:
        await db.execute(
            update(InstagramAccount)
            .where(
                InstagramAccount.workspace_id == access.workspace.id,
                InstagramAccount.profile_folder_id == folder.id,
            )
            .values(profile_folder_id=None)
        )
    await db.commit()
    await db.refresh(folder)
    return await _folder_response(folder, db)


@router.delete(
    "/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_profile_folder(
    folder_id: uuid.UUID,
    access: OwnerAccess,
    db: DbSession,
) -> None:
    folder = await _workspace_folder(access.workspace.id, folder_id, db)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada.")
    await db.execute(
        update(InstagramAccount)
        .where(
            InstagramAccount.workspace_id == access.workspace.id,
            InstagramAccount.profile_folder_id == folder.id,
        )
        .values(profile_folder_id=None)
    )
    await db.delete(folder)
    await db.commit()

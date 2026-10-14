"""ZIP extensions: the workspace owner publishes, authorized collaborators download."""

import hashlib
import re
import zipfile
from datetime import datetime
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import undefer

from app.auth.dependencies import DbSession, OwnerAccess, WorkspaceMemberAccess, require_csrf
from app.models import Extension

router = APIRouter(prefix="/api/extensions", tags=["Extensions"])

MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_ENTRIES = 5_000
MAX_EXTENSIONS_PER_WORKSPACE = 50
_ZIP_MAGIC = b"PK\x03\x04"
_ACCEPTED_TYPES = {"application/zip", "application/x-zip-compressed", "application/octet-stream"}


class ExtensionPayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    instructions: str | None = Field(default=None, max_length=8000)
    visible_to_collaborators: bool = True


class ExtensionResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    instructions: str | None
    visible_to_collaborators: bool
    file_name: str | None
    file_size: int | None
    has_file: bool
    created_at: datetime
    updated_at: datetime


def _response(item: Extension) -> ExtensionResponse:
    return ExtensionResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        instructions=item.instructions,
        visible_to_collaborators=item.visible_to_collaborators,
        file_name=item.file_name,
        file_size=item.file_size,
        has_file=item.file_size is not None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def validate_zip(content: bytes) -> None:
    if not content.startswith(_ZIP_MAGIC) or not zipfile.is_zipfile(BytesIO(content)):
        raise HTTPException(status_code=415, detail="O arquivo precisa ser um ZIP válido.")
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if not entries:
                raise HTTPException(status_code=422, detail="O ZIP está vazio.")
            if len(entries) > MAX_ENTRIES:
                raise HTTPException(status_code=422, detail="O ZIP tem arquivos demais.")
            total = 0
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
                    raise HTTPException(status_code=422, detail="O ZIP contém caminhos inválidos.")
                if entry.flag_bits & 0x1:
                    raise HTTPException(status_code=422, detail="ZIP protegido por senha não é aceito.")
                total += entry.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise HTTPException(status_code=422, detail="O conteúdo descompactado é grande demais.")
    except zipfile.BadZipFile:
        raise HTTPException(status_code=415, detail="O arquivo precisa ser um ZIP válido.") from None


def safe_file_name(raw: str | None, fallback: str) -> str:
    base = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or re.sub(r"[^A-Za-z0-9._-]+", "_", fallback)
    base = base[:100].rstrip("._") or "extensao"
    return base if base.lower().endswith(".zip") else f"{base}.zip"


@router.get("", response_model=list[ExtensionResponse])
async def list_extensions(access: WorkspaceMemberAccess, db: DbSession) -> list[ExtensionResponse]:
    query = select(Extension).where(Extension.workspace_id == access.workspace.id)
    if access.membership.role != "OWNER":
        query = query.where(Extension.visible_to_collaborators.is_(True), Extension.file_size.is_not(None))
    items = (await db.scalars(query.order_by(Extension.created_at.desc(), Extension.id))).all()
    return [_response(item) for item in items]


@router.post("", response_model=ExtensionResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_extension(payload: ExtensionPayload, access: OwnerAccess, db: DbSession) -> ExtensionResponse:
    count = await db.scalar(
        select(func.count(Extension.id)).where(
            Extension.workspace_id == access.workspace.id
        )
    )
    if (count or 0) >= MAX_EXTENSIONS_PER_WORKSPACE:
        raise HTTPException(status_code=409, detail="Limite de extensões atingido.")
    item = Extension(
        workspace_id=access.workspace.id,
        created_by_user_id=access.membership.user_id,
        name=" ".join(payload.name.split()),
        description=(payload.description or "").strip() or None,
        instructions=(payload.instructions or "").strip() or None,
        visible_to_collaborators=payload.visible_to_collaborators,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)  # server-side timestamps
    return _response(item)


async def _owned(db: DbSession, access: OwnerAccess, extension_id: UUID) -> Extension:
    item = await db.scalar(
        select(Extension).where(Extension.id == extension_id, Extension.workspace_id == access.workspace.id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Extensão não encontrada.")
    return item


@router.patch("/{extension_id}", response_model=ExtensionResponse, dependencies=[Depends(require_csrf)])
async def update_extension(
    extension_id: UUID, payload: ExtensionPayload, access: OwnerAccess, db: DbSession
) -> ExtensionResponse:
    item = await _owned(db, access, extension_id)
    item.name = " ".join(payload.name.split())
    item.description = (payload.description or "").strip() or None
    item.instructions = (payload.instructions or "").strip() or None
    item.visible_to_collaborators = payload.visible_to_collaborators
    await db.commit()
    await db.refresh(item)
    return _response(item)


@router.put("/{extension_id}/file", response_model=ExtensionResponse, dependencies=[Depends(require_csrf)])
async def upload_extension_file(
    extension_id: UUID, request: Request, access: OwnerAccess, db: DbSession
) -> ExtensionResponse:
    item = await _owned(db, access, extension_id)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in _ACCEPTED_TYPES:
        raise HTTPException(status_code=415, detail="Envie um arquivo ZIP.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="O ZIP deve ter até 25 MB.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_ZIP_BYTES:
            raise HTTPException(status_code=413, detail="O ZIP deve ter até 25 MB.")
        chunks.append(chunk)
    content = b"".join(chunks)
    validate_zip(content)
    item.file_name = safe_file_name(request.headers.get("x-file-name"), item.name)
    item.file_size = len(content)
    item.file_sha256 = hashlib.sha256(content).hexdigest()
    item.file_data = content
    await db.commit()
    await db.refresh(item)
    return _response(item)


@router.get("/{extension_id}/download")
async def download_extension(extension_id: UUID, access: WorkspaceMemberAccess, db: DbSession) -> Response:
    item = await db.scalar(
        select(Extension)
        .options(undefer(Extension.file_data))
        .where(Extension.id == extension_id, Extension.workspace_id == access.workspace.id)
    )
    if item is None or item.file_data is None:
        raise HTTPException(status_code=404, detail="Extensão não encontrada.")
    if access.membership.role != "OWNER" and not item.visible_to_collaborators:
        # Same answer as a missing item: hidden extensions are not discoverable.
        raise HTTPException(status_code=404, detail="Extensão não encontrada.")
    return Response(
        content=item.file_data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{item.file_name or "extensao.zip"}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "X-File-SHA256": item.file_sha256 or "",
        },
    )


@router.delete("/{extension_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_extension(extension_id: UUID, access: OwnerAccess, db: DbSession) -> None:
    item = await _owned(db, access, extension_id)
    await db.delete(item)
    await db.commit()

"""Funnel export/import.

* File: a versioned JSON (``flashpost-funnel`` v1) with the full definition and
  every media file embedded (base64). Group ids, tokens, keys and stats are
  never written; group deliveries come back unset (the importer picks a group).
* Import code: a signed, expiring code that copies the funnel straight from
  storage (no download), for passing a funnel to another authorized user.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.flow_schema import FlowDefinition
from app.core.config import get_settings
from app.models import TgFlow, TgMedia
from app.partners.service import _remap, _uuid_strings, clone_flow

FORMAT = "flashpost-funnel"
VERSION = 1
MAX_EXPORT_BYTES = 60 * 1024 * 1024
CODE_TTL_SECONDS = 7 * 24 * 3600


async def _flow_media(db: AsyncSession, flow: TgFlow) -> list[TgMedia]:
    ids = [uuid.UUID(v) for v in _uuid_strings(flow.definition, set())]
    if not ids:
        return []
    return list(await db.scalars(select(TgMedia).where(TgMedia.id.in_(ids), TgMedia.workspace_id == flow.workspace_id)))


async def export_flow(db: AsyncSession, flow: TgFlow) -> dict:
    from app.bots.engine import load_media_bytes

    medias = await _flow_media(db, flow)
    total = sum(m.size_bytes for m in medias)
    if total > MAX_EXPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"As mídias somam {total // (1024 * 1024)} MB; o limite do arquivo é 60 MB. Use o código de importação.",
        )
    files = []
    for media in medias:
        content = await load_media_bytes(media)
        files.append({
            "id": str(media.id), "kind": media.kind, "file_name": media.file_name,
            "content_type": media.content_type, "data": base64.b64encode(content).decode(),
        })
    return {
        "format": FORMAT, "version": VERSION, "name": flow.name,
        "definition": _remap(flow.definition, {}),  # resets group chat ids
        "media": files,
    }


async def import_flow(db: AsyncSession, data: dict, workspace_id: uuid.UUID) -> TgFlow:
    from app.instagram.storage import SupabaseStorage

    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise HTTPException(status_code=422, detail="Arquivo inválido: não é um funil do Flash.")
    if int(data.get("version") or 0) > VERSION:
        raise HTTPException(status_code=422, detail="Este arquivo é de uma versão mais nova do Flash.")
    ids: dict[str, str] = {}
    uploads = []
    for item in data.get("media") or []:
        try:
            content = base64.b64decode(item["data"], validate=True)
            old_id = str(uuid.UUID(str(item["id"])))
        except (KeyError, ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Arquivo inválido: mídia corrompida.") from None
        new_id = uuid.uuid4()
        safe = "".join(c for c in str(item.get("file_name") or "midia") if c.isalnum() or c in "._-")[:120] or "midia"
        path = f"{workspace_id}/bots/{new_id}/{safe}"
        ids[old_id] = str(new_id)
        uploads.append((path, content, str(item.get("content_type") or "application/octet-stream")))
        db.add(TgMedia(
            id=new_id, workspace_id=workspace_id, kind=str(item.get("kind") or "photo")[:16], file_name=safe,
            content_type=uploads[-1][2][:100], size_bytes=len(content), storage_path=path, file_ids={},
        ))
    definition = _remap(data.get("definition") or {}, ids)
    try:
        FlowDefinition.model_validate(definition)
    except Exception:
        raise HTTPException(status_code=422, detail="Arquivo inválido: o funil não passou na validação.") from None
    storage = SupabaseStorage.from_settings()
    for path, content, content_type in uploads:
        await storage.upload(path, content, content_type)
    flow = TgFlow(workspace_id=workspace_id, name=str(data.get("name") or "Funil importado")[:120], definition=definition)
    db.add(flow)
    await db.flush()
    return flow


# ------------------------------------------------------------------ import codes


def _secret() -> bytes:
    secret = get_settings().session_secret
    if secret is None:
        raise HTTPException(status_code=503, detail="Servidor sem chave de assinatura.")
    return hashlib.sha256(b"funnel-code:" + secret.get_secret_value().encode()).digest()


def make_code(flow_id: uuid.UUID) -> str:
    payload = f"{flow_id.hex}.{int(time.time()) + CODE_TTL_SECONDS}"
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    return base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode().rstrip("=")


def read_code(code: str) -> uuid.UUID:
    try:
        raw = base64.urlsafe_b64decode(code.strip() + "=" * (-len(code.strip()) % 4)).decode()
        flow_hex, expires, signature = raw.split(".")
        expected = hmac.new(_secret(), f"{flow_hex}.{expires}".encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(expected, signature):
            raise ValueError
        if int(expires) < time.time():
            raise HTTPException(status_code=422, detail="Código de importação expirado.")
        return uuid.UUID(flow_hex)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=422, detail="Código de importação inválido.") from None


async def import_from_code(db: AsyncSession, code: str, workspace_id: uuid.UUID) -> TgFlow:
    source = await db.get(TgFlow, read_code(code))
    if source is None:
        raise HTTPException(status_code=404, detail="O funil deste código não existe mais.")
    clone = await clone_flow(db, source, workspace_id)
    clone.template_flow_id = None  # an import is the importer's own funnel
    return clone


def dumps(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode()

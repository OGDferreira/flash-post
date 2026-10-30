"""Useful links (Integrações → Links): a list the Super Admin curates for every user
(groups, support, materials). Stored as one system setting."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, HttpUrl

from app.auth.dependencies import DbSession, SuperAdminUser, WorkspaceMemberAccess, require_csrf
from app.models import SystemSetting

router = APIRouter(prefix="/api/links", tags=["Links"])
LINKS_KEY = "useful_links"


class UsefulLink(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=80)]
    url: HttpUrl
    description: Annotated[str, Field(max_length=200)] = ""


class UsefulLinks(BaseModel):
    links: list[UsefulLink] = Field(default_factory=list, max_length=50)


async def _links(db) -> list[dict]:
    row = await db.get(SystemSetting, LINKS_KEY)
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    links = value.get("links")
    return links if isinstance(links, list) else []


@router.get("")
async def list_links(_access: WorkspaceMemberAccess, db: DbSession) -> dict:
    return {"links": await _links(db)}


@router.put("", dependencies=[Depends(require_csrf)])
async def save_links(payload: UsefulLinks, admin: SuperAdminUser, db: DbSession) -> dict:
    links = [{"title": item.title.strip(), "url": str(item.url), "description": item.description.strip()} for item in payload.links]
    row = await db.get(SystemSetting, LINKS_KEY)
    if row is None:
        db.add(SystemSetting(key=LINKS_KEY, value={"links": links}, updated_by_user_id=admin.id))
    else:
        row.value, row.updated_by_user_id = {"links": links}, admin.id
    await db.commit()
    return {"links": links}

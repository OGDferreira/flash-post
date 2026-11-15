"""ManyChat-style Instagram automations.

A comment (or DM) whose text matches a rule's keywords triggers a public reply
on the comment and/or a direct message to its author. The webhook calls
:func:`process_webhook`; everything here is best-effort and never raises back to
the request so Meta always gets its 200.

Until ``instagram_automation_enabled`` is turned on (it waits on Meta App Review
of the messaging/comment scopes), nothing is sent: a rule that matches is logged
as ``simulated`` so the owner can see what *would* fire.
"""
import logging
import random
import re
from collections.abc import Mapping, Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.crypto import decrypt_value
from app.models import (
    InstagramAccount,
    InstagramAutomationEvent,
    InstagramCommentAutomation,
    SystemSetting,
)

GRAPH_ENDPOINT = "https://graph.instagram.com/v25.0"
# DB toggle so the owner can flip the automations live/off without a redeploy;
# the env flag (instagram_automation_enabled) still forces it on when set.
AUTOMATIONS_ENABLED_KEY = "instagram_automations_enabled"
logger = logging.getLogger(__name__)


async def automations_live(db) -> bool:
    """True when real sending is on, from the env flag or the DB toggle."""
    if get_settings().instagram_automation_enabled:
        return True
    row = await db.get(SystemSetting, AUTOMATIONS_ENABLED_KEY)
    return bool(row and isinstance(row.value, dict) and row.value.get("enabled"))


# ----------------------------------------------------------------- matching


def _normalize(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


def matches(rule: InstagramCommentAutomation, text: str) -> bool:
    """True when ``text`` triggers the rule. Empty keyword list matches anything."""
    keywords = [kw for kw in (rule.keywords or []) if isinstance(kw, str) and kw.strip()]
    if not keywords:
        return True
    body = _normalize(text)
    if rule.match_mode == "exact":
        return any(body == _normalize(kw) for kw in keywords)
    return any(_normalize(kw) in body for kw in keywords)


_SPINTAX = re.compile(r"\{([^{}]*)\}")


def expand_spintax(text: str, *, _depth: int = 0) -> str:
    """Resolve ``{oi|olá|opa}`` groups to one random option, nesting allowed.

    Lets the owner write one message that reads differently every fire, so the
    Direct/reply doesn't look like a bot. A lone ``{}`` or ``{a}`` passes through."""
    if not text or "{" not in text or _depth > 8:
        return text or ""

    def pick(match: "re.Match[str]") -> str:
        return random.choice(match.group(1).split("|"))

    expanded = _SPINTAX.sub(pick, text)
    return expand_spintax(expanded, _depth=_depth + 1) if expanded != text else expanded


def _rule_targets_account(rule: InstagramCommentAutomation, account: InstagramAccount) -> bool:
    """True when ``rule`` is scoped to ``account`` (by folder, by account, or
    globally when it carries no scope)."""
    accounts = [str(a) for a in (rule.scope_account_ids or []) if a]
    folders = [str(f) for f in (rule.scope_folder_ids or []) if f]
    if not accounts and not folders:
        # No explicit scope: fall back to the legacy single-account column.
        return rule.instagram_account_id in (None, account.id)
    if str(account.id) in accounts:
        return True
    return account.profile_folder_id is not None and str(account.profile_folder_id) in folders


# ----------------------------------------------------------------- Graph calls


async def _post(client: httpx.AsyncClient, path: str, data: dict) -> None:
    response = await client.post(f"{GRAPH_ENDPOINT}/{path}", data=data)
    response.raise_for_status()


def _pick_dm_text(rule: InstagramCommentAutomation) -> str:
    """One DM variation (rotated), with spintax expanded. Falls back to dm_text."""
    variations = [t for t in (rule.dm_texts or []) if isinstance(t, str) and t.strip()]
    chosen = random.choice(variations) if variations else (rule.dm_text or "")
    return expand_spintax(chosen)


def _dm_message(rule: InstagramCommentAutomation, text: str | None = None) -> dict:
    """The messages-API ``message`` object: plain text, or a button template when
    the rule carries link buttons."""
    text = _pick_dm_text(rule) if text is None else text
    buttons = [
        {"type": "web_url", "url": b["url"], "title": b["label"][:20]}
        for b in (rule.dm_buttons or [])
        if isinstance(b, Mapping) and b.get("url") and b.get("label")
    ][:3]
    if buttons:
        return {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": (text or "👇")[:640],
                    "buttons": buttons,
                },
            }
        }
    return {"text": text[:1000]}


async def _send_comment_actions(
    ig_user_id: str, access_token: str, rule: InstagramCommentAutomation, comment_id: str
) -> None:
    """Public reply on the comment and/or a private DM to its author."""
    import json

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        if rule.public_reply_enabled and rule.public_replies:
            reply = expand_spintax(
                random.choice([r for r in rule.public_replies if isinstance(r, str) and r.strip()] or [""])
            )
            if reply.strip():
                await _post(client, f"{comment_id}/replies", {"message": reply[:900], "access_token": access_token})
        if rule.dm_enabled and (rule.dm_text or rule.dm_texts or rule.dm_buttons):
            await _post(
                client,
                f"{ig_user_id}/messages",
                {
                    "recipient": json.dumps({"comment_id": comment_id}),
                    "message": json.dumps(_dm_message(rule)),
                    "access_token": access_token,
                },
            )


async def _send_dm_reply(
    ig_user_id: str, access_token: str, rule: InstagramCommentAutomation, recipient_id: str
) -> None:
    import json

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        await _post(
            client,
            f"{ig_user_id}/messages",
            {
                "recipient": json.dumps({"id": recipient_id}),
                "message": json.dumps(_dm_message(rule)),
                "access_token": access_token,
            },
        )


# ----------------------------------------------------------------- firing


async def _claim_event(db, automation_id, object_id: str):
    """Reserve (automation, object) so a webhook retry never double-fires. Returns
    the new event row, or ``False`` when it was already handled. Uses a savepoint so
    a duplicate rolls back only this claim, never earlier fires in the same entry."""
    event = InstagramAutomationEvent(
        automation_id=automation_id, object_id=object_id[:191], status="skipped"
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        return False
    return event


async def _fire(
    db, account: InstagramAccount, rule: InstagramCommentAutomation, *, object_id: str, kind: str, author_id: str | None
) -> bool:
    """Run one matched rule. Returns True when it was the rule that handled the object."""
    event = await _claim_event(db, rule.id, object_id)
    if event is False:
        return True  # already handled by a previous delivery of this webhook

    if not await automations_live(db):
        event.status = "simulated"
        event.detail = "Automação desligada; nada foi enviado."
        await _bump(db, rule)
        return True

    token = None
    if account.encrypted_access_token is not None:
        try:
            token = decrypt_value(account.encrypted_access_token)
        except (RuntimeError, ValueError):
            token = None
    if token is None:
        event.status = "failed"
        event.detail = "Sem token válido para a conta."
        return True

    try:
        if kind == "comment":
            await _send_comment_actions(str(account.instagram_user_id), token, rule, object_id)
        elif author_id:
            await _send_dm_reply(str(account.instagram_user_id), token, rule, author_id)
        event.status = "sent"
        await _bump(db, rule)
    except httpx.HTTPError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        event.status = "failed"
        event.detail = f"Instagram recusou (HTTP {status_code})." if status_code else "Falha de rede ao enviar."
        logger.warning("Instagram automation %s failed for %s: %s", rule.id, object_id, event.detail)
    return True


async def _bump(db, rule: InstagramCommentAutomation) -> None:
    from sqlalchemy import func, update

    await db.execute(
        update(InstagramCommentAutomation)
        .where(InstagramCommentAutomation.id == rule.id)
        .values(fired_count=InstagramCommentAutomation.fired_count + 1, last_fired_at=func.now())
    )


async def _rules_for(db, account: InstagramAccount, trigger_type: str) -> Sequence[InstagramCommentAutomation]:
    # Scope lives in JSON (folders/accounts), so fetch the workspace's rules and
    # filter per account in Python. Rule counts per workspace stay small.
    rows = await db.scalars(
        select(InstagramCommentAutomation)
        .where(
            InstagramCommentAutomation.workspace_id == account.workspace_id,
            InstagramCommentAutomation.enabled.is_(True),
            InstagramCommentAutomation.trigger_type == trigger_type,
        )
        .order_by(InstagramCommentAutomation.created_at.asc())
    )
    return [rule for rule in rows if _rule_targets_account(rule, account)]


# ----------------------------------------------------------------- webhook entry


async def _account_for(db, ig_user_id: str) -> InstagramAccount | None:
    return await db.scalar(
        select(InstagramAccount).where(InstagramAccount.instagram_user_id == str(ig_user_id))
    )


async def _handle_comment(db, account: InstagramAccount, value: Mapping) -> None:
    comment_id = value.get("id")
    text = value.get("text")
    from_user = value.get("from") if isinstance(value.get("from"), Mapping) else {}
    author_id = str(from_user.get("id")) if from_user.get("id") is not None else None
    media = value.get("media") if isinstance(value.get("media"), Mapping) else {}
    media_id = str(media.get("id")) if media.get("id") is not None else None
    if not comment_id:
        return
    # Never answer the account's own comments (our public replies arrive as comments too).
    if author_id and author_id == str(account.instagram_user_id):
        return
    for rule in await _rules_for(db, account, "comment"):
        if rule.media_id and media_id and rule.media_id != media_id:
            continue
        if matches(rule, text or ""):
            if await _fire(db, account, rule, object_id=str(comment_id), kind="comment", author_id=author_id):
                break


async def _handle_message(db, account: InstagramAccount, event: Mapping) -> None:
    sender = event.get("sender") if isinstance(event.get("sender"), Mapping) else {}
    sender_id = str(sender.get("id")) if sender.get("id") is not None else None
    message = event.get("message") if isinstance(event.get("message"), Mapping) else {}
    if message.get("is_echo") or not sender_id:
        return
    if sender_id == str(account.instagram_user_id):
        return
    mid = str(message.get("mid") or event.get("timestamp") or "")
    text = message.get("text")
    if not mid:
        return
    for rule in await _rules_for(db, account, "dm"):
        if matches(rule, text or ""):
            if await _fire(db, account, rule, object_id=mid, kind="dm", author_id=sender_id):
                break


async def process_webhook(db, payload: Mapping) -> int:
    """Route a verified Instagram webhook to the automation engine. Returns the
    number of entries handled. Swallows per-entry errors so the webhook still 200s."""
    handled = 0
    for entry in payload.get("entry", []):
        if not isinstance(entry, Mapping):
            continue
        account = await _account_for(db, entry.get("id"))
        if account is None:
            continue
        try:
            for change in entry.get("changes", []) or []:
                if isinstance(change, Mapping) and change.get("field") == "comments":
                    value = change.get("value")
                    if isinstance(value, Mapping):
                        await _handle_comment(db, account, value)
            for messaging in entry.get("messaging", []) or []:
                if isinstance(messaging, Mapping):
                    await _handle_message(db, account, messaging)
            await db.commit()
            handled += 1
        except Exception:  # noqa: BLE001 - never fail the webhook
            await db.rollback()
            logger.exception("Instagram automation failed for entry %s", entry.get("id"))
    return handled

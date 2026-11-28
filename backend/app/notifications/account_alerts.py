"""Owner alerts when a connected Instagram/Meta account goes offline.

The worker already detects an expired/revoked token, isolates the account (removing it
from its loops so nothing more is sent on it) and logs a health event. This adds the
owner-facing notice: an in-app notification + web push, and a Telegram DM when the owner
has configured one. Every channel is best-effort — a notification failure must never break
the worker's transaction.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import InstagramAccount, TgBot, Workspace

logger = logging.getLogger(__name__)


def _reconnect_path(account_id: UUID) -> str:
    return f"/feature/accounts?reconnect={account_id}"


async def notify_account_disconnected(
    db: AsyncSession, account: InstagramAccount, reason: str
) -> None:
    """In-app + web push to the owner, plus a Telegram DM if configured. Caller commits."""
    workspace = await db.get(Workspace, account.workspace_id)
    if workspace is None:
        return

    title = "Conta desconectada"
    body = (
        f"@{account.username} parou de publicar (token expirado ou revogado). "
        "Toque para reconectar."
    )
    path = _reconnect_path(account.id)

    # In-app notice + best-effort web push (reuses the proven partner notifier).
    try:
        from app.partners.service import notify_user

        await notify_user(db, workspace.owner_id, "account_disconnected", title, body, path)
    except Exception:
        logger.exception("Account-disconnected in-app notice failed for %s.", account.id)

    # Telegram DM, only when the owner set it up.
    await _send_telegram_alert(db, workspace, account, reason)


async def _send_telegram_alert(
    db: AsyncSession,
    workspace: Workspace,
    account: InstagramAccount,
    reason: str,
) -> None:
    chat_id = workspace.alerts_telegram_chat_id
    if not chat_id:
        return
    try:
        bot = await _alert_bot(db, workspace)
        if bot is None:
            return
        from app.bots.telegram import TelegramClient, translate_target
        from app.core.crypto import decrypt_value

        token = decrypt_value(bot.encrypted_token)
        base = get_settings().public_base_url.rstrip("/")
        text = (
            f"⚠️ <b>Conta desconectada</b>\n\n"
            f"A conta <b>@{account.username}</b> saiu do ar e parou de publicar.\n"
            f"Motivo: {reason[:200]}\n\n"
            f"Reconecte para voltar a postar."
        )
        reply_markup = {
            "inline_keyboard": [[{"text": "Reconectar conta", "url": f"{base}{_reconnect_path(account.id)}"}]]
        }
        # Never translate this operational alert to a lead's language.
        token_reset = translate_target.set(None)
        try:
            await TelegramClient(token).send_message(int(chat_id), text, reply_markup=reply_markup)
        finally:
            translate_target.reset(token_reset)
    except Exception:
        logger.exception("Account-disconnected Telegram alert failed for %s.", account.id)


async def _alert_bot(db: AsyncSession, workspace: Workspace) -> TgBot | None:
    """The bot that sends alerts: the chosen one, else any active bot of the workspace."""
    if workspace.alerts_telegram_bot_id:
        bot = await db.get(TgBot, workspace.alerts_telegram_bot_id)
        if bot is not None and bot.workspace_id == workspace.id:
            return bot
    return await db.scalar(
        select(TgBot)
        .where(TgBot.workspace_id == workspace.id, TgBot.is_active.is_(True))
        .order_by(TgBot.created_at)
        .limit(1)
    )

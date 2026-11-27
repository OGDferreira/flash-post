"""Transactional email via Hostinger SMTP (noreply@flashpost.tech)."""

import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailNotConfigured(RuntimeError):
    pass


def _is_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_user and s.smtp_password)


def _send_sync(to: str, subject: str, html: str, text: str) -> None:
    s = get_settings()
    if not s.smtp_user or not s.smtp_password:
        raise EmailNotConfigured("SMTP_USER and SMTP_PASSWORD must be configured.")
    from_addr = f"{s.smtp_from_name} <{s.smtp_user}>"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ctx) as conn:
        conn.login(s.smtp_user, s.smtp_password.get_secret_value())
        conn.sendmail(s.smtp_user, to, msg.as_bytes())


async def send_email(to: str, subject: str, html: str, text: str) -> None:
    """Send a transactional email. Raises EmailNotConfigured if SMTP is not set up."""
    await asyncio.to_thread(_send_sync, to, subject, html, text)


async def send_verification_email(to: str, full_name: str, token: str) -> None:
    settings = get_settings()
    base_url = settings.public_base_url.rstrip("/")
    link = f"{base_url}/verificar-email?token={token}"
    subject = "Confirme seu e-mail — FlashPost"
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;color:#1a1a1a;background:#fff;margin:0;padding:32px 16px">
  <div style="max-width:520px;margin:0 auto">
    <h2 style="font-size:20px;font-weight:600;margin:0 0 16px">Bem-vindo(a) ao FlashPost, {full_name.split()[0]}!</h2>
    <p style="margin:0 0 24px;color:#444;line-height:1.6">
      Clique no botão abaixo para confirmar seu e-mail e ativar sua conta.
      O link expira em 24 horas.
    </p>
    <a href="{link}" style="display:inline-block;background:#6c63ff;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:600">
      Confirmar e-mail
    </a>
    <p style="margin:24px 0 0;font-size:12px;color:#888">
      Se você não criou esta conta, ignore este e-mail.<br>
      Ou copie e cole o link: <a href="{link}" style="color:#6c63ff">{link}</a>
    </p>
  </div>
</body>
</html>"""
    text = (
        f"Olá {full_name.split()[0]},\n\n"
        f"Confirme seu e-mail acessando o link:\n{link}\n\n"
        "O link expira em 24 horas.\n\n"
        "Se você não criou esta conta, ignore este e-mail."
    )
    await send_email(to, subject, html, text)


async def send_password_reset_email(to: str, full_name: str, token: str) -> None:
    settings = get_settings()
    base_url = settings.public_base_url.rstrip("/")
    link = f"{base_url}/redefinir-senha?token={token}"
    subject = "Redefinição de senha — FlashPost"
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;color:#1a1a1a;background:#fff;margin:0;padding:32px 16px">
  <div style="max-width:520px;margin:0 auto">
    <h2 style="font-size:20px;font-weight:600;margin:0 0 16px">Redefinir sua senha</h2>
    <p style="margin:0 0 24px;color:#444;line-height:1.6">
      Recebemos um pedido para redefinir a senha da conta associada a este e-mail.
      Clique no botão abaixo. O link expira em 1 hora.
    </p>
    <a href="{link}" style="display:inline-block;background:#6c63ff;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:600">
      Redefinir senha
    </a>
    <p style="margin:24px 0 0;font-size:12px;color:#888">
      Se você não solicitou a redefinição, ignore este e-mail — sua senha permanece a mesma.<br>
      Ou copie e cole o link: <a href="{link}" style="color:#6c63ff">{link}</a>
    </p>
  </div>
</body>
</html>"""
    text = (
        f"Olá {full_name.split()[0]},\n\n"
        f"Para redefinir sua senha, acesse:\n{link}\n\n"
        "O link expira em 1 hora.\n\n"
        "Se você não solicitou a redefinição, ignore este e-mail."
    )
    await send_email(to, subject, html, text)

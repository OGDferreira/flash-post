"""Remove credentials from free-form text before it is logged or persisted.

httpx error messages embed the full request URL, and the Graph API calls send
``access_token`` (and, during OAuth, ``client_secret``/``code``) as query
parameters. Diagnostics events are readable by every workspace member, so any
exception text must pass through :func:`redact_secrets` first.
"""

import re

_SENSITIVE_PARAMS = (
    "access_token",
    "input_token",
    "client_secret",
    "app_secret",
    "fb_exchange_token",
    "code",
    "refresh_token",
    "password",
    "token",
)
_QUERY_PARAM_PATTERN = re.compile(
    r"(?i)([?&;\s\"']|^)(" + "|".join(_SENSITIVE_PARAMS) + r")=([^&\s\"'<>]+)"
)
_JSON_FIELD_PATTERN = re.compile(
    r"(?i)([\"'](?:" + "|".join(_SENSITIVE_PARAMS) + r")[\"']\s*:\s*[\"'])([^\"']+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[a-z0-9._\-~+/=]{8,}")
# Instagram/Facebook user tokens ("IGAA…", "IGQV…", "EAA…") outside a key=value pair.
_META_TOKEN_PATTERN = re.compile(r"\b(?:IGAA|IGQV|EAA)[A-Za-z0-9_\-]{20,}")
# Sharkbot/Smokepay webhook path secrets.
_WEBHOOK_PATH_PATTERN = re.compile(
    r"(/api/(?:sharkbot/webhook|webhooks/smokepay/[0-9a-fA-F-]{36}))/[A-Za-z0-9_\-]{16,}"
)


def redact_secrets(value: str | None) -> str | None:
    if not value:
        return value
    redacted = _QUERY_PARAM_PATTERN.sub(r"\1\2=[redacted]", value)
    redacted = _JSON_FIELD_PATTERN.sub(r"\1[redacted]", redacted)
    redacted = _BEARER_PATTERN.sub(r"\1[redacted]", redacted)
    redacted = _META_TOKEN_PATTERN.sub("[redacted-token]", redacted)
    redacted = _WEBHOOK_PATH_PATTERN.sub(r"\1/[redacted]", redacted)
    return redacted


def install_log_redaction() -> None:
    """Redact secrets from every log record, including formatted tracebacks."""
    import logging
    import traceback

    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, "_flashpost_redacting", False):
        return

    def factory(*args, **kwargs):
        record = current_factory(*args, **kwargs)
        # Keep the args tuple shape: uvicorn's access formatter unpacks it.
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_secrets(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        if record.exc_info and record.exc_info[0] is not None:
            record.exc_text = redact_secrets(
                "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
            )
        return record

    factory._flashpost_redacting = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


def install_app_logging() -> None:
    """Show the app's own INFO lines (publications done, scheduler summaries) in the
    server log. Without a handler only WARNING and above reached the output."""
    import logging
    import sys

    app_logger = logging.getLogger("app")
    if any(getattr(handler, "_flashpost", False) for handler in app_logger.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    handler._flashpost = True  # type: ignore[attr-defined]
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False

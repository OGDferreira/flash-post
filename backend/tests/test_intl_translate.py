from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.bots import http, translate
from app.bots.flow_schema import FlowDefinition, International
from app.core.config import get_settings


def test_international_requires_currency_or_translate() -> None:
    with pytest.raises(ValidationError):
        International(enabled=True)
    assert International(enabled=True, currencies=["USD"]).usd_rate == Decimal("5.00")
    assert International(enabled=True, translate=True).enabled is True
    assert International().enabled is False  # default off, no funnel breaks


def test_fixed_usd_pricing_requires_per_plan_price() -> None:
    base = {
        "plans": [{"id": "vip", "name": "VIP", "price": "20.00",
                   "delivery": {"type": "group", "group_chat_id": -100}}],
        "international": {"enabled": True, "currencies": ["USD"], "pricing": "fixed"},
    }
    with pytest.raises(ValidationError):
        FlowDefinition.model_validate(base)
    base["plans"][0]["price_usd"] = "4.00"
    ok = FlowDefinition.model_validate(base)
    assert ok.plans[0].price_usd == Decimal("4.00")


def test_lang_of_maps_telegram_code() -> None:
    assert translate.lang_of("en-US") == "en"
    assert translate.lang_of("es") == "es"
    assert translate.lang_of("xx") is None
    assert translate.lang_of(None) is None


@pytest.mark.anyio
async def test_translate_off_returns_original(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "libretranslate_url", "")
    assert await translate.translate("Oi {nome}", "en") == "Oi {nome}"


@pytest.mark.anyio
async def test_translate_calls_libretranslate(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "libretranslate_url", "http://libretranslate:5000")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/translate"
        return httpx.Response(200, json={"translatedText": "Hi"})

    http.set_transport(httpx.MockTransport(handler))
    try:
        assert await translate.translate("Oi", "en") == "Hi"
        # Same source/target is a no-op (no call needed).
        assert await translate.translate("Oi", "pt") == "Oi"
    finally:
        http.set_transport(None)


@pytest.mark.anyio
async def test_translate_falls_back_on_error(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "libretranslate_url", "http://libretranslate:5000")
    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(500, json={})))
    try:
        assert await translate.translate("Oi", "en") == "Oi"
    finally:
        http.set_transport(None)

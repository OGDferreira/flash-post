"""The editable flow: every text, media, price and delivery the bot uses.

Stored as JSON in ``TgFlow.definition`` and validated here on save. Phase 1
covers +18 gate, welcome sequence, offer, plans, PIX copy and deliveries; later
phases add upsell/downsell/order bump/remarketing as new optional keys.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Text = Annotated[str, Field(max_length=4000)]
Caption = Annotated[str, Field(max_length=1000)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


BlockType = Literal["text", "photo", "video", "voice", "video_note", "album"]


class Block(_Model):
    """One message of a sequence. Media blocks reference uploaded TgMedia ids."""

    type: BlockType
    text: Caption | None = None
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    spoiler: bool = False  # Telegram's blurred "spoiler" media
    delay_seconds: Annotated[int, Field(ge=0, le=86400)] = 0  # wait before sending this block

    @model_validator(mode="after")
    def _check(self) -> "Block":
        if self.type == "text":
            if not (self.text or "").strip():
                raise ValueError("Bloco de texto precisa de texto.")
            if self.media_ids:
                raise ValueError("Bloco de texto não leva mídia.")
        elif self.type == "album":
            if not 2 <= len(self.media_ids) <= 10:
                raise ValueError("Álbum precisa de 2 a 10 mídias.")
        elif len(self.media_ids) != 1:
            raise ValueError("Este bloco precisa de exatamente uma mídia.")
        if self.type in ("voice", "video_note") and self.text:
            raise ValueError("Áudio de voz e vídeo redondo não têm legenda; use um bloco de texto.")
        return self


class LinkButton(_Model):
    label: Annotated[str, Field(min_length=1, max_length=64)]
    url: HttpUrl


class Delivery(_Model):
    """What the buyer receives after paying."""

    type: Literal["group", "pack", "default"]
    group_chat_id: int | None = None  # group/channel where the bot is admin
    text: Caption | None = None
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    link: LinkButton | None = None
    join_button_label: Annotated[str, Field(max_length=64)] = "🔓 Entrar no VIP"

    @model_validator(mode="after")
    def _check(self) -> "Delivery":
        if self.type == "group" and self.group_chat_id is None:
            raise ValueError("Escolha o grupo/canal da entrega.")
        if self.type == "pack" and not self.media_ids:
            raise ValueError("O pack precisa de pelo menos uma mídia.")
        if self.type == "default" and not (self.text or self.media_ids or self.link):
            raise ValueError("A entrega padrão precisa de mensagem, mídia ou link.")
        return self


class Plan(_Model):
    id: Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")]
    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Annotated[Decimal, Field(ge=Decimal("1.00"), le=Decimal("100000"), decimal_places=2)]
    # None = lifetime access.
    duration_days: Annotated[int, Field(ge=1, le=3650)] | None = 30
    button_text: Annotated[str, Field(max_length=64)] | None = None
    delivery: Delivery | None = None  # None = flow's default_delivery


class AgeGate(_Model):
    enabled: bool = False
    text: Text = "Este conteúdo é só para maiores de 18 anos. Confirme sua idade para continuar."
    button: Annotated[str, Field(max_length=64)] = "✅ Tenho 18 anos ou mais"


class Offer(_Model):
    text: Text = "Escolha seu plano 👇"
    media_id: uuid.UUID | None = None


class Payment(_Model):
    expiration_minutes: Annotated[int, Field(ge=5, le=1440)] = 30
    pix_text: Text = (
        "Pix gerado para <b>{plano}</b> no valor de <b>{valor}</b>.\n"
        "Copie o código abaixo e pague no app do seu banco. A liberação é automática."
    )
    copy_button: Annotated[str, Field(max_length=64)] = "📋 Copiar código Pix"
    check_button: Annotated[str, Field(max_length=64)] = "✅ Já paguei"
    pending_text: Annotated[str, Field(max_length=200)] = "Ainda não identificamos seu pagamento. Aguarde alguns segundos."
    approved_text: Text = "Pagamento aprovado! 🎉 Obrigado, {nome}."
    expired_text: Text = "Seu Pix expirou. Toque abaixo para gerar um novo."


class FlowDefinition(_Model):
    version: Literal[1] = 1
    age_gate: AgeGate = Field(default_factory=AgeGate)
    welcome: list[Block] = Field(default_factory=list, max_length=30)
    offer: Offer = Field(default_factory=Offer)
    plans: list[Plan] = Field(default_factory=list, max_length=10)
    payment: Payment = Field(default_factory=Payment)
    default_delivery: Delivery | None = None

    @model_validator(mode="after")
    def _check(self) -> "FlowDefinition":
        ids = [plan.id for plan in self.plans]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada plano precisa de um id diferente.")
        for plan in self.plans:
            if plan.delivery is None and self.default_delivery is None:
                raise ValueError(f"O plano '{plan.name}' não tem entrega e o fluxo não tem entrega padrão.")
        return self

    def media_ids(self) -> set[uuid.UUID]:
        found: set[uuid.UUID] = set()
        for block in self.welcome:
            found.update(block.media_ids)
        if self.offer.media_id:
            found.add(self.offer.media_id)
        deliveries = [p.delivery for p in self.plans] + [self.default_delivery]
        for delivery in deliveries:
            if delivery:
                found.update(delivery.media_ids)
        return found

    def plan(self, plan_id: str) -> Plan | None:
        return next((p for p in self.plans if p.id == plan_id), None)


def default_flow() -> FlowDefinition:
    return FlowDefinition(
        welcome=[Block(type="text", text="Oi, {nome}! 💕 Que bom te ver por aqui.")],
        plans=[],
    )

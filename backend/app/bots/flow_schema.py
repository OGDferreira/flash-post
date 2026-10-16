"""The editable flow: every text, media, price, button and delivery the bot uses.

Stored as JSON in ``TgFlow.definition`` and validated here on save. Every key
added after phase 1 is optional with a default, so flows saved earlier keep
validating unchanged.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Text = Annotated[str, Field(max_length=4000)]
Caption = Annotated[str, Field(max_length=1000)]
Label = Annotated[str, Field(max_length=64)]
Money = Annotated[Decimal, Field(ge=Decimal("1.00"), le=Decimal("100000"), decimal_places=2)]
Delay = Annotated[int, Field(ge=0, le=43200)]  # minutes, up to 30 days
# Telegram colors inline buttons by style (newer apps; older ones show the default look).
ButtonStyle = Literal["default", "primary", "success", "danger"]
MediaList3 = Annotated[list[uuid.UUID], Field(default_factory=list, max_length=3)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


BlockType = Literal["text", "photo", "video", "voice", "video_note", "album"]


class Block(_Model):
    """One message of the pre-offer sequence. Media blocks reference uploaded TgMedia ids."""

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

    # "upsell": nothing to hand over, the purchase just starts the upsell sequence.
    type: Literal["group", "pack", "default", "upsell"]
    group_chat_id: int | None = None  # group/channel where the bot is admin
    text: Caption | None = None
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    link: LinkButton | None = None
    join_button_label: Label = "🔓 Entrar no VIP"
    start_upsell: bool = True  # after delivering, send the flow's upsell sequence

    @model_validator(mode="after")
    def _check(self) -> "Delivery":
        if self.type == "group" and self.group_chat_id is None:
            raise ValueError("Escolha o grupo/canal da entrega.")
        if self.type == "pack" and not self.media_ids:
            raise ValueError("O pack precisa de pelo menos uma mídia.")
        if self.type == "default" and not (self.text or self.media_ids or self.link):
            raise ValueError("A entrega padrão precisa de mensagem, mídia ou link.")
        return self


class OrderBump(_Model):
    """Extra offered before the PIX ("Adicionar X por +R$ Y?"); one PIX for the total."""

    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Money
    text: Text = "Quer adicionar <b>{bump}</b> por apenas <b>+{bump_valor}</b>?"
    media_ids: MediaList3
    accept_label: Label = "✅ Sim, quero!"
    decline_label: Label = "Não, obrigado"
    delivery: Delivery


class Plan(_Model):
    id: Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")]
    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Money
    # None = lifetime access.
    duration_days: Annotated[int, Field(ge=1, le=3650)] | None = 30
    button_text: Label | None = None
    button_style: ButtonStyle = "default"
    delivery: Delivery | None = None  # None = flow's default_delivery
    # Order bump: "default" uses the flow's, "custom" uses order_bump, "off" skips it.
    bump_mode: Literal["default", "custom", "off"] = "default"
    order_bump: OrderBump | None = None

    @model_validator(mode="after")
    def _check(self) -> "Plan":
        if self.bump_mode == "custom" and self.order_bump is None:
            raise ValueError(f"Configure o order bump personalizado do plano '{self.name}'.")
        return self


class AgeGate(_Model):
    enabled: bool = False
    text: Text = "Este conteúdo é só para maiores de 18 anos. Confirme sua idade para continuar."
    button: Label = "✅ Tenho 18 anos ou mais"


class Offer(_Model):
    """The welcome screen: up to 3 media sent first, then the message with the buttons."""

    text: Text = "Escolha seu plano 👇"
    media_id: uuid.UUID | None = None  # phase 1 single media; folded into media_ids
    media_ids: MediaList3
    spoiler: bool = False
    # Separate message that carries the buttons (the welcome text goes alone above it).
    secondary_enabled: bool = False
    secondary_text: Text = "Escolha seu plano abaixo 👇"
    # One call-to-action button instead of the plan list; tapping it shows the plans.
    cta_enabled: bool = False
    cta_label: Label = "🔥 Ver planos"
    cta_style: ButtonStyle = "success"
    plans_text: Text = "Escolha seu plano 👇"
    redirect_buttons: list[LinkButton] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _fold_media(self) -> "Offer":
        if self.media_id and self.media_id not in self.media_ids:
            self.media_ids = [self.media_id, *self.media_ids][:3]
        self.media_id = None
        return self


class UpsellStep(_Model):
    """Offer sent after a purchase; declining (or buying) moves on to the next step.
    With ``hide_decline`` there is no "no" button: the next step follows on its own delay."""

    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Money
    duration_days: Annotated[int, Field(ge=1, le=3650)] | None = None
    delay_minutes: Delay = 0
    media_ids: MediaList3
    spoiler: bool = False
    text: Text
    accept_label: Label = "✅ Quero aproveitar"
    accept_style: ButtonStyle = "success"
    decline_label: Label = "Não, obrigado"
    hide_decline: bool = False
    delivery: Delivery | None = None  # None = flow's default_delivery


class CustomOffer(_Model):
    """A plan that exists only inside one downsell step."""

    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Money
    duration_days: Annotated[int, Field(ge=1, le=3650)] | None = 30
    delivery: Delivery | None = None  # None = flow's default_delivery


class DownsellStep(_Model):
    """Discounted plans for leads who did not pay; stops as soon as they pay."""

    delay_minutes: Annotated[int, Field(ge=1, le=43200)] = 30
    media_ids: MediaList3
    spoiler: bool = False
    text: Text
    discount_type: Literal["percent", "fixed"] = "percent"
    discount_value: Annotated[Decimal, Field(gt=0, le=Decimal("100000"), decimal_places=2)] = Decimal("10")
    plan_ids: list[str] = Field(default_factory=list, max_length=10)  # empty = every plan
    custom_offer: CustomOffer | None = None  # replaces the discounted plans when set
    button_style: ButtonStyle = "success"

    @model_validator(mode="after")
    def _check(self) -> "DownsellStep":
        if self.discount_type == "percent" and self.discount_value >= 100:
            raise ValueError("O desconto em % do downsell precisa ser menor que 100.")
        return self


class Payment(_Model):
    expiration_minutes: Annotated[int, Field(ge=5, le=1440)] = 30
    pix_text: Text = (
        "Pix gerado para <b>{plano}</b> no valor de <b>{valor}</b>.\n"
        "Copie o código abaixo e pague no app do seu banco. A liberação é automática."
    )
    copy_button: Label = "📋 Copiar código Pix"
    check_button: Label = "✅ Já paguei"
    pending_text: Annotated[str, Field(max_length=200)] = "Ainda não identificamos seu pagamento. Aguarde alguns segundos."
    approved_text: Text = "Pagamento aprovado! 🎉 Obrigado, {nome}."
    expired_text: Text = "Seu Pix expirou. Toque abaixo para gerar um novo."


class FlowDefinition(_Model):
    version: Literal[1] = 1
    age_gate: AgeGate = Field(default_factory=AgeGate)
    welcome: list[Block] = Field(default_factory=list, max_length=30)  # optional pre-offer sequence
    offer: Offer = Field(default_factory=Offer)
    plans: list[Plan] = Field(default_factory=list, max_length=10)
    payment: Payment = Field(default_factory=Payment)
    default_delivery: Delivery | None = None
    order_bump: OrderBump | None = None  # flow default, used by plans in "default" bump mode
    upsells: list[UpsellStep] = Field(default_factory=list, max_length=20)
    downsell_trigger: Literal["pix", "start"] = "pix"  # phase 2; folded into downsell_audience
    # "no_pix": started and never generated a PIX; "pix": generated a PIX and did not pay.
    downsell_audience: list[Literal["no_pix", "pix"]] | None = None
    downsells: list[DownsellStep] = Field(default_factory=list, max_length=20)
    support_username: Annotated[str, Field(max_length=33, pattern=r"^@?[A-Za-z0-9_]{0,32}$")] | None = None

    @model_validator(mode="after")
    def _check(self) -> "FlowDefinition":
        ids = [plan.id for plan in self.plans]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada plano precisa de um id diferente.")
        for plan in self.plans:
            if plan.delivery is None and self.default_delivery is None:
                raise ValueError(f"O plano '{plan.name}' não tem entrega e o fluxo não tem entrega padrão.")
        known = set(ids)
        for index, step in enumerate(self.downsells, start=1):
            if any(plan_id not in known for plan_id in step.plan_ids):
                raise ValueError(f"O downsell {index} usa um plano que não existe mais.")
        if self.support_username:
            self.support_username = self.support_username.lstrip("@") or None
        if self.downsell_audience is None:
            self.downsell_audience = ["pix"] if self.downsell_trigger == "pix" else ["no_pix", "pix"]
        self.downsell_audience = sorted(set(self.downsell_audience))
        needs_default = [step.delivery is None for step in self.upsells] + [
            bool(step.custom_offer and step.custom_offer.delivery is None) for step in self.downsells
        ]
        if any(needs_default) and self.default_delivery is None:
            raise ValueError("Uma oferta usa a entrega padrão, mas o fluxo não tem entrega padrão.")
        return self

    def media_ids(self) -> set[uuid.UUID]:
        found: set[uuid.UUID] = set()
        for block in self.welcome:
            found.update(block.media_ids)
        found.update(self.offer.media_ids)
        bumps = [self.order_bump] + [plan.order_bump for plan in self.plans]
        deliveries = [p.delivery for p in self.plans] + [self.default_delivery]
        for bump in bumps:
            if bump:
                found.update(bump.media_ids)
                deliveries.append(bump.delivery)
        for step in self.upsells:
            found.update(step.media_ids)
            deliveries.append(step.delivery)
        for down in self.downsells:
            found.update(down.media_ids)
            if down.custom_offer:
                deliveries.append(down.custom_offer.delivery)
        for delivery in deliveries:
            if delivery:
                found.update(delivery.media_ids)
        return found

    def plan(self, plan_id: str) -> Plan | None:
        return next((p for p in self.plans if p.id == plan_id), None)

    def bump_for(self, plan: Plan) -> OrderBump | None:
        if plan.bump_mode == "off":
            return None
        if plan.bump_mode == "custom":
            return plan.order_bump
        return self.order_bump


def default_flow() -> FlowDefinition:
    return FlowDefinition(
        offer=Offer(text="Oi, {nome}! 💕 Que bom te ver por aqui.\n\nEscolha seu plano abaixo 👇"),
        plans=[],
    )

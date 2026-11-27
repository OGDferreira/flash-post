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
    # Humanized conversation: when True, the bot waits for the lead to reply before sending
    # this block (instead of / on top of the time delay). Only used in the welcome sequence;
    # ignored in the after-purchase drip.
    wait_for_reply: bool = False

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
    # Messages sent to the buyer right after this delivery, for ANY purchase that uses it
    # (plan, order bump, upsell or downsell). Each message is a text or an audio (voice);
    # ``delay_seconds`` on a message is how long to wait before it (0 = instant / right
    # after the previous one).
    after_purchase: Annotated[list[Block], Field(max_length=10)] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Delivery":
        if self.type == "group" and self.group_chat_id is None:
            raise ValueError("Escolha o grupo/canal da entrega.")
        if self.type == "pack" and not self.media_ids:
            raise ValueError("O pack precisa de pelo menos uma mídia.")
        if self.type == "default" and not (self.text or self.media_ids or self.link):
            raise ValueError("A entrega padrão precisa de mensagem, mídia ou link.")
        for message in self.after_purchase:
            if message.type not in ("text", "voice"):
                raise ValueError("A sequência pós-compra aceita só texto ou áudio.")
        return self


class OrderBump(_Model):
    """Extra offered before the PIX ("Adicionar X por +R$ Y?"); one PIX for the total."""

    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Money
    text: Text = "Quer adicionar <b>{bump}</b> por apenas <b>+{bump_valor}</b>?"
    media_ids: MediaList3
    accept_label: Label = "✅ Sim, quero!"
    decline_label: Label = "Não, obrigado"
    delivery: Delivery | None = None  # None = the funnel's default delivery


class Plan(_Model):
    id: Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")]
    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Money
    # Fixed USD price for this plan (international "fixed" pricing); None = convert by the rate.
    price_usd: Annotated[Decimal, Field(ge=Decimal("0.50"), le=Decimal("100000"), decimal_places=2)] | None = None
    # None = lifetime access.
    duration_days: Annotated[int, Field(ge=1, le=3650)] | None = 30
    button_text: Label | None = None
    button_style: ButtonStyle = "default"
    delivery: Delivery | None = None  # None = flow's default_delivery
    # Own "payment approved" message for this plan; None = use the funnel's default (Payment.approved_text).
    approved_text: Text | None = None
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
    With ``hide_decline`` there is no "no" button: the next step only follows a payment."""

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
    # Own "payment approved" message for this upsell; None = funnel default.
    approved_text: Text | None = None


class CustomOffer(_Model):
    """A plan that exists only inside one downsell step."""

    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Money
    duration_days: Annotated[int, Field(ge=1, le=3650)] | None = 30
    delivery: Delivery | None = None  # None = flow's default_delivery
    # Own "payment approved" message for this downsell offer; None = funnel default.
    approved_text: Text | None = None


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


class Previews(_Model):
    """"Ver prévias" button on the welcome screen: sends media that delete themselves."""

    enabled: bool = False
    label: Label = "👀 Ver prévias"
    style: ButtonStyle = "primary"
    text: Caption | None = "👀 Prévias liberadas! Elas somem em {tempo}."
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    spoiler: bool = False
    # Telegram only deletes a bot's message within 48 hours of sending it.
    delete_after_seconds: Annotated[int, Field(ge=5, le=172800)] = 60

    @model_validator(mode="after")
    def _check(self) -> "Previews":
        if self.enabled and not self.media_ids:
            raise ValueError("Adicione pelo menos uma mídia nas prévias.")
        return self


class SmartReplyRule(_Model):
    """A keyword rule for a lead's free-text message: when any keyword is found in the
    message, the bot answers with ``reply`` and then optionally nudges the funnel on."""

    # Case/accent-insensitive "contains" match; a rule with no keywords never matches on its
    # own (use the fallback for the catch-all). Spintax ``{a|b}`` is allowed in ``reply``.
    keywords: Annotated[list[Annotated[str, Field(min_length=1, max_length=60)]], Field(max_length=20)] = Field(
        default_factory=list
    )
    reply: Text
    # After replying: "none" just answers; "plans" re-sends the plan buttons; "offer" re-sends
    # the whole welcome offer (media + buttons). Keeps the funnel moving after an objection.
    then: Literal["none", "plans", "offer"] = "none"

    @model_validator(mode="after")
    def _check(self) -> "SmartReplyRule":
        if not (self.reply or "").strip():
            raise ValueError("A resposta inteligente precisa de texto.")
        return self


class SmartReplies(_Model):
    """Replies to a lead who types something off-script (a question, an objection) instead of
    tapping a button. Keyword rules are tried in order; the first match answers. When none match
    and ``fallback_enabled`` is on, ``fallback_text`` answers. Off = the bot stays silent as before."""

    enabled: bool = False
    rules: Annotated[list[SmartReplyRule], Field(max_length=30)] = Field(default_factory=list)
    fallback_enabled: bool = False
    fallback_text: Text = (
        "Não entendi 😅 Toque em um dos botões acima para continuar, ou me diga o que você procura."
    )
    # What the fallback does after answering, like a rule's ``then``.
    fallback_then: Literal["none", "plans", "offer"] = "none"

    @model_validator(mode="after")
    def _check(self) -> "SmartReplies":
        if self.enabled and self.fallback_enabled and not (self.fallback_text or "").strip():
            raise ValueError("Configure a mensagem de fallback das respostas no DM.")
        return self


class FollowUpStep(_Model):
    """One retomada attempt: after ``delay_minutes`` of the lead going quiet, send this
    message (text and/or media). Several steps = several attempts, each with its own wait."""

    delay_minutes: Annotated[int, Field(ge=1, le=43200)] = 60  # up to 30 days
    text: Caption | None = None
    media_ids: MediaList3
    spoiler: bool = False

    @model_validator(mode="after")
    def _check(self) -> "FollowUpStep":
        if not ((self.text or "").strip() or self.media_ids):
            raise ValueError("Cada tentativa de retomada precisa de texto ou mídia.")
        return self


class FollowUp(_Model):
    """Retomada de conversa: if a lead abandons mid-funnel (goes quiet, no reply) the bot
    sends automatic follow-ups. ``steps`` are the attempts, in order; the timer resets on any
    lead action and the chain stops as soon as the lead pays. Off = no follow-ups, as before."""

    enabled: bool = False
    steps: Annotated[list[FollowUpStep], Field(max_length=10)] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "FollowUp":
        if self.enabled and not self.steps:
            raise ValueError("Adicione pelo menos uma tentativa de retomada.")
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
    # The "payment approved" message, sent before the delivery. True: always; False: never
    # (the delivery goes straight away); None (funnels saved before the switch): as before,
    # skipped when an upsell follows right after the payment.
    approved_enabled: bool | None = None
    # Optional image sent together with the "payment approved" message (media + caption in the
    # same Telegram message; falls back to media then text when the caption is too long).
    approved_media_ids: MediaList3
    approved_spoiler: bool = False
    expired_text: Text = "Seu Pix expirou. Toque abaixo para gerar um novo."
    # Legacy single choice of how the Pix was shown: "qr" = QR code + text + code in one
    # message; "steps" = instructions, the code in a copy box, then the buttons. Kept so
    # funnels saved before the switch keep validating; folded on load into the two toggles
    # below, which can now be on at the same time.
    layout: Literal["qr", "steps"] = "qr"
    # Both can be on: the lead gets the QR image AND the step-by-step with the copy box.
    # None on both (funnels saved before the switch) = derive from ``layout``.
    qr_enabled: bool | None = None
    steps_enabled: bool | None = None
    steps_text: Text = (
        "✅ <b>Como realizar o pagamento:</b>\n\n"
        "1. Abra o aplicativo do seu banco.\n"
        "2. Selecione a opção \"Pagar\" ou \"PIX\".\n"
        "3. Escolha \"PIX Copia e Cola\".\n"
        "4. Cole a chave que está abaixo e finalize o pagamento com segurança."
    )
    code_intro: Annotated[str, Field(max_length=200)] = "Copie o código abaixo:"
    after_code_text: Annotated[str, Field(max_length=500)] = "Após efetuar o pagamento, clique no botão abaixo ⤵️"
    # Optional message (media + text) sent right before the Pix, for a warmer payment step.
    intro_enabled: bool = False
    intro_text: Text | None = None
    intro_media_ids: MediaList3
    intro_spoiler: bool = False

    @model_validator(mode="after")
    def _fold_layout(self) -> "Payment":
        # Old funnels only set ``layout``; map it to the two independent toggles.
        if self.qr_enabled is None and self.steps_enabled is None:
            self.qr_enabled = self.layout == "qr"
            self.steps_enabled = self.layout == "steps"
        else:
            self.qr_enabled = bool(self.qr_enabled)
            self.steps_enabled = bool(self.steps_enabled)
        # Never leave the lead with no way to pay.
        if not self.qr_enabled and not self.steps_enabled:
            self.qr_enabled = True
        # Keep ``layout`` meaningful for anything still reading it (QR wins when both are on).
        self.layout = "qr" if self.qr_enabled else "steps"
        if self.intro_enabled and not (self.intro_text or self.intro_media_ids):
            raise ValueError("Configure a mensagem (texto ou mídia) que vai antes do pagamento.")
        return self

    def show_qr(self) -> bool:
        return self.qr_enabled is None and self.layout == "qr" or bool(self.qr_enabled)

    def show_steps(self) -> bool:
        return self.steps_enabled is None and self.layout == "steps" or bool(self.steps_enabled)


class International(_Model):
    """Cartão (Stripe) para vender também em moeda estrangeira, configurado por funil.

    Quando ligado e a Stripe estiver liberada, o lead pode pagar no cartão na moeda
    escolhida, além do Pix em BRL. ``translate`` liga a tradução automática da copy.
    """

    enabled: bool = False
    # Moedas de cartão além do BRL (hoje só USD).
    currencies: list[Literal["USD"]] = Field(default_factory=list, max_length=1)
    # "variable": converte o preço em BRL pela taxa; "fixed": usa o preço próprio do plano.
    pricing: Literal["variable", "fixed"] = "variable"
    # BRL por 1 USD (modo variável). Ex.: 5.00 → R$5 = US$1.
    usd_rate: Annotated[Decimal, Field(ge=Decimal("1"), le=Decimal("100"), decimal_places=2)] = Decimal("5.00")
    # Traduz a copy automaticamente para o idioma do lead (LibreTranslate).
    translate: bool = False

    @model_validator(mode="after")
    def _check(self) -> "International":
        if self.enabled and not self.currencies and not self.translate:
            raise ValueError("Ligue ao menos uma moeda estrangeira ou a tradução automática.")
        return self


class FlowDefinition(_Model):
    version: Literal[1] = 1
    age_gate: AgeGate = Field(default_factory=AgeGate)
    international: International = Field(default_factory=International)
    # "Conversa humanizada": the pre-offer sequence runs only when this is on. Default True
    # so funnels saved before the toggle (and any with welcome blocks) behave exactly as before.
    welcome_enabled: bool = True
    welcome: list[Block] = Field(default_factory=list, max_length=30)  # optional pre-offer sequence
    offer: Offer = Field(default_factory=Offer)
    # Keyword replies + fallback for leads who type something off-script in the DM.
    smart_replies: SmartReplies = Field(default_factory=SmartReplies)
    # Automatic follow-ups when a lead goes quiet mid-funnel (retomada de conversa).
    follow_up: FollowUp = Field(default_factory=FollowUp)
    plans: list[Plan] = Field(default_factory=list, max_length=10)
    payment: Payment = Field(default_factory=Payment)
    default_delivery: Delivery | None = None
    order_bump: OrderBump | None = None  # flow default, used by plans in "default" bump mode
    upsells: list[UpsellStep] = Field(default_factory=list, max_length=20)
    previews: Previews = Field(default_factory=Previews)
    # Legacy: one sequence aimed at "no_pix" and/or "pix" leads. Folded on load into the
    # two separate sequences below and then dropped.
    downsell_trigger: Literal["pix", "start"] = "pix"
    downsell_audience: list[Literal["no_pix", "pix"]] | None = None
    # Sequence for leads who generated a PIX and did not pay.
    downsells: list[DownsellStep] = Field(default_factory=list, max_length=20)
    # Sequence for leads who started and never generated a PIX (None = not migrated yet).
    downsells_no_pix: Annotated[list[DownsellStep], Field(max_length=20)] | None = None
    support_username: Annotated[str, Field(max_length=33, pattern=r"^@?[A-Za-z0-9_]{0,32}$")] | None = None
    # @ do bot no Telegram, mostrado como link no teste do funil (abre t.me/<@>).
    bot_handle: Annotated[str, Field(max_length=33, pattern=r"^@?[A-Za-z0-9_]{0,32}$")] | None = None

    @model_validator(mode="after")
    def _check(self) -> "FlowDefinition":
        ids = [plan.id for plan in self.plans]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada plano precisa de um id diferente.")
        for plan in self.plans:
            if plan.delivery is None and self.default_delivery is None:
                raise ValueError(f"O plano '{plan.name}' não tem entrega e o fluxo não tem entrega padrão.")
        if self.downsells_no_pix is None:
            audience = self.downsell_audience
            if audience is None:
                audience = ["pix"] if self.downsell_trigger == "pix" else ["no_pix", "pix"]
            self.downsells_no_pix = [step.model_copy(deep=True) for step in self.downsells] if "no_pix" in audience else []
            if "pix" not in audience:
                self.downsells = []
        self.downsell_trigger, self.downsell_audience = "pix", None
        known = set(ids)
        for label, steps in (("Pix gerado", self.downsells), ("Pix não gerado", self.downsells_no_pix)):
            for index, step in enumerate(steps, start=1):
                if any(plan_id not in known for plan_id in step.plan_ids):
                    raise ValueError(f"O downsell {index} ({label}) usa um plano que não existe mais.")
        if self.support_username:
            self.support_username = self.support_username.lstrip("@") or None
        if self.bot_handle:
            self.bot_handle = self.bot_handle.lstrip("@") or None
        if self.international.enabled and self.international.pricing == "fixed" and "USD" in self.international.currencies:
            missing = [plan.name for plan in self.plans if plan.price_usd is None]
            if missing:
                raise ValueError(f"No preço fixo em USD, defina o preço de cada plano: {', '.join(missing)}.")
        needs_default = [step.delivery is None for step in self.upsells] + [
            bool(step.custom_offer and step.custom_offer.delivery is None) for step in self.all_downsells()
        ]
        bumps = [self.order_bump] + [plan.order_bump for plan in self.plans]
        needs_default += [bool(bump and bump.delivery is None) for bump in bumps]
        if any(needs_default) and self.default_delivery is None:
            raise ValueError("Uma oferta usa a entrega padrão, mas o fluxo não tem entrega padrão.")
        return self

    def media_ids(self) -> set[uuid.UUID]:
        found: set[uuid.UUID] = set()
        for block in self.welcome:
            found.update(block.media_ids)
        found.update(self.offer.media_ids)
        for step in self.follow_up.steps:
            found.update(step.media_ids)
        found.update(self.previews.media_ids)
        found.update(self.payment.intro_media_ids)
        found.update(self.payment.approved_media_ids)
        bumps = [self.order_bump] + [plan.order_bump for plan in self.plans]
        deliveries = [p.delivery for p in self.plans] + [self.default_delivery]
        for bump in bumps:
            if bump:
                found.update(bump.media_ids)
                deliveries.append(bump.delivery)
        for step in self.upsells:
            found.update(step.media_ids)
            deliveries.append(step.delivery)
        for down in self.all_downsells():
            found.update(down.media_ids)
            if down.custom_offer:
                deliveries.append(down.custom_offer.delivery)
        for delivery in deliveries:
            if delivery:
                found.update(delivery.media_ids)
                for message in delivery.after_purchase:
                    found.update(message.media_ids)
        return found

    def all_downsells(self) -> list[DownsellStep]:
        return [*self.downsells, *(self.downsells_no_pix or [])]

    def downsell_steps(self, sequence: str) -> list[DownsellStep]:
        """``sequence``: "pix" (generated a PIX, did not pay) or "no_pix" (never generated one)."""
        return self.downsells if sequence == "pix" else (self.downsells_no_pix or [])

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

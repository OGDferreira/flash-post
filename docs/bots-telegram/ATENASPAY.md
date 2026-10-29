# Atenas Pay

Atenas Pay is centrally managed by the Flash platform administrator. Users do not
enter their own Atenas API credentials. The administrator configures the platform
account once; sales and withdrawals are then routed to the appropriate Atenas
subaccount.

## Production setup (Render)

1. In the Atenas Pay dashboard, open **Dashboard → Integrações → API Keys** and
   copy the API key for the account/environment you intend to use.
2. In Render, open the FlashPost **Web Service → Environment** and add:

   | Key | Value |
   | --- | --- |
   | `ATENASPAY_API_KEY` | The API key copied from Atenas Pay |
   | `ATENASPAY_WEBHOOK_SECRET` | The webhook secret configured in Atenas Pay, below |

   Keep both values secret. Do not put them in the repository, frontend, or a
   message. `ATENASPAY_BASE_URL` does not need to be added for production; it
   defaults to `https://atenaspay.com.br`.
3. In FlashPost, open **Bots → Gateways de pagamento** (or `/bot/gateways`)
   while signed in as the Super Admin. In the Atenas Pay administrator card,
   copy the displayed webhook URL.
   It has this format:

   `https://<seu-dominio-publico>/api/bots/pay/atenaspay`
4. In Atenas Pay, open **Dashboard → Integrações → Webhooks**, configure a
   webhook secret, and save that same secret as `ATENASPAY_WEBHOOK_SECRET` in
   Render. Register the URL copied from FlashPost as a global webhook URL. If
   Atenas Pay asks which event to subscribe to, enable the PIX payment
   confirmation event (`payment.confirmed`).
5. Save the Render environment variables and let the service redeploy/restart.
   Return to **Bots → Gateways de pagamento**. Confirm that the API key and webhook
   secret both show as configured, then select **Liberar Athenas Pay**.
6. Make a low-value test payment and confirm it is approved in FlashPost. Also
   check the Atenas Pay dashboard for the transaction and webhook delivery.

`PUBLIC_BASE_URL` must be the public root URL of this deployed FlashPost service,
without `/api` or a trailing endpoint path. For example:
`PUBLIC_BASE_URL=https://flashpost.onrender.com`. The webhook URL shown in the
FlashPost Gateways panel is authoritative; use that exact URL in Atenas Pay.

The API key is used for PIX charges, balance lookup, and withdrawals. The webhook
secret is used to verify payment notifications; both are required before the
Super Admin can release Atenas Pay. A webhook URL is not a secret and is not an
environment variable.

## Choosing the gateway order

In **Bots → Gateways de pagamento**, every user and partner sees their gateways as
ordered cards (Principal, Fallback 1, Fallback 2). Tapping a card, or its arrows,
moves it up one position until it is the principal; the order is saved right away.
It applies only to the user's own funnels, and per funnel in "Gateway por funil".
Funnels shared by another operation always use the gateway set by whoever shared
them and cannot be changed by the receiver. Until someone orders their gateways,
the automatic order is SnakePay (when released), SmokePay, then Atenas Pay (when released).

## Payments and webhook

Each operation is charged through its Atenas Pay subaccount, using the workspace's stable
`fp-<workspace id>` external reference. Shared-funnel commissions and platform fees are sent
as subaccount splits. PIX creation uses the order ID as `external_id` for idempotency.

The webhook validates `X-Webhook-Signature` as HMAC-SHA256 of
`<timestamp>.<raw request body>` and processes `payment.confirmed` only. Duplicate notices are
safe; the order is approved and delivered only once. The "Já paguei" check also queries the
transaction with `GET /api/pix/{id}`.

## Saques pela Carteira Flash

With `ATENASPAY_API_KEY` configured on the server, the Wallet also reads the
workspace subaccount's live balance and lets the workspace owner or an
affiliated partner request a Pix withdrawal. It resolves the workspace's
external reference (`fp-<workspace id>`) through `GET /api/shops/{external_ref}`
and uses the returned internal ID for `GET /api/shops/{id}/balance`,
`POST /api/shops/{id}/withdraw`, and `GET /api/shops/{id}/withdrawals`. The user
cannot choose the reference: the API derives it from the authenticated account
and workspace.

Withdrawals use `POST /api/shops/{id}/withdraw`, require at least
R$ 10, and include an idempotent `correlation_id`, `sub_shop_id`, Pix key, and
key type. Flash records the request before calling Atenas Pay and periodically
checks `GET /api/shops/{id}/withdrawals` while the payout is
processing. If the API response is lost, Flash reuses the same
`correlation_id` during reconciliation instead of creating another withdrawal.
The gateway-reported fee and Pix E2E receipt are saved when available.

This feature withdraws only money already credited to that Atenas Pay
subaccount. A balance recorded only inside Flash or held by another gateway
cannot be withdrawn through Atenas. The Atenas account must also be enabled
for withdrawals and satisfy its verification requirements. The Super Admin
can request a payout for a partner from the administrative wallet page; the
partner or workspace owner can request their own payout from Wallet unless an
administrator has blocked withdrawals.

Reference: [Atenas Pay PIX creation](https://atenaspay.com.br/docs/create-pix) and
[payment webhook](https://atenaspay.com.br/docs/webhook-payment).

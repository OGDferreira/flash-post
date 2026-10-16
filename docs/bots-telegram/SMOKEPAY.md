# SmokePay: referência para o motor de bots

Resumo da documentação oficial (https://smokepay.com.br/docs, API v1.0), só com o que o motor de bots usa.
**Nenhuma chave real neste arquivo.** Credenciais ficam em variáveis de ambiente (Render) ou criptografadas no banco.

## Credenciais
| Variável | Origem no painel SmokePay | Escopo |
|---|---|---|
| `SMOKEPAY_API_KEY` | Integrações / Credenciais API | Somente **PIX** (sem Saques) |
| `SMOKEPAY_WEBHOOK_SECRET` | Integrações / Webhooks (HMAC) | Validação de assinatura |

Base URL `https://smokepay.com.br`, header `x-api-key`, JSON, datas ISO 8601 em UTC.

## Criar cobrança — `POST /api/pix/create`
| Campo | Uso no motor |
|---|---|
| `amount` (number, **reais**, mín. 1.00) | Preço do plano + order bump − desconto (2 casas) |
| `description` | "{nome do fluxo} · {plano}" (aparece no app do banco) |
| `external_id` | `tgo_{order_uuid}`: **idempotência**; repetir devolve a mesma cobrança |
| `webhook_url` | `https://flashpost.onrender.com/api/pay/smokepay/{segredo}` |
| `expiration` (segundos, padrão 1800) | Validade configurável do fluxo |
| `shop_id` | (terceiros) subconta do workspace, ex.: `ws_{workspace_id}` |
| `splits[]` | (terceiros) `{parent: true, amount: taxa_plataforma}` |

Resposta: `transaction.{id, txid, external_id, amount, fee, net_amount, status=pending, pix_copia_cola, qr_code_base64 (data URI PNG), expires_at}`.
Códigos: 201 criada, 200 idempotente, 400 validação, 401 chave, 409 conflito de external_id, 429 rate limit, 500/502 falha (retentar com o **mesmo** external_id).

## Consultar — `GET /api/pix/{id}`
`{id}` aceita o UUID, o txid ou o **nosso external_id**. Status: `pending | paid | expired | cancelled`.
Se `pending`, a SmokePay consulta o gateway na hora: serve para o botão "Verificar status" e para a conciliação de backup.

## Webhook `payment.confirmed`
- Headers: `X-Webhook-Event: payment.confirmed`, `X-Webhook-Signature: t=<unix>,v1=<hmac_hex>`.
- Assinatura: `HMAC-SHA256(secret, f"{t}.{corpo_cru}")`, comparação em tempo constante, janela de ±300 s. Usar os **bytes crus** da requisição, nunca o JSON re-serializado.
- Corpo: `event, transaction_id, txid, external_id, status=paid, amount, fee, net_amount, payer_name, payer_document_masked, paid_at, shop_id?, shop_external_ref?`.
- Não tem `event_id`: deduplicar por `transaction_id`.
- Retentativas: até 8 em ~7 dias (imediato, 1 min, 5 min, 30 min, 2 h, 12 h, 24 h, 72 h). **Qualquer 4xx encerra as tentativas.**
  - Assinatura inválida → 401 (correto parar).
  - Erro nosso (banco fora etc.) → 5xx, para a SmokePay tentar de novo.
- O evento também vai para os webhooks globais do painel. O endpoint financeiro atual (`app/smokepay`) continua recebendo as vendas do bot, o que é correto para o Financeiro (é venda da conta).

## Regras do motor
1. A venda só é aprovada por webhook válido **ou** por `GET /api/pix/{external_id}` com `status=paid`. Nunca por ação do lead.
2. Conciliação: um job consulta pedidos `pending` com mais de 2 min e menos de `expiration` (backup do webhook).
3. Valor pago: conferir `amount` do webhook contra o pedido; divergência vai para revisão, sem entrega automática.
4. Taxa SmokePay (`fee`, ex. 5%) é registrada no pedido para o painel mostrar bruto, taxa e líquido.

## Terceiros (fase 6): subcontas
- Cada workspace cliente = subconta `shop_id` (criada automaticamente no 1º Pix).
- Taxa da plataforma calculada no FlashPost (fixa até o limite; fixa + % acima) e enviada como `splits: [{parent: true, amount: X}]`.
- Os splits incidem sobre o **líquido após a taxa SmokePay**. Validar `X < net_amount` antes de enviar, porque split que excede é descartado em silêncio.
- Saldo e saque do cliente: `GET /api/shops/{id}/balance`, `POST /api/shops/{id}/withdraw` (mín. R$ 10, cooldown 5 min, `correlation_id`). Precisa de chave com escopo **Saques**, separada da chave PIX.

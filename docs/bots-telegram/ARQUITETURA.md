# Bots de vendas no Telegram: arquitetura (proposta)

Status: **proposta para aprovação**. Nada aqui foi implementado ainda.

## 1. Objetivo

Ter, dentro do FlashPost, um motor próprio de bots de vendas no Telegram com tudo o que o SharkBot oferece
(referência: vídeo "Referência de bot", tour de 3 min 53 s pelo painel SharkBot).

- **Agora:** roda em paralelo ao SharkBot. As métricas dos dois aparecem juntas no painel, identificadas pela origem.
- **Depois:** trocar 100% para o motor próprio, sem perder histórico de leads e vendas.
- **Futuro:** vender para terceiros (multi-tenant), cobrando uma **taxa da plataforma por venda aprovada**.
- **Regra de produto:** todo o fluxo é editável pelo usuário no painel. Nenhum texto, preço, atraso ou mídia fica fixo no código.

## 2. Visão geral

```
Lead no Telegram ──> Telegram Bot API ──webhook──> /api/tg/{bot_id}/{secret}
                                                        │
                                              Motor de fluxo (estado do lead)
                                     ┌──────────────────┼────────────────────┐
                               Envia mensagens     Gera Pix no gateway     Agenda ações futuras
                               (fila com limite)   (prioridade + fallback)  (downsell, remarketing,
                                                         │                   aviso de vencimento)
Gateway ──webhook assinado──> /api/pay/{gateway}/{conta}/{secret}
                                                         │
                                Venda aprovada: entrega (convite VIP de uso único) + upsell
                                + taxa da plataforma no razão + push "💸 Venda aprovada"
```

Tudo roda no backend FastAPI atual (mesmo serviço do Render), com Postgres/Supabase. Nada de serviço novo na primeira fase.

## 3. Modelo de dados (tabelas novas, todas com `workspace_id`)

| Tabela | Para quê | Campos principais |
|---|---|---|
| `tg_bots` | Bots conectados | token criptografado (`encrypt_value`), `tg_bot_id`, username, nome, foto, `webhook_secret`, status (online/erro), `flow_id`, limite por plano |
| `tg_flows` | Fluxos editáveis | nome, `definition` (JSON versionado, seção 4), `version`, `published_version`, ativo |
| `tg_flow_versions` | Histórico do fluxo | snapshot do JSON a cada "Salvar", para desfazer e para exportar/importar |
| `tg_leads` | Cada pessoa que deu /start | `tg_user_id`, nome, username, idioma, bot, fluxo, etapa atual, origem (`start` param / tracking), bloqueou o bot? |
| `tg_orders` | Cada Pix gerado | lead, plano/oferta (boas-vindas, upsell N, downsell, order bump, pack, renovação), valor, valor com variação de centavos, gateway usado, `external_id`, status (gerado → pago → expirado/estornado), QR/copia-e-cola, expira em |
| `tg_subscriptions` | Acesso com prazo | lead, plano, início, fim, grupo/canal, status, renovações |
| `tg_deliveries` | Entregas | pedido, tipo (convite VIP, mídia no privado, link), link de convite usado, entregue em |
| `tg_jobs` | Ações agendadas | lead, tipo (enviar etapa, downsell, remarketing, aviso de vencimento, expulsar), executar em, tentativas, `idempotency_key` |
| `tg_media_cache` | Reuso de mídia | arquivo de origem → `file_id` do Telegram por bot (o "cache de mídia" do vídeo) |
| `tg_groups` | Grupos/canais VIP | `chat_id`, título, bot é admin?, permissões |
| `payment_gateways` | Contas de gateway do workspace | tipo (SmokePay, AtenasPay…), credenciais criptografadas, prioridade, ativo, segredo do webhook |
| `platform_fees` | Razão de taxas da plataforma | pedido, valor da venda, % e taxa fixa aplicadas, status (a cobrar, cobrada via split, faturada) |
| `tg_remarketing_campaigns` | Disparos em massa | segmento (não pagou, expirou, comprou X), mensagem, mídia, agendamento, enviados/falhas |

As tabelas `shark_leads` e `shark_transactions` continuam como estão. O painel soma as duas fontes com uma coluna `source` (`sharkbot` | `flashpost`).

## 4. O fluxo editável (JSON)

Um fluxo é um documento JSON com as mesmas 13 seções do editor do SharkBot. O painel edita esse JSON e o motor só lê dele.

| Seção | O que o usuário configura |
|---|---|
| Bots | bots vinculados (vários bots por fluxo), grupo de cache de mídia, @suporte, tradução automática |
| Boas-vindas | mídias (separadas ou agrupadas, "mídia dinâmica"), texto com variáveis `{nome}` `{username}` `{plano}` `{valor}`, mensagem secundária, botão CTA, atraso entre mensagens |
| Planos | até 10 planos: nome, preço, moeda, duração (mensal, vitalício…), cor e texto do botão, entrega do plano, order bump próprio, **variação de preço em centavos** |
| Upsell | até 20 sequências após o pagamento: mídia, texto, plano oferecido, atraso, entrega |
| Downsell | até 20 sequências para quem não pagou: enviar após X min, desconto %, planos da oferta |
| Order Bump | produto extra no checkout, aplicável em boas-vindas, upsell, downsell e packs |
| Packs | conteúdos avulsos com preço próprio |
| Prévias | amostras enviadas antes da compra |
| Pagamentos | texto do Pix, QR na mesma mensagem ou separado, botões "Copiar código" e "Verificar status", prova social, mensagem de aprovação, botão de acesso |
| Assinatura | avisos antes de vencer (14/7/5/3/2/1 dias), mensagem de expiração, planos de renovação com desconto, expulsão automática |
| Remarketing | sequências para leads frios, por segmento |
| Botões | textos e cores padrão |
| Conversões | só leitura: Pix gerados/pagos, receita, conversão por etapa, "mais vendido" e "menor conversão" |

Recursos do vídeo que entram junto:
- **Exportar/importar fluxo** por código: o JSON compactado em base64.
- **Variáveis disponíveis** clicáveis no editor.
- **Mídias por etapa** enviadas uma vez e reutilizadas por `file_id`.

**Versionamento:** "Salvar" cria uma versão nova. Leads no meio do funil continuam na versão em que entraram, até o próximo passo, para nada quebrar no meio de uma compra.

## 5. Motor de fluxo

- **Webhook do Telegram:** um endpoint por bot (`/api/tg/{bot_id}/{secret}`). O webhook é registrado com `setWebhook` + `secret_token`, e o header é conferido a cada chamada. O endpoint responde 200 na hora e processa em segundo plano.
- **Estado do lead:** etapa atual + contexto (plano escolhido, pedidos abertos). Cada ação é idempotente (`update_id` do Telegram e `idempotency_key` nos jobs), porque o Telegram e os gateways reenviam eventos.
- **Fila de envio:** respeita os limites do Telegram (~30 mensagens/s por bot e 1/s por conversa). Se um bot for bloqueado pelo lead (erro 403), o lead é marcado e sai das sequências.
- **Ações agendadas:** downsell em X min, remarketing, aviso de vencimento e expulsão vão para `tg_jobs`. Um worker lê os jobs vencidos a cada poucos segundos, com `SELECT … FOR UPDATE SKIP LOCKED`, para não executar duas vezes. O APScheduler atual só "acorda" esse worker.
- **Escala:** a primeira fase roda dentro do serviço atual. Se o volume crescer, o worker vira um serviço separado no Render sem mudar o código do motor.

## 6. Pagamentos

### 6.1 Interface comum de gateway
Cada gateway é um adaptador com a mesma interface:
`criar_pix(valor, referência, cliente)` → `{id, copia_e_cola, qr, expira_em}`, `consultar(id)`, `validar_webhook(headers, corpo)`, `estornar(id)` (quando houver).

- **Prioridade e fallback:** se o gateway principal falhar ao gerar o Pix, o próximo da lista tenta, como o "Sistema de Fallback Inteligente" do vídeo.
- **Confirmação:** a venda só é aprovada pelo webhook assinado do gateway, ou por `consultar()` no botão "Verificar status". Nunca pela palavra do usuário.
- **Variação de centavos:** soma alguns centavos aleatórios para casar pagamentos em gateways que não devolvem a referência.
- **Primeiro gateway:** SmokePay. O FlashPost já recebe webhooks dele (`app/smokepay`), falta a parte de **gerar** o Pix. Depende da documentação da API de cobrança.

### 6.2 Taxa da plataforma (para vender a terceiros)
Cada workspace tem um plano com `% por venda` e/ou `R$ fixo por venda` (ex.: 2,5% + R$ 0,50). A cada venda aprovada, uma linha é registrada em `platform_fees`. Há duas formas de cobrar, e a escolha depende do gateway:

1. **Split no gateway (preferível):** se o gateway tiver split, a taxa já cai na conta da plataforma no momento do pagamento. Sem inadimplência.
2. **Razão + cobrança:** sem split, a taxa acumula e é cobrada por fatura semanal/mensal, com bloqueio dos bots se a fatura vencer.

O dono da plataforma (super admin) define planos e taxas. O cliente vê as taxas em "Financeiro".

## 7. Entrega

- **Grupo/canal VIP:** o bot precisa ser admin. Na aprovação, gera um convite com `createChatInviteLink(member_limit=1, expire_date)` e manda ao comprador. Quando a assinatura vence, `banChatMember` + `unbanChatMember` remove o acesso sem bloquear uma recompra.
- **Privado:** envia as mídias/links da entrega configurada.
- **Upsell entregue:** "mesmo do fluxo principal" ou entrega própria, como no vídeo.

## 8. Telas no FlashPost (aba "Bots")

| Tela | Conteúdo |
|---|---|
| Meus Robôs | cards por bot (foto, @username, leads, vendas, fluxo, online), conectar bot por token com tutorial do @BotFather, limite por plano |
| Meus Fluxos | lista com starts e conversão, criar/duplicar/importar/exportar |
| Editor de Fluxo | as 13 seções em abas, com pré-visualização da conversa no estilo Telegram |
| Gateways | contas, prioridade, fallback, teste de conexão, extrato |
| Clientes | leads e compradores, histórico, assinatura, reenviar acesso |
| Remarketing | campanhas por segmento |
| Grupos | grupos/canais VIP, verificação de permissão do bot |
| Conversões/Análises | funil por etapa, receita, ticket médio, ranking de bots/modelos |

Notificações: push "💸 Venda aprovada · R$ 97,00 · bot @ana_vip" (usa o Web Push existente).

## 9. Segurança e conformidade

- Tokens de bot e credenciais de gateway sempre criptografados; nunca enviados ao navegador depois de salvos.
- Webhooks com segredo na URL **e** assinatura/header conferidos; rejeita repetição.
- Isolamento por `workspace_id` em todas as consultas (multi-tenant desde o início).
- **Conteúdo adulto:** confirmação de maioridade do comprador antes da oferta, registro do aceite, e apenas conteúdo de criadoras adultas com consentimento. Termos de uso da plataforma proíbem o resto, e a plataforma pode desativar bots.
- **Sem cobranças enganosas:** o motor não terá "taxa de segurança devolvida" nem cobranças ocultas. Upsell e order bump são sempre ofertas claras.

## 10. Fases

| Fase | Entrega | Pronto quando |
|---|---|---|
| 1. Fundação | tabelas, conectar bot por token, webhook do Telegram, boas-vindas + planos, Pix SmokePay, aprovação, convite VIP, push de venda | um lead real compra e entra no grupo sozinho |
| 2. Funil | upsell, downsell, order bump, packs, prévias, fila de jobs | funil completo editável |
| 3. Assinaturas | vencimento, avisos, renovação, expulsão | assinatura renova ou sai sozinha |
| 4. Gateways | mais adaptadores, prioridade, fallback, extrato | fallback testado com falha simulada |
| 5. Remarketing e análises | campanhas, funil por etapa, ranking | — |
| 6. Multi-tenant comercial | planos, `platform_fees`, split/fatura, limites por plano | cobrança automática de taxa |
| 7. Migração total | importar leads/assinantes do SharkBot, desligar integração | SharkBot desligado sem perda |

## 11. Perguntas em aberto

1. **SmokePay:** há documentação da API para **gerar** cobranças Pix (não só o webhook)? Ela tem split?
2. **Entrega:** grupo/canal VIP por assinatura, conteúdo no privado, ou ambos na fase 1?
3. **Taxa futura:** qual modelo? % por venda, valor fixo ou os dois? Qual faixa (ex.: 2–5%)?
4. **Ordem das fases:** a fase 1 acima atende como primeiro passo?

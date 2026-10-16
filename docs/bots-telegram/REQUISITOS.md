# Bots de vendas no Telegram: requisitos (entrevista de 16/10/2026)

Complementa `ARQUITETURA.md`. Decisões tomadas pelo dono do produto em entrevista.

## Princípio
**O usuário monta tudo pelo painel**: mídias, copy, planos, preços, atrasos, entregas, upsell, downsell,
order bump, packs, remarketing, renovação e botões. Nada de conteúdo fixo no código.

## Contexto de operação
- Roda **em paralelo ao SharkBot** agora; o bot próprio deve permitir troca total depois.
- Futuro: vender a terceiros com **taxa por venda**.
- Fase 1 aprovada como descrita em `ARQUITETURA.md` §10.

## Decisões

| Tema | Decisão |
|---|---|
| Boas-vindas | Sequência de blocos com atraso configurável entre cada um (simula conversa) |
| Tipos de mídia | Foto, vídeo, áudio de voz (voice note), vídeo redondo (video note), álbum, mídia com spoiler/borrada |
| Validade do Pix | Configurável por fluxo; lembrete antes de expirar e novo Pix depois |
| Entrega | O usuário escolhe por plano/oferta: grupo/canal VIP, pack, entrega padrão (mensagem + mídias + link opcional) |
| Grupo VIP | Um grupo/canal por plano (vários planos podem usar o mesmo); convite de uso único; remoção ao vencer |
| Downsell | Sequência (até 20) para quem gerou Pix e não pagou, com desconto crescente; para ao pagar |
| Upsell | Sequência (até 20) após o pagamento, cada oferta com mídia, copy, preço, atraso e entrega própria; recusou → próxima |
| Order bump | Pergunta "Adicionar X por +R$ Y?" (Sim/Não) antes de gerar o Pix; Pix único com o total |
| Remarketing automático | (1) deu /start e não gerou Pix; (2) gerou Pix e não pagou; (3) assinatura vencida |
| Remarketing manual | Campanha por segmento (todos, compradores, não compradores, por plano) com agendamento |
| Durações de plano | Semanal, mensal, trimestral, semestral, vitalício e dias personalizados |
| Renovação | Avisos configuráveis antes de vencer, cada um com botão de Pix de renovação e desconto opcional (sem cobrança recorrente automática) |
| Packs | Mídias entregues no privado com proteção contra encaminhar/salvar (`protect_content`) |
| Conta do gateway (terceiros) | **Conta da plataforma**: o dinheiro de todos os clientes cai na conta da plataforma e é repassado descontando a taxa (ver riscos) |
| Taxa da plataforma | Configurável no admin: até um valor-limite cobra só taxa fixa; acima, taxa fixa + %; planos diferentes por cliente |
| Permissões | Só o responsável do workspace vê e edita a aba Bots |
| Gateways | SmokePay (fase 1), depois AtenasPay, PushinPay e SyncPay |
| Anti-queda | Vários bots por fluxo + link redirecionador do FlashPost que aponta sempre para um bot vivo; push quando um bot cai |
| Rastreio | Link `t.me/bot?start=código` por origem (conta do Instagram/campanha); leads e vendas por origem no painel |
| Maioridade (+18) | Confirmação opcional por fluxo (o usuário liga/desliga) |
| Pushes | Venda aprovada; bot caiu / gateway falhou; resumo do dia e marcos de vendas |

## Riscos e pendências
1. **Conta da plataforma recebendo dinheiro de terceiros**: a plataforma vira intermediadora de pagamentos.
   Antes de abrir para terceiros, validar com contador/advogado: enquadramento (subcredenciamento/arranjo de
   pagamento), notas fiscais sobre a taxa vs. sobre o total, KYC dos clientes, responsabilidade por chargeback
   e se os termos da SmokePay permitem repasse. Para a operação própria (fase 1) isso não se aplica.
   O sistema terá saldo por cliente, repasse (saque) e extrato, e também a opção de conta própria do cliente,
   caso a validação exija.
2. **API da SmokePay**: falta a documentação do endpoint de **criação** de cobrança Pix (o FlashPost hoje só
   recebe o webhook). O site bloqueia acesso automatizado (HTTP 403).
3. **+18 opcional**: recomendado ligado em fluxos de conteúdo adulto.

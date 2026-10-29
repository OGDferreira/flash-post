# Guia completo da Flash Bot

Este documento descreve as áreas e os recursos de vendas via Telegram que estão implementados na Flash Bot. A Flash Bot é uma das áreas da Flash Post e usa o mesmo workspace e sessão. Para os demais recursos da plataforma, consulte [GUIA_FLASH_POST.md](./GUIA_FLASH_POST.md).

## 1. O que a Flash Bot faz

A Flash Bot conecta bots do Telegram a funis de venda editáveis. O bot atende leads, apresenta ofertas e planos, gera cobranças Pix, confirma pagamentos por webhook ou consulta ao gateway, entrega o produto configurado e acompanha vendas e comissões.

As principais telas são:

| Tela | Caminho | Para que serve |
|---|---|---|
| Painel | `/bot` | Starts, leads, Pix, vendas, receita e conversão por período. |
| Análises | `/bot/analises` | Comparativos de funis e planos. |
| Meus funis | `/bot/funis` | Criar e editar funis, acompanhar resumo e administrar cópias. |
| Pastas de funis | `/bot/pastas` | Agrupar funis e sortear um funil por lead. |
| Compartilhados comigo | `/bot/compartilhados-comigo` | Usar funis compartilhados por outro dono. |
| Que compartilhei | `/bot/compartilhei` | Compartilhar seus funis e definir as regras por sócio. |
| Meus bots | `/bot/robos` | Conectar, ativar e vincular bots a funis ou pastas. |
| Remarketing | `/bot/remarketing` | Criar, programar e acompanhar campanhas para leads. |
| Leads, starts e vendas | `/bot/vendas` | Consultar leads e pedidos, incluindo Pix gerados, pagos e expirados. |
| Gateways | `/bot/gateways` | Consultar e configurar gateways e sua prioridade. |
| Carteira | `/carteira` | Consultar saldos e saques suportados. |

O acesso pode ser limitado por perfil e permissão. Consulte o dono da operação se a tela necessária não estiver disponível.

## 2. Configuração inicial

1. **Conecte um bot do Telegram.** Crie-o no `@BotFather` e informe o token em **Meus bots > Conectar bot**. O token é usado pelo servidor para falar com a API do Telegram.
2. **Configure um destino de entrega.** Para entregar acesso a um grupo ou canal, adicione o bot como administrador e conceda a permissão necessária para convidar e remover membros.
3. **Crie um funil.** Configure conteúdo, pelo menos um plano, a validade do Pix e uma forma de entrega válida.
4. **Associe o bot ao funil.** Em Meus bots, selecione o funil ou uma pasta de funis. Um bot sem funil não responde com um fluxo de venda.
5. **Configure os gateways.** A disponibilidade depende do administrador da plataforma e das credenciais definidas no servidor ou na conta.
6. **Teste a jornada.** Abra o link do bot, envie `/start`, percorra a oferta e confirme que o Pix e a entrega funcionam antes de divulgar.

## 3. Meus bots

Em **Meus bots**, cada cartão apresenta nome, `@username`, estado, leads, vendas, conversão e faturamento.

O dono pode:

- conectar um bot pelo token do `@BotFather`;
- ativar ou pausar o bot;
- escolher um funil, limpar a associação ou apontar para uma pasta;
- reconectar o webhook do Telegram;
- vincular grupos/canais para entrega e cache de mídias;
- verificar a quantidade de mídias em cache;
- remover um bot.

Um bot pode executar seu próprio funil ou um funil compartilhado que esteja disponível para a operação. O vínculo de um funil pode ser alterado; a alteração vale para novos `/start`, não reescreve a jornada em andamento dos leads.

### Cache de mídia

O cache guarda referências de mídia do Telegram por bot para reutilização de conteúdo e redução de reenvios. A verificação mostra quantas mídias estão armazenadas no cache em relação ao total.

## 4. Meus funis e editor

O editor é dividido em nove seções. Alterações são salvas no funil e passam a valer para novos leads.

### 4.1 Bots

- Vincule vários bots ao mesmo funil.
- Ative/desative bots vinculados ou remova a associação.
- Consulte o resumo do funil: leads, VIPs e receita.
- Configure um username de suporte opcional para mostrar um botão de contato nas mensagens.

Com mais de um bot vinculado, cada bot atende os leads que chegam por ele; isso permite manter bots de reserva, mas não migra automaticamente os leads entre bots.

### 4.2 Boas-vindas

Monte uma sequência de até 30 blocos, com atraso configurável entre as mensagens:

- texto;
- foto;
- vídeo;
- áudio de voz;
- vídeo redondo;
- álbum com 2 a 10 mídias.

É possível ordenar os blocos, adicionar mídia e marcar fotos/vídeos como spoiler. Depois da sequência, o bot apresenta a oferta inicial. A mensagem da oferta pode conter até três mídias, botões de redirecionamento e um botão CTA que abre a lista de planos.

### 4.3 Planos

Configure até 10 planos por funil:

- nome, preço e duração (semanal, quinzenal, mensal, trimestral, semestral, anual, dias personalizados ou vitalício);
- texto e estilo do botão de compra;
- entrega própria ou entrega padrão;
- order bump padrão, personalizado ou desativado para aquele plano.

O preço precisa respeitar os limites de cobrança do gateway; no PIX da Athenas Pay, o mínimo documentado é R$ 1,00.

### 4.4 Upsell

Configure até 20 ofertas após uma compra, cada uma com preço, duração, atraso, texto, mídias, botões e entrega. O lead pode aceitar ou recusar uma oferta. Há a opção de ocultar o botão de recusa, caso em que a próxima etapa só é apresentada após o pagamento, conforme o comportamento descrito no editor.

### 4.5 Downsell

Há sequências separadas para dois públicos:

- **Pix gerado e não pago**;
- **deu `/start` e não gerou Pix**.

Cada sequência aceita até 20 mensagens/ofertas, com atraso, mídias, desconto percentual ou fixo, seleção de planos e, opcionalmente, um plano personalizado. O downsell para quando o lead paga.

### 4.6 Order bump

Ofereça um item extra antes da cobrança. O lead escolhe aceitar ou recusar; se aceitar, o valor do item é somado e a compra gera um Pix único. Pode haver um bump padrão para o funil ou um bump individual por plano.

### 4.7 Prévias

Ative um botão de prévia e escolha as mídias, legenda, estilo do botão e tempo de remoção. As mensagens de prévia podem ser apagadas automaticamente entre 5 segundos e 48 horas depois do envio. É necessário cadastrar mídia para habilitar a seção.

### 4.8 Pagamento

Personalize:

- validade do Pix (5 minutos a 24 horas);
- texto enviado junto com a cobrança;
- rótulos dos botões de copiar código e “Já paguei”;
- mensagem de pagamento pendente;
- mensagem após aprovação;
- mensagem quando o Pix expira.

O pagamento é considerado aprovado pelo retorno autenticado do gateway ou por consulta ao gateway no fluxo de verificação. A mensagem do cliente, sozinha, não confirma uma venda.

### 4.9 Verificação +18

Ative uma confirmação de idade antes de continuar e defina o texto e o botão. O recurso é opcional por funil.

## 5. Entregas

Cada plano, bump ou oferta pode escolher uma forma de entrega, conforme as opções disponíveis:

- **Grupo/canal**: o bot cria um convite individual e, para acesso com duração, agenda a remoção quando a assinatura expira.
- **Pack**: envia as mídias compradas diretamente no Telegram, protegidas contra encaminhamento/armazenamento quando o modo de proteção é aplicado.
- **Entrega padrão**: envia mensagem, mídias e/ou link.
- **Upsell**: inicia a sequência de ofertas adicionais sem outra entrega imediata.

A entrega de grupo requer que o bot consiga administrar convites e membros no destino. A duração define o tempo de acesso; planos vitalícios não expiram.

## 6. Pastas de funis

Uma pasta agrupa funis. Ao associar um bot a uma pasta, o sistema sorteia um funil elegível para cada lead que inicia a conversa. Use pastas para distribuir leads entre variantes; verifique que os funis contidos têm planos, conteúdo e entregas configurados.

## 7. Compartilhamentos entre sócios

### Compartilhados comigo

O sócio aceita o compartilhamento e usa o funil do dono nos próprios bots. As regras de gateway e divisão são definidas por quem compartilhou. O conteúdo do funil é protegido para o sócio: leads, vendas e métricas da operação do sócio pertencem ao sócio.

### Que compartilhei

O dono escolhe o funil e o sócio e define, por compartilhamento:

- gateway;
- porcentagem do vendedor e comissão do dono;
- loop opcional que acompanha o funil;
- quando aplicável, dados de recebimento exigidos pelo gateway.

As regras se aplicam a vendas futuras. Vendas anteriores mantêm as condições vigentes quando foram cobradas.

### Regras por gateway

- **SmokePay**: usa a configuração central/subconta e os splits disponíveis para o fluxo.
- **SnakePay**: no fluxo documentado pela interface, o vendedor pode precisar cadastrar as próprias credenciais SnakePay; o dono informa o identificador SnakePay para receber a comissão quando aplicável. Os requisitos mudam para compartilhamentos em que o dono recebe toda a venda.
- **Athenas Pay**: usa a chave de API configurada pela plataforma e subcontas gerenciadas pela integração. A documentação fornecida descreve `shop_id` e divisão do líquido entre subcontas; o sócio não precisa configurar uma chave própria para este fluxo.

Na Athenas Pay, a comissão é enviada como split durante a cobrança. A subconta do vendedor é o destino principal e a subconta do dono pode receber a parte definida nas regras; o restante permanece na subconta principal. As subcontas são criadas pelo provedor no primeiro uso do identificador. A confirmação e o crédito dos splits dependem do pagamento ser aprovado.

**Limite de saque:** embora a Athenas Pay tenha operações próprias de saldo e saque documentadas para subcontas, a carteira atual do Flash não oferece a solicitação de saque Athenas pelo painel. O recebimento dividido na subconta não deve ser confundido com saque integrado à Carteira do Flash.

## 8. Gateways de pagamento

### Visão e prioridade

Em **Gateways**, o usuário consulta os provedores disponíveis, estado, taxas/descrições apresentadas e configuração por funil. O administrador pode definir a liberação central e a prioridade; as opções exibidas dependem do perfil, credenciais e disponibilidade.

### SmokePay

As cobranças podem usar a conta central e subcontas identificadas pelo Flash. A interface de gateways apresenta a configuração e o webhook, e a Carteira tem suporte de saque SmokePay conforme configuração do servidor.

### SnakePay

Pode ser habilitada pelo administrador para a plataforma. A tela permite configurar as credenciais de uma conta própria, quando usada, e o segredo de Cash Out para saque. As credenciais de usuário salvas são protegidas no servidor. A disponibilidade de split exige identificadores de destinatários válidos e regras suportadas pela conta.

### Athenas Pay

A liberação é administrativa. A chave de API e o segredo do webhook são definidos no servidor; o painel mostra o estado de configuração, URL do webhook e liberação para usuários. A integração de cobrança utiliza `POST /api/pix/create`, `shop_id`, `splits` e verificação de webhook HMAC conforme a documentação fornecida.

### Fallback e disponibilidade

O motor tenta os gateways na ordem configurada ou na ordem automática aplicável à operação. Um gateway indisponível, sem configuração ou que recuse a cobrança pode ser ignorado para tentar a próxima opção. Isso não substitui a conferência de que o pedido foi efetivamente criado e pago.

## 9. Leads, starts, pedidos e análises

### Painel

Escolha o período para acompanhar starts, leads, Pix gerados/pagos, receita e conversão. Os números são específicos dos bots/funis acessíveis à conta.

### Análises

Compare funis e planos para identificar vendas, receita e conversão no período selecionado. Os resultados dependem do intervalo e dos dados recebidos dos gateways e do Telegram.

### Leads, starts e vendas

A listagem exibe eventos de início e pedidos. Os pedidos podem apresentar estados como pendente, pago, expirado, em revisão ou falhou, com plano, valor, bot, lead, origem e datas disponíveis. Taxa, comissão e líquido dependem das informações retornadas pelo gateway.

### Atualização do estado

O gateway envia um webhook de pagamento, e o Flash Bot valida e associa o evento ao pedido. O botão “Já paguei” também consulta o gateway quando a operação suporta essa verificação. O processamento de confirmações é idempotente para evitar duplicar a entrega em notificações repetidas.

## 10. Remarketing

Em **Remarketing**, crie campanhas associadas a um funil. O editor permite escolher público/segmento, mensagens, mídias, botões e ofertas. Os segmentos disponíveis incluem todos, compradores, não compradores, quem gerou Pix, VIP expirado e membros de grupo, conforme as opções apresentadas pelo editor.

Uma campanha pode ser:

- enviada imediatamente;
- programada para uma data e horário;
- recorrente uma vez, diariamente, a cada quantidade de horas ou em dias da semana, conforme o agendador da tela.

O usuário pode consultar estatísticas, pausar um envio, retomar do ponto em que parou, editar ou excluir a campanha. Ao reenviar uma campanha já executada, os destinatários anteriores podem recebê-la novamente.

## 11. Carteira e repasses

A carteira consolidada está em **Carteira e saques**. Ela apresenta saldo por gateway e inicia o fluxo de saque para os gateways oferecidos pela interface, hoje SmokePay e SnakePay. Confira a chave Pix, a taxa e o valor líquido antes de confirmar: um Pix enviado pode não ser reversível.

Comissões de compartilhamento são registradas a partir dos pagamentos aprovados e splits informados pelos gateways. Para Athenas Pay, o saldo pode ser creditado na subconta do dono, mas a solicitação de saque dessa subconta ainda não está integrada à carteira Flash.

## 12. Jornada de compra

```text
/start → confirmação +18 (se ativa) → boas-vindas → oferta e planos
      → order bump (se configurado) → Pix → webhook/consulta
      → pagamento aprovado → entrega → upsells → fim do acesso (se temporário)
```

Se o lead não concluir a compra, a sequência de downsell apropriada pode ser enviada após os atrasos configurados. Quando uma cobrança expira, o bot pode informar a expiração e permitir gerar um novo Pix. Os eventos e tarefas são registrados no banco e processados pelo scheduler do backend.

## 13. Importação e exportação de funis

Os funis podem ser duplicados e exportados/importados por arquivo ou código de portabilidade, conforme as ações da tela de funis. Um código de importação possui validade; para compartilhar com um sócio preservando as regras e mantendo o conteúdo protegido, use os recursos próprios de compartilhamento.

## 14. Variáveis e personalização de mensagens

O editor de texto rico oferece variáveis para inserir dados contextuais do lead, da oferta ou da cobrança, como nome, username, plano e valor. As variáveis visíveis no editor são as suportadas por cada etapa. Use a prévia e faça um teste pelo Telegram para revisar a renderização final.

## 15. Administração e requisitos operacionais

- O administrador da plataforma configura os segredos dos gateways no ambiente do backend e controla a liberação.
- O endpoint público de webhook precisa estar acessível pelo provedor.
- A chave Telegram e os segredos de gateway não devem ser incluídos em mensagens, capturas de tela ou código do frontend.
- O scheduler do backend executa tarefas de expiração, entrega e campanhas programadas; indisponibilidade prolongada do serviço afeta tarefas temporizadas.
- O bot precisa manter permissões válidas nos grupos/canais para entregar convites e remover membros no vencimento.
- A confirmação de venda depende de dados confiáveis do provedor; o usuário não deve liberar manualmente um produto com base apenas em comprovante enviado pelo comprador.

## 16. O que não está descrito como funcionalidade atual

O editor atualmente apresenta as seções listadas neste guia. As decisões registradas no documento antigo de requisitos que não aparecem no editor atual — por exemplo, uma central de aviso de renovação com Pix de renovação configurável ou cobrança recorrente automática — não devem ser consideradas funcionalidades disponíveis sem uma tela e um fluxo implementados.

O saque Athenas pela Carteira Flash também não está disponível, mesmo que o provedor possua endpoints para subcontas. A existência de um endpoint na API externa não significa que a operação esteja conectada ao produto.

## 17. Documentação técnica relacionada

- [Arquitetura histórica dos bots](./bots-telegram/ARQUITETURA.md): documento de proposta atualizado com aviso de implementação; conferir este guia para a descrição funcional atual.
- [Requisitos e decisões de produto](./bots-telegram/REQUISITOS.md).
- [Configuração SmokePay](./bots-telegram/SMOKEPAY.md).
- [Configuração Athenas Pay](./bots-telegram/ATENASPAY.md).
- [Instalação e implantação](../README.md).

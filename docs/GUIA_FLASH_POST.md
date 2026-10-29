# Guia de funcionalidades da Flash Post

Este guia descreve as áreas disponíveis na aplicação conforme as telas e os fluxos atualmente implementados. Os menus variam conforme o perfil e as permissões da conta. A Flash Bot tem um guia próprio em [GUIA_FLASH_BOT.md](./GUIA_FLASH_BOT.md).

## 1. Visão geral da plataforma

A Flash Post reúne duas áreas de trabalho:

- **Flash**: gerenciamento de contas profissionais do Instagram, publicação em loops, métricas e operação da equipe.
- **Flash Bot**: criação e operação de bots de vendas no Telegram, funis, pagamentos e acompanhamento de vendas.

O seletor de ferramenta no menu alterna entre Flash e Flash Bot. As duas áreas usam a mesma sessão e o mesmo workspace. A área aberta, o menu e o tema dependem da rota selecionada.

## 2. Acesso e perfis

### Cadastro e entrada

- O acesso começa em **Entrar** ou **Criar conta**.
- Novos cadastros ficam pendentes até a aprovação de um administrador da plataforma.
- O convite de colaborador é aberto pelo link recebido em `/convite/:token`.
- O perfil permite conferir dados da conta, workspace e permissão.

### Perfis de workspace

- **Dono da operação (OWNER)**: administra o workspace e, conforme sua relação com outros usuários, pode gerenciar colaboradores e sócios.
- **Colaborador (COLLABORATOR)**: acessa apenas as áreas autorizadas para o trabalho no workspace; não recebe automaticamente acesso a todas as telas do dono.
- **Sócio (partner)**: é um usuário associado a um dono. Pode ver as áreas habilitadas pelo dono e, conforme as permissões, seu painel, contas, loops, métricas permitidas, Flash Bot e carteira.
- **Administrador da plataforma (SUPER_ADMIN)**: possui uma área administrativa separada. Quando também tem acesso de dono a um workspace, pode alternar entre a operação e a administração.

As permissões são verificadas tanto na navegação quanto nas rotas protegidas. O menu não substitui as validações do servidor.

## 3. Flash: contas, publicações e resultados

### Painel

O painel inicial resume a atividade do workspace no período selecionado, com métricas e indicadores da operação, avisos e informações de sócios quando aplicável. Um sócio ou colaborador pode receber uma versão de painel limitada ao próprio perfil.

### Contas conectadas

Em **Contas > Contas conectadas**, o dono conecta contas profissionais do Instagram por meio de um app Meta configurado no workspace. A tela permite:

- consultar as contas e o estado da conexão;
- filtrar contas ativas ou com problemas, pesquisar e ordenar a lista;
- associar contas a pastas de perfis;
- conectar e desconectar contas;
- acompanhar dados de conexão e duração até uma eventual falha.

Os tokens de acesso são mantidos no backend e não são exibidos no navegador. Contas desconectadas ou com erro podem precisar de reconexão ou de correção das permissões Meta.

### Apps Meta

Em **Configurações > Apps Meta**, o dono cadastra e administra os apps Meta usados para autorizar as contas do workspace. Cada app pode ser selecionado no processo de conexão. As credenciais são armazenadas de forma protegida no servidor.

### Pastas de perfis

Em **Pastas > Pastas de perfis**, contas podem ser organizadas em grupos para facilitar a seleção e a administração em outras áreas, como loops.

### Loops de publicação

Em **Loops > Loops de publicação**, o dono cria e administra execuções contínuas de publicações. A tela permite configurar loops, escolher contas e mídias, acompanhar o estado da publicação, pausar/retomar e analisar falhas. Também é possível ver as contas vinculadas ao loop e a duração de conexão antes de erros.

Loops compartilhados por um sócio podem aparecer como cópias vinculadas. A cópia usa a configuração compartilhada, mas o sócio conecta as próprias contas; essas contas não são transferidas pelo compartilhamento.

A publicação depende das permissões da Meta, da validade do token, dos requisitos de mídia e da configuração operacional habilitada no servidor.

Para o fluxo OAuth, convites de testadores, pastas por prefixo, armazenamento de mídia e execução/reconciliação de jobs, consulte o [guia técnico de contas do Instagram e loops](./GUIA_TECNICO_INSTAGRAM_E_LOOPS.md).

### Métricas e relatórios

Em **Métricas e relatórios > Métricas**, é possível escolher período e contas e consultar as áreas:

- **Por conta**: resumo de métricas da conta selecionada.
- **Views por dia**: evolução diária de visualizações.
- **Vídeos em alta**: conteúdos com melhor desempenho no período.
- **Ranking de engajamento**: ordenação de contas por engajamento.
- **Bots e fluxos**: desempenho relacionado aos bots e funis.
- **Vendas**: resultados de vendas integrados disponíveis para o workspace.

Os dados de insights dependem do que a Meta fornece para cada conta, tipo de mídia, permissão e período. Uma métrica indisponível na API não é necessariamente uma falha da conta.

### Ranking

Em **Visão geral > Ranking**, o usuário consulta o desempenho comparativo disponibilizado para as contas e operações às quais tem acesso.

### Feed

Em **Automações e filas > Feed**, é possível consultar publicações recentes e dados retornados pela Meta, como informações do perfil e métricas do conteúdo. A disponibilidade dos dados varia por conta e permissão. Esta área não substitui o gerenciamento dos loops de publicação.

### Log de erros

Em **Automações e filas > Log de erros**, o usuário pesquisa falhas por categoria, origem e período para diagnosticar problemas operacionais.

### Financeiro

Em **Métricas e relatórios > Financeiro**, o dono acompanha entradas, saídas, retiradas, pagamentos registrados para colaboradores, saldo e movimentações da operação. A tela também possui metas e controles de notificação relacionados às vendas. Na **Carteira**, donos e sócios/parceiros podem solicitar saques PIX do saldo disponível nos gateways habilitados para sua subconta. Com Atenas Pay configurada no servidor, o saldo é consultado na subconta Atenas do workspace e o saque é solicitado diretamente pela Flash; ele não usa saldos de outros gateways.

## 4. Sócios, equipe e organização

### Sócios, convites e comissões

Em **Sócios e comissões**, o dono gera e administra convites de parceria, define a comissão associada ao convite e acompanha resultados dos sócios. A área apresenta dados de contas, publicações, leads e vendas quando disponíveis. O dono pode abrir os detalhes da operação de um sócio.

Os compartilhamentos de funis e as regras de comissão específicas por funil ficam na área da Flash Bot; consulte [GUIA_FLASH_BOT.md](./GUIA_FLASH_BOT.md).

### Colaboradores

Em **Colaboradores e compartilhamentos > Colaboradores**, o dono administra a equipe do workspace. Entre as funções disponíveis estão:

- consultar convites e membros;
- cadastrar e editar colaboradores;
- controlar acesso;
- definir metas e valores/regras de remuneração conforme os campos da operação;
- registrar pagamentos;
- consultar indicadores e ranking da equipe;
- remover colaboradores.

O colaborador acessa somente as áreas permitidas pelo produto e pelas regras de navegação.

### E-mails das contas

Em **Contas > E-mails das contas**, o usuário administra registros de e-mail relacionados às contas, inclusive criação, edição, status, observações, fornecedor e importação em lote por arquivo ou texto. A tela também permite filtrar e excluir registros, inclusive em lote.

## 5. Configurações e comunicação

### Configurações

Em **Configurações**, o usuário ajusta opções pessoais e operacionais disponíveis no workspace. A tela inclui modo de exibição e opções para o widget de vendas no iPhone, incluindo apresentação e código de instalação.

### Webhooks e integrações

Em **Configurações > Webhooks**, o dono administra integrações SmokePay exibidas para a operação, incluindo criação e edição da operação, percentual de split, estado, rotação de chave e URL do webhook. Também há componentes para a integração SharkBot.

### Extensões

Em **Configurações > Extensões**, o dono cria, edita e remove registros de extensões e controla se ficam visíveis para colaboradores.

### Notificações e avisos

- **Notificações**: preferências e recursos de notificação disponíveis para a conta.
- **Avisos**: consulta avisos recebidos pela aplicação. Alertas de venda podem atualizar informações financeiras e reproduzir o som de venda quando o navegador permitir.

### Dúvidas e erros

Em **Suporte > Dúvidas e erros**, o usuário registra e consulta solicitações ou problemas, conforme os tipos apresentados na tela.

### Contatos

Em **Suporte > Contatos**, o dono consulta e administra os contatos associados ao workspace.

## 6. Carteira e saques

Na **Carteira**, o usuário consulta os saldos e solicita saques para uma chave Pix entre os gateways que suportam essa tela. O fluxo de saque pede a conferência dos dados de destino antes da confirmação e apresenta estados como em análise, processando, pago, recusado ou falhou.

Os gateways, valores mínimos, taxas e disponibilidade dependem da configuração do servidor e do saldo retornado pelo provedor. A Carteira não deve ser interpretada como uma função de saque universal para todo gateway; atualmente, a interface de saque enumera SmokePay e SnakePay.

## 7. Administração da plataforma

As páginas administrativas são exclusivas de `SUPER_ADMIN`:

- **Visão geral**: indicadores administrativos.
- **Usuários**: administração e aprovação de usuários.
- **Saques dos sócios**: acompanhamento e processamento administrativo das carteiras de parceiros.
- **Gateways de pagamento**: liberação e configuração administrativa dos gateways da Flash Bot.
- **Operações**: consulta de operações e seus resultados.
- **Workspaces**: consulta e administração de workspaces.
- **Funis**: consulta e administração de funis da plataforma.
- **Premiações**: configuração de premiações.
- **Notificações**: administração de notificações da plataforma.
- **Sistema**: configurações administrativas do sistema.

## 8. Instalação e funcionamento técnico

A implantação de referência e as variáveis de ambiente estão descritas no [README.md](../README.md). Em produção, o frontend React/Vite e o backend FastAPI são servidos pelo mesmo serviço, com PostgreSQL/Supabase e migrations Alembic.

O scheduler executa tarefas de manutenção e publicação em segundo plano no serviço da aplicação. Recursos que dependem de terceiros — Instagram/Meta, gateways de pagamento, notificações push e integrações externas — precisam de credenciais e permissões válidas.

## 9. Dicas de acesso

- Para adicionar contas do Instagram, configure primeiro um app Meta e autorize uma conta profissional.
- Para publicar, confira a validade da conexão, as permissões e os requisitos da mídia antes de iniciar um loop.
- Para vender pelo Telegram, siga o guia específico da [Flash Bot](./GUIA_FLASH_BOT.md).
- Se uma tela não aparecer, confira seu perfil e as permissões concedidas pelo dono ou administrador.
- Nunca coloque segredos de API, tokens ou chaves privadas no frontend ou em documentos públicos. As configurações de produção devem permanecer no gerenciador de segredos do serviço.

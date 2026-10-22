# Progresso — atualização 0.4.0

Branch: `main` (Render faz deploy a partir dela). Migração `20261015_32` é aditiva (dados preservados).

## Feito
- Métricas: período único (`period_bounds`, fuso `APP_TIME_ZONE`); `GET /api/analytics/views-daily` separa *views recebidas no dia* (Meta, por dia) de *views acumuladas dos vídeos publicados no dia*; cards/gráficos/relatórios usam o mesmo período.
- Filiados: código de convite por chefe (cadastro + perfil), % de participação, aba Filiados (contas + SharkBot + participação de referência, sem repasse), bloqueio de auto-vínculo/ciclo, sem acesso aos dados do chefe.
- Meta: callback somente leitura + copiar, modal "Como configurar" (escopos instagram_business_basic / _content_publish / _manage_insights).
- SharkBot: várias contas Shark (token de webhook por conta; o ID sozinho NÃO basta — é preciso configurar o webhook), origem em cada venda, deduplicação, vendas paginadas com filtro período/conta, conversões e ticket médio (só pagas, divisão por zero tratada).
- Extensões (ZIP ≤25 MB validado) e Dúvidas e erros (status acompanhável).
- UI: cards mais compactos, modo claro (toggle no cabeçalho, persistido), preto mais profundo no escuro, transições de página/aba (opacity+translate, respeita reduced-motion), foto de perfil redimensionada no cliente e enviada ao selecionar.
- Testes: 222 backend passando; `tsc`, `npm run build`, `npm run test:filters` ok.

## Pendências / não validado
- Dia de corte dos insights diários da Meta (fuso) não documentado: não validado contra a Meta real.
- Webhook Shark e OAuth Meta não testados contra serviços reais.
- Modo claro remapeia cores hex existentes; telas pouco usadas podem precisar de ajuste fino.
- Participação é valor de referência (bruto, sem taxas); não há repasse automático.

## Rodada 2 (ajustes pós-uso)
- Removidos banner de contas desconectadas e card "Saúde das contas"; sidebar com hover suave e botão fixar; Hub e Pastas em grade; "Organizar contas" ao lado do lápis.
- Loops: falhas listam todas as contas com falha (antes filtrava só contas conectadas) com erro ao expandir; edição em pop-up.
- Analytics: lista de contas até o rodapé; sync em segundo plano de todas as contas (`POST /api/analytics/sync`, `GET /api/analytics/sync-status`) com barra de status; Views por dia/Vídeos em alta mostram carregando/vazio/erro.
- Bots e fluxos agrupados por conta Shark + bot/fluxo (fallback por nome); dados já gravados sem id de bot continuam como estão.
- Sharkbot (URL e contas) em Integrações; nova aba "Apps Meta" (Configurações removida, rota antiga redireciona).

## 0.4.2
- Dashboard abre sempre em "Hoje"; colaboradores em cards recolhidos (nome + contas conectadas hoje), expandem ao clicar.
- Performance: gzip nas respostas; assets com hash em cache imutável (index/SW/manifest sempre revalidados); resumo do dashboard não soma views por vídeo (1 chamada Meta a menos por vídeo, por conta); polling de colaboradores 30s→120s.
- Nota: plano free do Render hiberna após ~15 min parado (primeiro acesso lento); só plano pago ou ping externo resolve.

## 0.5.0 — Neumorphism
- Design system trocado de glass para neumorphism (soft UI) em claro e escuro: tokens `--nm-*` em `index.css`, superfícies elevadas/afundadas por par de sombras; sidebar, topbar, nav mobile, cards, botões, campos, filtros de período e modais redesenhados.
- Tema claro corrigido: sidebar agora é clara e as cores de texto/fundo/borda hex legadas são remapeadas por script (contraste por luminância); `text-white` vira escuro no claro, exceto em botões de marca.
- "Conectar conta" vai direto ao Hub e mostra a lista de apps Meta inline (sem pop-up, antes de carregar as contas).
- Pendências: telas raras podem pedir ajuste fino de contraste; remap do tema claro é gerado a partir das classes `[#hex]` em uso (regerar se surgirem novas).

## 0.5.1
- Pastas: "Organizar contas" abre pop-up com todas as contas; tocar em conta sem pasta abre pop-up para escolher a pasta (usa o PUT de contas da pasta, mantendo as já existentes).
- App instalado (display-mode standalone): zoom por pinça/duplo toque bloqueado (viewport, gestos e touch-action).
- Loops: card mostra todo o relatório; lista de contas só aparece ao clicar no card ("Ver contas").
- Não validado com dados reais (demo sem pastas/contas); zoom só testável no PWA instalado.

## 0.6.0 — Parte 1: tokens e componentes base
- 1.310 cores hex soltas viraram tokens semânticos (`text-fg/fg-2/muted/accent`, `danger/warning/success(+soft)`, `brand`, `well`) definidos por tema em `index.css`; remap do tema claro removido. Ciano unificado no azul da marca.
- Novos componentes: `ui/Button`, `ui/Card`, `ui/Badge`; `lib/confirm.tsx` (`confirmAction` + `ConfirmHost`) substitui os 22 `window.confirm` por pop-up do design (título/detalhe/verbo inferidos; perigo = botão vermelho).
- Pendências do plano: 2 navegação mobile, 3 polling/Error Boundary, 4 dividir páginas, 5 testes Playwright, 6 worker de sync. Migrar botões artesanais para `<Button>` ao tocar cada tela.

## 0.7.0 — Parte 1: glassmorphism
- Design system trocado de neumorphism para glassmorphism (claro e escuro) via camada no fim de `index.css` e tokens `--glass-*`; mesmas classes (`glass-panel`, `dashboard-card`, `btn-*`, `.field`).
- Fundo ambiente animado (`body::before`, só `transform`, 38s, desligado em `prefers-reduced-motion`). Blur forte só ≥768px em cards/barras/modais; no celular fundos mais opacos, sem blur pesado.
- Grade de métricas no PC: 3 colunas (≥720px) e 4 (≥1100px), cards compactos (fim das barras compridas); celular mantém 2 por linha quadrados.
- theme-color e cache do service worker (v10) atualizados.

## 0.7.1 — Parte 2: logo e topo
- Logo C (F + post) aplicado: `components/BrandLogo`, `favicon.svg/.ico`, ícones 192/512 e `flashpost-logo.png` regenerados; cache do SW v11.
- Topo mostra só o ícone + "FlashPost" (sem "Workspace"); saudação "Boa tarde, <nome>" + data com hora e minutos (sem segundos) agora fica no início do Painel (dono e colaborador), atualizando a cada 30 s.

## 0.7.2 — Parte 3: navegação
- `layouts/navigation.ts`: 6 atalhos diretos (Painel, Contas, Pastas, Loops, Métricas, Colaboradores) + grupos recolhíveis (Contas, Publicação, Métricas, Equipe, Integrações, Suporte; Administração para super admin). Colaborador vê só o permitido (inclui Extensões e Dúvidas e erros).
- Menu lateral: atalhos no topo, grupos embaixo; grupo da página atual abre sozinho.
- Celular: botão de 3 traços e gaveta removidos; barra inferior com os atalhos + botão "+" (Mais) que abre folha com todas as funções por grupo, Perfil e Sair.
- Sidebar e folhas mais opacos para leitura. SW v12.

## 0.8.0 — Partes 4 e 5: conexões do dia, ranking com foto, alertas
- Resumo de analytics ganhou `connected_today`, `disconnected_today` (+ lista com tipo), `account_connection_ranking_today` e `_month`. "Desconectadas hoje" conta só quedas reais do dia: status erro/desconectada com `error_at` hoje; reconectadas (error_at limpo) e quedas de dias anteriores não entram.
- Tipo da queda (`classify_inactive_account`): manual, suspensa, restrita ou expirada, a partir do motivo salvo. `/api/loops/alerts` devolve `suspended_accounts` e `restricted_accounts`; o banner do Painel e o sino de notificações mostram as contas que caíram hoje.
- Painel: card "Conexões hoje" (conectadas/desconectadas); ranking com abas Dia (padrão) e Mensal; fotos no Painel, no Painel do colaborador e na página Ranking (iniciais como reserva). Novo `GET /api/members/{id}/avatar` (só membros ativos do mesmo workspace).
- Limite conhecido: restrição só é detectada quando a conta é isolada por erro da Meta; conta restrita que ainda publica não é sinalizada. Não há push no celular para queda de conta (só sino/banner). Não validado com a Meta real.

## 0.9.0 — Parte 6: convite de colaborador por link
- Migração `20261015_33` (aditiva): tabela `collaborator_invites` (só o hash do token é guardado; valor por conta, metas, bônus, validade, usos).
- Chefe: `POST/GET/DELETE /api/collaborators/invites`, `GET .../invites/defaults` ("última configuração usada" = valores do convite mais recente), `POST /api/collaborators/{id}/approve|reject`. Tela em Colaboradores: gerar link (modal, copiar), links ativos, revogar, fila "Aguardando sua aprovação".
- Colaborador: página pública `/convite/:token` faz o próprio cadastro; o vínculo nasce `INVITED` com o valor/metas do convite e o login responde 403 "aguarda a aprovação do chefe" até o chefe aprovar (vira `ACTIVE`; Extensões e Dúvidas e erros já fazem parte do acesso de colaborador). Link de uso único por padrão, expira em 7 dias (1–30), revogável; o link só aparece uma vez.
- Recusar apaga o cadastro pendente (e o usuário, se não tiver outro vínculo). Criação manual de colaborador continua existindo.
- Pendência: sem aviso (sino/push) ao chefe quando chega cadastro pendente além da fila na página.

## 0.10.0 — Animação da logo e Aparência
- Splash animada da logo no `index.html` (aparece antes do JS carregar) e o mesmo desenho animado nos estados de carregamento (`LoadingState`); sem movimento para quem pede "reduzir movimento".
- Perfil > Aparência: cor do site (7 predefinidas + seletor livre + "Padrão") e "Remover animações". A paleta toda (botões, realces, brilho do fundo) vem de variáveis derivadas de uma cor (`lib/appearance.ts`); guardado no navegador. Cores claras (amarelo/verde) usam tons mais escuros para manter o contraste do texto branco.
- Hover: cards e botões sobem de leve (só transform), campos realçam a borda.

## 0.10.1 — Barra lateral por hover e pastas inline
- Menu lateral: abre mais rápido ao passar o mouse (60 ms / fecha em 220 ms); as subabas de cada grupo abrem ao passar o mouse, animadas (grid-rows), e fecham ao tirar o mouse (teclado: foco abre). Item com leve deslize no hover.
- Removido o selo "Sistema online" do topo.
- Pastas: editar nome e cor agora acontece dentro do próprio card (Enter salva, Esc cancela); o formulário no topo ficou só para criar pasta.

## 0.10.2 — Aba Contatos e animação centralizada
- Nova aba **Contatos** (grupo Suporte; também para colaboradores): WhatsApp do FlashPost (+55 27 99938-4259, abre conversa com mensagem pronta), Suporte, Comunidade (grupo de WhatsApp — "Em breve" até existir o link), Instagram do FlashPost e Bot do Telegram ("Em breve"). Links e @ configuráveis em `frontend/src/lib/contacts.ts`.
- Animação da logo agora ocupa o centro da tela (tela cheia) nos carregamentos de sessão/permissões/página; carregamentos dentro de painéis continuam inline.

## 0.10.3 — Painel do colaborador no celular
- Cards do painel do colaborador agora usam o mesmo grid quadrado (2 por linha no celular) do painel do chefe.
- Novo card "A receber hoje" (conexões do dia × valor por conta conectada, vindo de `earnings_today`).
- Corrigido: valores em R$ apareciam como "R$ —" porque a API devolve decimais como texto; agora são convertidos.
- Pop-up de notificações no celular ocupa a largura da tela (antes cortava à esquerda) e tem fundo opaco.

## 0.10.4 — Login e cadastro redesenhados
- Login e cadastro usam o mesmo layout (`features/auth/AuthShell.tsx`): vidro + cor do tema, logo nova e copy financeira estilo landing page ("Cada conexão vira dinheiro no bolso" / "Transforme suas contas em receita previsível"), 3 benefícios e um cartão marcado como "exemplo ilustrativo". Os benefícios citados existem no produto (ganho do dia, metas/ranking, pagamentos).
- Sair já leva ao login (`/login`, com limpeza de cache e CSRF).

## 0.10.5 — Menos polling e ErrorBoundary
- Intervalos de atualização automática mais longos (Financeiro/E-mails/Erros 15–30 s → 60 s; demais painéis 60 s → 120 s; "Painel do colaborador" mantém 60 s por causa do "A receber hoje"). O sync em andamento continua a 3 s e o React Query já pausa polling com a aba em segundo plano.
- `ErrorBoundary` em volta do conteúdo das páginas: erro de renderização numa tela mostra aviso com "Recarregar" e a navegação continua funcionando; reseta ao trocar de rota.

## 0.10.6 — Páginas divididas e testes de fluxo
- Tipos e helpers das páginas grandes saíram para arquivos próprios, sem mudar comportamento: `pages/loops/loopShared.ts`, `pages/emails/emailShared.tsx`, `pages/collaborators/collaboratorShared.ts` e `CollaboratorParts.tsx` (WorkDaysPanel, campos). Loops 1171→1007, E-mails 943→823, Colaboradores 885→590 linhas.
- Testes de fluxo com Playwright (`frontend/e2e/flows.spec.ts`, `npm run test:e2e`): rota protegida → login, login com copy nova + erro de senha, cadastro, entrar → Contatos → Sair → login. Precisa do front e da API rodando; variáveis `E2E_BASE_URL`, `E2E_EMAIL`, `E2E_PASSWORD`, `E2E_CHROMIUM`.

## 0.11.0 — Pushes de conquistas do dia
- Novo `app/notifications/milestones.py`, rodando junto com o job de metas (reaproveita a mesma leitura de Insights por conta, sem chamadas extras à Meta). Vale para todo usuário com push ativado no dispositivo (Perfil → Notificações neste dispositivo).
- Marcos por dia local: visualizações 10 mil / 50 mil / 100 mil / 500 mil / 1 milhão; posts publicados 1 mil / 5 mil / 10 mil / 15 mil; vendas pagas Shark 10 / 50 / 100 / 500 (só chefe). Colaborador conta só as contas que ele conectou.
- Frases cômicas com emoji e variações sorteadas ("já pode comprar o pastel na feira 🥟", "Dubai te espera 🏝️", "o Zuckerberg tem medo de você 🫣", "vai com calma, quer ficar rico? 😂").
- Cada marco é enviado uma vez por dia; se vários forem batidos entre duas checagens, vai só o maior. Migração `20261015_34` (aditiva): tabela `milestone_notifications`.
- Limite: depende do push estar ativado no aparelho (no iPhone, só com o app instalado na Tela de Início) e de a Meta devolver as visualizações.

## 0.11.1 — Login/cadastro compactos
- Espaçamentos menores no celular: o login inteiro cabe na tela (390×844). Campos 40 px no celular, 44 px no desktop.
- Copy explica o que a plataforma faz: "Seu Instagram no piloto automático" / "Menos trabalho manual, mais resultado" — conectar contas, agenda de publicações, automações para pessoas e empresas. Frase rotativa (7 variações, troca a cada 3,5 s) e 4 benefícios no desktop. Removido o cartão de valor ilustrativo.

## 0.12.0 — Conquistas com dados reais, seguidores e admin de notificações
- Textos das conquistas viraram modelos com `{valor}` (número real do dia), `{conta}` e `{nome}`: ex. "👀 12.340 visualizações hoje!". Mais frases por marco (3–4 por marco de views, 3 por posts/vendas, 2 por seguidores).
- Seguidores: a cada 1 h o job em segundo plano relê `followers_count` de todas as contas conectadas (Meta) e avisa chefe(s) + quem conectou quando uma conta bate 1 mil, 5 mil, 10 mil, 50 mil ou 100 mil. Na primeira vez que vê uma conta grava o que ela já tem sem notificar (não dispara "bateu 1 mil" para quem já tinha 50 mil). Migração `20261015_35` (aditiva): `account_follower_milestones`.
- Admin → Notificações (`/admin/notifications`): editar/adicionar/remover frases por tipo e marco (salvo em `system_settings.milestone_messages`), "Voltar ao padrão" e botão Testar por frase, que monta o texto com os dados reais de hoje do workspace do admin e envia push para os dispositivos dele.
- Contas e Pastas: card da conta mostra "· por <apelido>" de quem conectou.

## 0.13.0 — Sequência, recorde, provocação no ranking e resumo da noite
- `app/notifications/engagement.py`, rodando no mesmo job das conquistas (a cada 15 min), só para quem tem push ativo. Usa conexões reais (`first_connected_at`, fuso de São Paulo).
- **Sequência 🔥**: dias seguidos batendo a meta diária de conexões (sem meta: ≥ 1 conexão). Às 20h, se a sequência é de 2+ dias e hoje ainda não bateu: "😱 Sua sequência de N dias tá em risco! Faltam X conexões…" (1×/dia).
- **Recorde pessoal 🏆**: quando as conexões de hoje passam o melhor dia anterior (melhor ≥ 3), 1×/dia.
- **Ranking**: compara com a checagem anterior; "⚠️ Fulano te passou no ranking do dia. Vai deixar? 😤" (no máximo 1×/hora) e "👑 Você é o número 1 de hoje!" (1×/dia). O retrato anterior fica em memória: após reiniciar o servidor, a primeira checagem só grava a posição.
- **Resumo da noite 🌙** às 22h: conexões, views do dia e R$ (colaborador: a receber pelas conexões; chefe: vendas pagas do dia), com frase de fechamento sorteada.
- Painéis (chefe e colaborador): cards "Sequência" e "Recorde pessoal" via `GET /api/notifications/engagement/me`.
- Estes textos ainda não são editáveis no admin (só as conquistas de views/posts/vendas/seguidores).

## 0.13.1 — Ajustes do painel
- Card "Sequência": removido o emoji 🔥; agora é o ícone vetorial de chama (preenchido quando há sequência, cinza quando não).
- Tema: a escolha (claro/escuro) é guardada em localStorage **e** num cookie de 1 ano, e reaplicada na abertura; se o navegador limpar o localStorage, o cookie mantém o tema.
- "Conexões hoje" → "Conexões do período": conectadas e desconectadas passam a seguir o filtro marcado (Hoje/Ontem/7 dias/30 dias/Total/Personalizado). Campos novos em `/api/analytics/summary`: `connected_period`, `disconnected_period`, `disconnected_period_accounts` (os `*_today` continuam para o sino).
- Data da saudação sempre com inicial maiúscula ("Quinta-feira, 15 de outubro…").
- Botão flutuante de atualizar (canto inferior direito, acima do menu no celular): refaz todas as consultas da tela (contas novas, métricas, ranking) com ícone girando.

## 0.13.2 — Barra do topo
- Topo reformulado: mostra o nome da página atual (e "FlashPost"/"Administração" como subtítulo), sino e tema agrupados numa cápsula, sem a sombra pesada.
- Diagnóstico Shark (sem mudança de código): o webhook recebe normalmente; a diferença de números vem de bots do Shark que não enviam eventos ao FlashPost.

## 0.14.0 — Automação por pasta
- Pasta com "Entrada automática por nome": prefixos (alice, alic, ali.…) + chave ligar/desligar. Conta NOVA conectada e sem pasta cujo @ começa com um prefixo entra na pasta sozinha. Não mexe em contas existentes.
- Loop com "Entrar no loop automaticamente" por pasta: toda conta que entra na pasta (manual ou auto) entra no loop e é enfileirada se ele estiver ativo. Contas nunca são removidas automaticamente. Loop pode ser criado só com pastas.
- Migration 20261015_36 (3 colunas com default). Aba Pastas mostra "Contas sem pasta" no topo. Topo mostra só "FlashPost".

## 0.14.1 — Notificações
- Causa de "não funcionam": em produção havia 0 dispositivos com push inscritos (nada a entregar). Novo aviso "Ativar notificações" (um toque) no app; no iPhone orienta instalar na Tela de Início.
- Frases padrão curtas: parabéns + views do dia + posts postados hoje (novo placeholder `{posts}`).

## 0.15.0 — Falcon Post e Falcon Bot (etapa 1: identidade, navegação e conta)
- FlashPost passa a se chamar **Falcon Post** (azul → ciano) e FlashBot **Falcon Bot** (violeta → magenta). Emblemas, logos com nome (versões para fundo claro e escuro), favicon, ícones do app instalado e notificações vêm de `frontend/public/brand/falcon*`. As páginas legais (Meta) continuam com o nome antigo até o app da Meta ser renomeado.
- As duas ferramentas dividem o mesmo login e o mesmo shell: o caminho decide a ferramenta (`lib/brand.ts`: `/bot/*`, `/carteira`, `/feature/affiliates` são Falcon Bot), com menu, paleta (`html[data-app]`) e logo próprios. Botão flutuante no canto inferior esquerdo alterna entre elas e volta para a última tela usada em cada uma.
- Falcon Post: menu por finalidade — Visão geral, Contas, Pastas, Loops, Métricas e relatórios, Automações e filas, Colaboradores, Configurações, Suporte. Item "Automações" (página vazia) saiu do menu.
- Falcon Bot deixou de ser uma página com abas: cada seção tem endereço (`/bot`, `/bot/funis`, `/bot/robos`, `/bot/remarketing`, `/bot/compartilhados-comigo`, `/bot/vendas`, `/bot/gateways`) e o menu lateral agrupa Funis, Robôs e leads, Vendas e financeiro, Gateways, Sócios e Conta. `/feature/bots?tab=x` redireciona.
- Visual inspirado na organização do painel da Sharkbot: fundo quase preto, cards com borda fina, Space Grotesk em títulos/números e JetBrains Mono nos rótulos (fontes empacotadas pelo Vite; a CSP não permite fontes externas). Camada "Falcon" no fim de `index.css`.
- Animação de entrada: o emblema da ferramenta gira e pousa com um anel e um brilho (splash do `index.html` e carregamentos).
- Perfil → **Alterar senha** (`POST /api/profile/password`): exige a senha atual, confirmação, nova ≠ atual; tentativas erradas usam o mesmo limitador do login; a sessão do navegador é renovada. Outras sessões abertas não são encerradas (o cookie de sessão é assinado e não há versão de sessão no banco).
- Painel do sócio no Falcon Post simplificado: contas conectadas e desconectadas (estado atual, não por período), botão "Conectar nova conta", faturamento com filtro de período e saldo da carteira, e ranking de posts. O menu do sócio no Falcon Post mostra só Painel, Contas, Loops (para os loops compartilhados), Ranking e Suporte.
- Pendente: artes das premiações ainda têm a marca antiga (FLASHBOT) embutida na imagem.

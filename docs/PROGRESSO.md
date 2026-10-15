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

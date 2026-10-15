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

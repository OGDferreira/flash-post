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

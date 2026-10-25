# Implementação de Permissões e Taxas para Sócios

## Status da Implementação

### ✅ Backend Completo

1. **Modelos de Dados**
   - `PartnerPermission`: Permissões granulares por plataforma (Flash Post / Flash Bot)
   - `FeeChangeLog`: Histórico de alterações de taxas com auditoria

2. **Serviços**
   - `permissions.py`: Gerenciamento e validação de permissões
   - `fee_service.py`: Gerenciamento de taxas (individual/global) com histórico

3. **Rotas API**
   - `GET /api/admin/partner-permissions/{user_id}`: Buscar permissões de um sócio
   - `PUT /api/admin/partner-permissions`: Atualizar permissões
   - `POST /api/admin/partner-permissions/initialize/{user_id}`: Inicializar permissões padrão
   - `GET /api/admin/fees/current`: Listar taxas atuais
   - `GET /api/admin/fees/user/{user_id}`: Taxa de um usuário específico
   - `PUT /api/admin/fees/user`: Alterar taxa individual
   - `PUT /api/admin/fees/global`: Alterar taxa global
   - `GET /api/admin/fees/history`: Histórico de alterações
   - `POST /api/admin/fees/preview-global`: Preview de alteração global
   - `GET /api/partners/me`: Atualizado para retornar permissões

4. **Migration**
   - `20261025_66_partner_permissions_and_fee_log.py`

### ✅ Frontend Completo

1. **Componentes**
   - `PartnerPermissionsManager`: Gerenciamento visual de permissões
   - `FeeManagementPanel`: Painel administrativo de taxas
   
2. **Hooks e APIs**
   - `permissionsApi.ts`: Hooks React Query para permissões
   - `feesApi.ts`: Hooks React Query para taxas
   - `usePartnerPermissions.ts`: Verificação de permissões do usuário

3. **Integração**
   - AdminUsersPage: Botão de permissões e painel de taxas
   - PartnerDashboardPage: Respeita permissões configuradas

## Como Testar

### 1. Executar a Migration

```bash
cd backend
alembic upgrade head
```

### 2. Testar Criação de Permissões

```bash
# Inicializar permissões para um sócio
curl -X POST http://localhost:8000/api/admin/partner-permissions/initialize/{user_id} \
  -H "X-CSRF-Token: {token}" \
  -H "Cookie: flashpost_session={session}"
```

### 3. Testar Alteração de Taxa Individual

```bash
curl -X PUT http://localhost:8000/api/admin/fees/user \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: {token}" \
  -H "Cookie: flashpost_session={session}" \
  -d '{
    "user_id": "{user_id}",
    "new_fee": 2.50,
    "reason": "Ajuste comercial"
  }'
```

### 4. Testar Alteração de Taxa Global

```bash
curl -X PUT http://localhost:8000/api/admin/fees/global \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: {token}" \
  -H "Cookie: flashpost_session={session}" \
  -d '{
    "new_fee": 3.00,
    "reason": "Reajuste da plataforma"
  }'
```

### 5. Verificar Histórico

```bash
curl http://localhost:8000/api/admin/fees/history \
  -H "Cookie: flashpost_session={session}"
```

## Fluxo de Uso

### Para o Administrador

1. **Gerenciar Permissões de Sócios**
   - Acesse Admin → Usuários
   - Localize um sócio (marcado com badge "Sócio")
   - Clique em "Permissões"
   - Configure individualmente para Flash Post e Flash Bot
   - Salve as alterações

2. **Gerenciar Taxas**
   - No topo da página Admin → Usuários, há o painel de taxas
   - **Taxa Global**: Altera para todos os usuários
   - **Taxa Individual**: Selecione um usuário específico
   - Defina a nova taxa (ou deixe vazio para padrão da plataforma)
   - Opcionalmente, adicione um motivo
   - Clique em "Ver Histórico" para auditar alterações

### Para o Sócio

O painel simplificado do sócio agora:
- Mostra apenas as seções permitidas
- Oculta "Contas Conectadas" se não tiver permissão
- Oculta "Ranking" se não tiver permissão
- Oculta informações de carteira se não tiver permissão para Flash Bot → Carteiras

## Permissões Disponíveis

### Flash Post
- `can_view_dashboard`: Visualizar painel principal
- `can_view_ranking`: Acessar ranking diário de visualizações
- `can_view_accounts`: Gerenciar contas conectadas
- `can_view_meta_apps`: Configurar Apps Meta
- `can_view_settings`: Acessar configurações
- `can_view_contact`: Visualizar contato

### Flash Bot
- `can_view_bot_dashboard`: Visualizar painel do Flash Bot
- `can_view_leads`: Gerenciar leads
- `can_view_wallets`: Acessar carteiras e sacar

## Notas Importantes

1. **Permissões Padrão**
   - Quando um usuário vira sócio, recebe permissões padrão (apenas dashboards)
   - O administrador deve configurar as demais permissões manualmente

2. **Taxas**
   - `null` significa taxa padrão da plataforma
   - Alterações globais afetam TODOS os usuários ativos
   - O histórico é mantido para auditoria
   - Vendas já processadas não são recalculadas

3. **Segurança**
   - Todas as rotas de admin requerem `SUPER_ADMIN`
   - Verificações de CSRF estão implementadas
   - O backend valida permissões mesmo se o frontend for burlado

## Tarefas Pendentes

1. ⏳ Implementar filtro de período no pop-up de informações do sócio (Flash Bot)
2. ⏳ Criar visualização "Ver como sócio" para administradores
3. ⏳ Remover ícones antigos do Falcon da pasta `frontend/public/brand/`
4. ⏳ Adicionar validação de permissões nas rotas protegidas do App.tsx
5. ⏳ Testes E2E para fluxo completo

# Guia técnico: contas do Instagram e loops de publicação

Este documento descreve o fluxo implementado na FlashPost para autorizar uma
conta profissional do Instagram, armazenar mídias e publicá-las em um loop.
Inclui a automação de pastas por prefixo de usuário e a inclusão das contas em
loops que observam essas pastas. Os exemplos abaixo são trechos do código atual;
os caminhos e os links de linha permitem conferir o contexto completo.

> **Escopo:** este guia documenta o comportamento do código deste workspace.
> A Meta pode alterar requisitos, permissões e nomes de telas; valide sempre as
> permissões e os requisitos atuais na documentação oficial antes de publicar.

## 1. Visão do fluxo completo

```text
OWNER configura um app Meta e seu redirect URI
  -> Instagram profissional é convidado como testador (se o app estiver em Development)
  -> usuário escolhe o app no FlashPost e inicia Instagram Login
  -> callback valida state, usuário, workspace, membership e app
  -> FlashPost troca o code, recebe token longo e consulta o perfil
  -> token é cifrado e a conta é salva no banco
  -> primeira conexão: @username pode determinar a pasta
  -> conta na pasta pode entrar nos loops que observam essa pasta
  -> upload JPEG/MP4 é guardado em Storage privado; metadados ficam no banco
  -> loop cria um job por conta e mídia
  -> worker cria o container na Meta, aguarda processamento e publica
  -> progresso é atualizado apenas para a conta cuja publicação foi confirmada
```

Uma pasta organiza contas; ela não armazena as credenciais nem publica por si
só. Um loop contém a configuração de publicação, a lista ordenada de mídias,
as contas selecionadas e, opcionalmente, IDs de pastas acompanhadas.

## 2. Meta: app, redirect URI e testador

### 2.1 Configuração do app

O fluxo existente usa **Instagram API with Instagram Login**, com as contas
profissionais Business ou Creator. O cadastro de app no FlashPost pertence ao
workspace e contém o App ID e o App Secret correspondentes ao Instagram Login.
O segredo é cifrado no backend; nunca deve ir para o frontend, Git, logs,
mensagens ou configuração pública.

O redirect URI usado pelo FlashPost é `PUBLIC_BASE_URL` acrescido de
`/api/instagram/callback`. O endereço registrado no painel Meta precisa ser
idêntico ao enviado durante o login (incluindo esquema, host, porta e caminho).
Em produção o README deste projeto lista o endereço de callback configurado.

Documentação oficial da Meta:

- [Instagram API with Instagram Login: Business Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Instagram Platform: visão geral e opções de login](https://developers.facebook.com/documentation/instagram-platform)

### 2.2 Convite e aceite do Instagram Tester

O convite de testador é uma **relação de acesso ao app em modo Development**.
Ele não conecta a conta ao FlashPost, não entrega um token ao FlashPost e não
substitui o consentimento OAuth. São etapas separadas:

1. No Meta for Developers, abra o app correto e adicione o usuário do Instagram
   em **Roles / Instagram Testers** (a nomenclatura da interface pode mudar).
2. O convidado deve entrar na conta Instagram profissional que será testada e
   aceitar o convite pendente nas configurações de **Apps e sites / Convites de
   testador** do Instagram.
3. Só depois de o convite aparecer como aceito, inicie a conexão no FlashPost
   com o app Meta que enviou o convite e conclua a tela de consentimento.
4. Verifique que a conta é Business ou Creator e que concedeu as permissões
   solicitadas pelo fluxo, incluindo publicação de conteúdo.

Enquanto o app estiver em Development, use contas que tenham acesso autorizado
ao app (por exemplo, testadores adicionados e com convite aceito). Para permitir
que contas fora das funções de teste usem a integração, avalie o modo Live, os
níveis de acesso avançado e a revisão do app exigidos pela Meta para os recursos
solicitados. Um convite aceito não equivale à aprovação de acesso avançado.

**Atenção à documentação antiga:** tutoriais de Instagram Basic Display API
podem descrever telas ou permissões de uma integração diferente. O código deste
projeto usa Instagram Login e permissões `instagram_business_*`; não copie
configuração de Basic Display para este fluxo.

## 3. Conectar uma conta: frontend, OAuth e persistência

### 3.1 Começo no frontend

Na interface de conexão, o usuário escolhe um app Meta do workspace. O frontend
chama `POST /api/instagram/connect`; a API devolve a URL de autorização e o
navegador é redirecionado para o Instagram. A escolha explícita do app evita
autorizar com credenciais diferentes das que pertencem às contas existentes.

Arquivos principais:

- [`ConnectAccountModal.tsx`](../frontend/src/components/ConnectAccountModal.tsx)
- [`router.py` — início e callback OAuth](../backend/app/instagram/router.py#L582)

### 3.2 Estado OAuth e validação no callback

O início do fluxo gera um `state` aleatório e guarda na sessão os dados que
amarram a tentativa ao usuário, workspace, credencial e revisão do app. O
callback compara o `state` de forma segura, rejeita tentativas expiradas (10
minutos), confere novamente usuário ativo, workspace ativo e membership ativa
OWNER/COLLABORATOR, e rejeita credencial removida ou alterada durante o login.

Trecho representativo de [`router.py`](../backend/app/instagram/router.py#L582):

```python
state = secrets.token_urlsafe(32)
request.session[_OAUTH_SESSION_KEY] = {
    "state": state,
    "user_id": request.session["user_id"],
    "workspace_id": str(access.workspace.id),
    "meta_app_id": str(credential.id),
    "credential_revision": str(credential.revision),
    "created_at": int(time.time()),
    "return_to": return_to,
}
```

O motivo: o `state` ajuda a impedir que uma resposta OAuth iniciada por outra
sessão seja associada ao usuário atual. Guardar a revisão do app também evita
que um callback iniciado com um segredo seja aceito depois da substituição da
credencial. Não remova essas verificações ao reorganizar as rotas.

### 3.3 Troca do code e permissões

`build_authorization_url` solicita:

- `instagram_business_basic`: identidade e perfil da conta;
- `instagram_business_content_publish`: publicação;
- `instagram_business_manage_insights`: métricas/Insights.

O backend troca o `code` por um token de curta duração e, depois, pelo token
long-lived. Em seguida consulta `user_id`, `username` e dados do perfil. A
implementação exige as permissões Basic e Content Publish se a resposta da Meta
trouxer a lista de permissões; a permissão de Insights é necessária para os
recursos de métricas, mas não para publicar.

Confira [`oauth.py`](../backend/app/instagram/oauth.py#L10) para os escopos e a
troca. O callback não confia em campos de perfil enviados pelo navegador: usa a
resposta autenticada da API da Meta.

### 3.4 Token cifrado e conta no banco

O registro `InstagramAccount` guarda workspace, pasta opcional, usuário
Instagram, username, estado, vencimento, credencial Meta que autorizou a conta
e token cifrado em `encrypted_access_token`. O segredo em texto claro existe
apenas durante a operação no servidor. A chave mestra de criptografia é
obrigatória para a conexão.

Veja [`instagram_account.py`](../backend/app/models/instagram_account.py#L24) e
[`router.py` — persistência e automação da primeira conexão](../backend/app/instagram/router.py#L760).
Uma conta nova chama `automate_account`; uma reconexão atualiza o registro e
token, mas não executa novamente essa automação. Portanto, reconectar não
reclassifica automaticamente a conta em outra pasta.

O worker renova tokens long-lived válidos antes do vencimento. Token expirado,
revogado ou inválido exige reconexão; refresh não substitui consentimento nem
recupera token já expirado.

## 4. Pastas: classificar contas por nome e associar loops

### 4.1 Regra aplicada ao nome da conta

Na interface de Pastas, o nome da pasta é descritivo. A regra automática usa
**prefixos do username do Instagram**, não o nome da pasta. Exemplo:

```text
Pasta: Receitas
Prefixo: cozinha
Conta nova: @cozinha_da_ana
Resultado: a conta entra em "Receitas"
```

Prefixos são convertidos para minúsculas, espaços laterais e `@` inicial são
removidos, itens repetidos são eliminados, há limite de 30 prefixos e cada
prefixo é limitado a 40 caracteres. Se mais de uma pasta corresponder, é usada
a primeira em ordem alfabética pelo nome.

Código essencial de [`folder_automation.py`](../backend/app/instagram/folder_automation.py):

```python
def matches(username: str, prefixes: list[str]) -> bool:
    name = username.strip().lower().lstrip("@")
    return any(prefix and name.startswith(prefix) for prefix in prefixes)
```

É correspondência por início do username: o prefixo `cozinha` também combina
com `cozinharapido`. Se for necessário igualdade exata ou uma regra diferente,
isso precisa ser uma mudança intencional de produto e acompanhada por testes.

### 4.2 Colocar contas da pasta em um loop

Um loop observa pastas por `auto_folder_ids` (IDs, não nomes). Ao criar ou
editar o loop, a API junta as contas conectadas e elegíveis das pastas. Quando
uma conta nova é classificada numa pasta, `join_auto_loops` encontra loops do
workspace que observam aquela pasta e associa a conta se ela ainda não estiver
associada.

Trechos em [`folder_automation.py`](../backend/app/instagram/folder_automation.py):

```python
for loop in loops:
    if str(folder_id) not in {str(item) for item in (loop.auto_folder_ids or [])}:
        continue
    fresh = [account for account in accounts if account.id not in existing]
    for account in fresh:
        db.add(InstagramLoopAccount(loop_id=loop.id, account_id=account.id))
    if fresh and loop.status == "active":
        await enqueue_loop_publications_now(db, loop, fresh, now=now)
```

Isso explica o fluxo automático solicitado: configure o prefixo na pasta,
inclua o ID dessa pasta em um loop, e novas contas correspondentes podem ser
incluídas e enfileiradas. Para contas existentes, a pasta deve ser atribuída ou
a associação de loop ajustada pela interface/API; mudar apenas o prefixo não
reprocessa contas já classificadas. Contas não são removidas automaticamente
de loops quando saem da pasta.

Referências:

- [`folder_automation.py` — normalização, classificação e inclusão](../backend/app/instagram/folder_automation.py)
- [`folders_router.py` — CRUD e atribuição manual](../backend/app/instagram/folders_router.py#L215)
- [`ProfileFoldersPage.tsx` — tela de pastas e busca por contas](../frontend/src/pages/ProfileFoldersPage.tsx)
- [`loops/router.py` — validação de contas e pastas do loop](../backend/app/loops/router.py#L839)

## 5. Mídias: arquivo no Storage, metadados no banco

### 5.1 Upload e validação

O upload autenticado de mídia passa pela rota `POST /api/media`. Atualmente:

- aceita JPEG (`image/jpeg`) e MP4 (`video/mp4`);
- limita o tamanho a 50 MiB, verificando o cabeçalho e o conteúdo transmitido;
- confere a assinatura básica do arquivo, em vez de confiar só no nome ou MIME;
- aplica validação adicional de vídeo/Reels;
- restringe capas de Reels a imagem JPEG.

O binário é enviado ao bucket privado `instagram-media` do Supabase Storage. O
banco **não armazena o binário**: `InstagramMedia` registra caminho no bucket,
nome, MIME, tipo, tamanho, legenda e timestamps. O caminho inclui o workspace e
um UUID do objeto.

Confira [`media_router.py`](../backend/app/instagram/media_router.py#L116),
[`storage.py`](../backend/app/instagram/storage.py#L10) e
[`instagram_loop.py` — modelo `InstagramMedia`](../backend/app/models/instagram_loop.py#L134).
Se a gravação de metadados falhar depois do upload, a rota tenta excluir o
objeto órfão; erros de persistência e limpeza são registrados.

### 5.2 URL assinada para a Meta

Como o bucket é privado, a Meta não recebe uma URL pública permanente. Na
publicação, o backend cria uma URL assinada temporária (TTL de quatro horas) e
envia essa URL à Graph API. O token de serviço do Supabase permanece no backend.
Uma falha na criação da assinatura impede a publicação e é registrada no job.

Veja [`storage.py` — criação da URL assinada](../backend/app/instagram/storage.py#L82)
e [`publishing.py` — URL e container](../backend/app/instagram/publishing.py#L163).

## 6. Configurar e criar um loop

Um loop guarda nome, intervalo mínimo/máximo, tipo de publicação, limite diário
por conta, modo de legenda/capa, estado ativo/pausado e IDs de pastas
observadas. Tabelas de associação conectam loop-contas e loop-mídias. O job de
publicação e o estado de progresso são persistidos separadamente.

Na criação, a API valida que as contas, pastas e mídias pertencem ao workspace;
filtra contas conectadas e mídia compatível com o tipo do loop; grava as
associações; aplica configurações de legenda/capa e enfileira imediatamente a
primeira mídia para cada conta elegível.

Trecho de [`loops/router.py`](../backend/app/loops/router.py#L1027):

```python
accounts, auto_folders = await _selected_with_folders(
    access.workspace.id, payload.account_ids, payload.auto_folder_ids, db
)
media = await _validate_selected_media(
    access.workspace.id, payload.media_ids, payload.post_type, db
)
...
_save_loop_accounts(loop, accounts, db)
_save_loop_media(loop, media, db)
...
await enqueue_loop_publications_now(db, loop, accounts, now=now)
```

O pool de mídia tem ordem estável por `created_at` e ID. Em `reels` só entram
vídeos; em `images`, só imagens; em `both`, os dois tipos. A opção de repetição
faz o ciclo voltar ao início depois da última mídia. Uma nova publicação de
uma conta só avança a posição dessa conta depois de confirmada pela Meta.

Modelos relevantes em [`instagram_loop.py`](../backend/app/models/instagram_loop.py):

| Tabela / modelo | Papel |
|---|---|
| `instagram_loops` / `InstagramLoop` | Configuração do loop e `auto_folder_ids` |
| `instagram_loop_accounts` / `InstagramLoopAccount` | Associação loop-conta |
| `instagram_media` / `InstagramMedia` | Metadados do arquivo armazenado |
| `instagram_loop_media` / `InstagramLoopMedia` | Associação loop-mídia |
| `instagram_publication_jobs` / `InstagramPublicationJob` | Fila, tentativas, container e resultado |
| `instagram_loop_account_states` / `InstagramLoopAccountState` | Posição e agenda individuais por conta |

O progresso individual evita que uma conta rápida ou com falhas altere a
posição de outra. Há índice único parcial para manter no máximo um job ativo
por combinação loop/conta, além da sequência de fila.

## 7. Agendamento e publicação na API da Meta

### 7.1 Quando os jobs são enfileirados

O scheduler executa um tick a cada 60 segundos. Em cada tick ele verifica
tokens expirados, jobs interrompidos, publicações de resultado incerto, renova
tokens elegíveis e enfileira contas ativas cuja próxima execução venceu.
Loops novos ou reativados podem enfileirar imediatamente; depois, cada conta
recebe um intervalo aleatório entre os limites do loop após uma publicação
confirmada.

O enqueue não cria mais de um job ativo para a mesma conta no loop. Ele também
respeita o limite diário configurado no loop e o teto de segurança atual de
100 publicações por conta em qualquer janela móvel de 24 horas.

O serviço é iniciado junto ao processo FastAPI. No PostgreSQL, um advisory lock
impede que mais de uma instância processe o mesmo tick. Como o scheduler é
in-process, o serviço web precisa permanecer ativo para o horário ser
processado; serviço suspenso não executa ticks enquanto estiver dormindo.

Referências: [`scheduler.py` — seleção da próxima mídia e enqueue](../backend/app/loops/scheduler.py#L204),
[`scheduler_service.py` — intervalo do tick e lock](../backend/app/workers/scheduler_service.py#L1),
[`loop_scheduler.py` — execução do tick](../backend/app/workers/loop_scheduler.py#L834).

### 7.2 Etapas da chamada de publicação

Para cada job, o worker:

1. Marca o job como `publishing`, incrementa a tentativa e descriptografa o
   token da conta que autorizou aquele Instagram.
2. Confere a identidade retornada por `/me` contra o username salvo.
3. Cria URL assinada do arquivo e chama `POST /{ig-user-id}/media`. Para vídeo,
   envia `media_type=REELS`; legenda e capa são incluídas conforme o loop.
4. Para vídeo, consulta o container até `FINISHED`; `ERROR`, `EXPIRED`, status
   desconhecido ou timeout geram falha controlada.
5. Persiste `container_id` e o instante da solicitação imediatamente antes de
   `media_publish`.
6. Chama `POST /{ig-user-id}/media_publish` e grava o ID retornado.
7. Só depois da confirmação marca `published`, atualiza o horário e avança a
   posição daquela conta.

Trecho central em [`publishing.py`](../backend/app/instagram/publishing.py#L163):

```python
create_response = await _request_with_retry(
    client,
    "POST",
    f"{GRAPH_ENDPOINT}/{instagram_user_id}/media",
    data=create_payload,
)
container_id = _response_id(create_response.json())

# Para vídeo, o fluxo consulta status_code até FINISHED.
...
if before_publish is not None:
    await before_publish(container_id)
publish_response = await client.post(
    f"{GRAPH_ENDPOINT}/{instagram_user_id}/media_publish",
    data={"creation_id": container_id, "access_token": access_token},
)
```

**Por que registrar antes de `media_publish`:** a conexão pode cair depois que
a Meta publicou, mas antes de o FlashPost receber a resposta. Sem esse marcador,
um retry cego poderia duplicar o post.

### 7.3 Estados, falhas e reconciliação

Estados de job usados pelo modelo: `waiting_for_media`, `queued`, `publishing`,
`published` e `failed`. Falhas definitivas ou anteriores à solicitação de
publicação podem ser tentadas novamente até três tentativas (intervalos
progressivos de um e cinco minutos). Erro de token não segue retry normal: o
worker isola a conta com erro e ela precisa ser reconectada.

Se `media_publish` pode ter sido aceito mas a resposta não chegou, o job fica
em `publishing`. A reconciliação consulta o status do container:

- `PUBLISHED`: confirma o job sem publicar novamente;
- `FINISHED`: publica o mesmo container, que não deve ser recriado;
- `ERROR` ou `EXPIRED`: aplica a política normal de falha/retry;
- estado desconhecido ou ainda em processamento: tenta consultar novamente;
- incerteza que persiste por 24 horas: bloqueia a conta para revisão manual.

Falha de conteúdo que a Meta não poderá processar pode avançar a mídia para não
bloquear indefinidamente a conta. Nas demais falhas finais, a posição permanece
para que a conta tente a mesma mídia depois. Falhas em uma conta são registradas
individualmente e não devem interromper a fila das outras.

O worker lê `INSTAGRAM_PUBLISHING_ENABLED`. Com valor `false`, ele pode
preparar/enfileirar jobs, mas não envia publicações à Meta. Em produção, essa
flag deve ser habilitada conscientemente depois de configurar o ambiente e
validar uma conta e mídia de teste.

Referências: [`loop_scheduler.py` — tentativa e falhas](../backend/app/workers/loop_scheduler.py#L47),
[`loop_scheduler.py` — reconciliação](../backend/app/workers/loop_scheduler.py#L675),
[`scheduler.py` — avanço por publicação confirmada](../backend/app/loops/scheduler.py#L429).

## 8. Checklist operacional para implementar ou depurar

1. Confirme se a conta é profissional e se o app Meta está usando Instagram
   Login, com permissões de publicação e callback exato.
2. Em Development, confirme o papel de testador e o aceite do convite **antes**
   de iniciar OAuth; depois confirme o consentimento no login.
3. Verifique a associação da conta ao workspace, app credencial, estado e
   vencimento do token. Não copie nem imprima token em logs.
4. Para classificação automática, confira username, prefixos normalizados,
   `auto_enabled`, pasta escolhida e se o loop observa o ID daquela pasta.
5. Confirme que a conta está conectada, não expirada, pertence ao workspace e
   está associada ao loop. Confira o estado individual da conta.
6. Valide o upload e os metadados; verifique que o arquivo permanece no bucket
   privado e que o backend consegue emitir uma URL assinada.
7. Confirme que o loop está ativo, tem mídia compatível, intervalo válido, sem
   limite diário alcançado, e que o worker está em execução.
8. Verifique `INSTAGRAM_PUBLISHING_ENABLED`. Se desligado, jobs não serão
   enviados, mesmo que o loop esteja ativo.
9. Em uma resposta incerta após `media_publish`, confira o estado do container
   e do job antes de qualquer intervenção manual. Não recrie o job nem publique
   a mesma mídia às cegas.

## 9. Fontes de código

- Frontend: [`ConnectAccountModal.tsx`](../frontend/src/components/ConnectAccountModal.tsx),
  [`LoopsPage.tsx`](../frontend/src/pages/LoopsPage.tsx),
  [`ProfileFoldersPage.tsx`](../frontend/src/pages/ProfileFoldersPage.tsx).
- Backend OAuth: [`router.py`](../backend/app/instagram/router.py),
  [`oauth.py`](../backend/app/instagram/oauth.py),
  [`instagram_account.py`](../backend/app/models/instagram_account.py).
- Pastas: [`folders_router.py`](../backend/app/instagram/folders_router.py),
  [`folder_automation.py`](../backend/app/instagram/folder_automation.py).
- Mídia/publicação: [`media_router.py`](../backend/app/instagram/media_router.py),
  [`storage.py`](../backend/app/instagram/storage.py),
  [`publishing.py`](../backend/app/instagram/publishing.py).
- Loop/worker: [`router.py`](../backend/app/loops/router.py),
  [`scheduler.py`](../backend/app/loops/scheduler.py),
  [`instagram_loop.py`](../backend/app/models/instagram_loop.py),
  [`loop_scheduler.py`](../backend/app/workers/loop_scheduler.py),
  [`scheduler_service.py`](../backend/app/workers/scheduler_service.py).

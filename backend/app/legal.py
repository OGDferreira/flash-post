from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public information"])
_SUPPORT_EMAIL = "lucassantosdz111@gmail.com"
_LAST_UPDATED = "3 de outubro de 2026"

_STYLE = """
<style>
  :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #f5f7fb; background: #070809; }
  * { box-sizing: border-box; }
  body { margin: 0; min-width: 320px; line-height: 1.65; }
  main { width: min(100% - 32px, 820px); margin: 48px auto; padding: 32px; border: 1px solid #202838; border-radius: 16px; background: #0d1015; }
  header { margin-bottom: 32px; padding-bottom: 20px; border-bottom: 1px solid #202838; }
  .brand { color: #f5f7fb; font-weight: 700; letter-spacing: -.04em; text-decoration: none; }
  .brand span, a { color: #8295ff; }
  h1 { margin: 22px 0 8px; font-size: clamp(28px, 5vw, 38px); line-height: 1.15; letter-spacing: -.045em; }
  h2 { margin: 28px 0 8px; font-size: 19px; letter-spacing: -.02em; }
  p, li { color: #b6c0d1; }
  li + li { margin-top: 8px; }
  a { overflow-wrap: anywhere; }
  .updated, footer { color: #8793a7; font-size: 13px; }
  .notice { padding: 14px 16px; border: 1px solid #27334a; border-radius: 10px; background: #10141b; }
  footer { margin-top: 36px; padding-top: 18px; border-top: 1px solid #202838; }
  @media (max-width: 600px) { main { margin: 16px auto; padding: 22px 18px; } }
</style>
"""

_PAGES = {
    "privacy": """
      <h1>Política de Privacidade</h1>
      <p class="updated">Última atualização: {updated}</p>
      <p>Esta política explica como o FlashPost trata informações quando você usa o serviço. O FlashPost está em desenvolvimento e os recursos disponíveis podem mudar conforme novos módulos forem lançados.</p>
      <h2>Informações tratadas</h2>
      <ul>
        <li><strong>Cadastro e perfil:</strong> nome, e-mail, apelido público e, se informado, URL de imagem de perfil.</li>
        <li><strong>Workspace:</strong> identificador do workspace, participação e função de acesso.</li>
        <li><strong>Segurança da sessão:</strong> cookie de sessão protegido e informações técnicas necessárias para autenticação e proteção contra abuso.</li>
        <li><strong>Aplicativos Meta do workspace:</strong> App IDs, nomes internos e App Secrets informados pelo OWNER. Os segredos são criptografados no servidor e não são retornados ao navegador após serem salvos.</li>
        <li><strong>Conta profissional do Instagram conectada:</strong> identificador, nome de usuário, URL da foto de perfil, contagens de seguidores e publicações retornadas na autorização, validade do acesso e token OAuth. O token é armazenado criptografado e usado para manter a conexão autorizada.</li>
      </ul>
      <h2>Como usamos as informações</h2>
      <p>Usamos essas informações para autenticar usuários, operar workspaces, proteger o serviço e permitir que um OWNER configure seu próprio aplicativo Meta e conecte contas profissionais do Instagram. O FlashPost oferece publicação por Loop, métricas operacionais de publicações e exibe as contagens de seguidores e publicações retornadas no momento da autorização. Métricas de Insights da Meta, como impressões, alcance e interações, ainda não são consultadas.</p>
      <h2>Compartilhamento e serviços de terceiros</h2>
      <p>Quando você inicia uma conexão com o Instagram, o navegador é direcionado à Meta para autenticação e consentimento. A Meta trata dados conforme seus próprios termos e políticas. O FlashPost não vende informações pessoais. Dados podem ser processados pelos provedores de hospedagem e banco de dados necessários para operar o serviço.</p>
      <h2>Armazenamento e segurança</h2>
      <p>O FlashPost aplica controles de acesso por workspace e criptografa segredos de aplicativos e tokens de acesso antes de armazená-los. Nenhum sistema pode garantir segurança absoluta. Não compartilhe senhas, App Secrets ou tokens em mensagens de suporte.</p>
      <h2>Retenção e exclusão</h2>
      <p>As informações são mantidas enquanto a conta ou a conexão correspondente estiver ativa e pelo tempo necessário para atender obrigações legítimas ou legais. Para solicitar acesso, correção ou exclusão de dados pessoais, escreva para <a href="mailto:{email}">{email}</a>, usando o assunto “Privacidade e dados — FlashPost”. Inclua o e-mail da conta FlashPost e descreva o pedido; não envie senha, App Secret ou token. A equipe poderá solicitar confirmação razoável de identidade antes de processar a solicitação.</p>
      <p>Para remover uma conexão do Instagram, o OWNER pode usar “Desconectar” na aba Contas. Para excluir a conta FlashPost e dados associados, use o canal de contato acima; a exclusão de conta ainda é processada mediante solicitação, não por um botão de autoatendimento.</p>
      <h2>Contato</h2>
      <p>Dúvidas ou solicitações de privacidade: <a href="mailto:{email}">{email}</a>.</p>
    """,
    "terms": """
      <h1>Termos de Serviço</h1>
      <p class="updated">Última atualização: {updated}</p>
      <p>Estes termos se aplicam ao uso do FlashPost. Ao criar uma conta ou utilizar o serviço, você concorda com estas condições. Se não concordar, não utilize o serviço.</p>
      <h2>O serviço</h2>
      <p>O FlashPost está em desenvolvimento e oferece contas, workspaces, publicação por Loop e métricas operacionais básicas. Recursos podem estar indisponíveis, em teste ou ser alterados. Métricas de Insights da Meta dependem da elegibilidade da conta e das permissões concedidas. Mensagens e webhooks da Meta não estão habilitados na integração atual.</p>
      <h2>Conta e segurança</h2>
      <p>Você deve fornecer informações corretas, manter suas credenciais seguras e comunicar uso não autorizado. O OWNER é responsável por gerenciar acesso ao workspace e por ações realizadas por seus membros.</p>
      <h2>Aplicativos Meta e contas Instagram</h2>
      <p>O OWNER que configurar a integração deve fornecer App IDs e App Secrets válidos de aplicativos Meta que controle e esteja autorizado a usar. Esses segredos são armazenados criptografados. Você declara ter autoridade para conectar a conta Instagram e conceder as permissões solicitadas. A conexão depende da Meta, da elegibilidade da conta e da validade do consentimento e dos tokens. Cada conta conectada permanece associada ao app usado para autorizá-la.</p>
      <p>O Instagram, a Meta e seus serviços são independentes do FlashPost e regidos pelos próprios termos e políticas. O FlashPost não é afiliado, endossado ou administrado pela Meta.</p>
      <h2>Uso permitido</h2>
      <p>Você não deve usar o serviço para violar leis, direitos de terceiros, termos da Meta ou controles de segurança; tentar acessar workspaces sem autorização; ou interferir na disponibilidade do serviço.</p>
      <h2>Desconexão e encerramento</h2>
      <p>Um OWNER pode desconectar uma conta do workspace. O FlashPost tentará revogar a autorização junto à Meta; se isso não for confirmado, a conexão local ainda será removida e o OWNER receberá instruções para concluir a revogação nas configurações do Instagram. Para solicitar encerramento da conta FlashPost e exclusão de dados, consulte <a href="/deletar">Instruções de exclusão de dados</a>.</p>
      <h2>Disponibilidade e alterações</h2>
      <p>O serviço é fornecido em desenvolvimento e pode sofrer interrupções ou alterações. Não prometemos disponibilidade contínua ou que integrações de terceiros permaneçam inalteradas.</p>
      <h2>Contato</h2>
      <p>Dúvidas sobre estes termos: <a href="mailto:{email}">{email}</a>.</p>
    """,
    "deletion": """
      <h1>Instruções de exclusão de dados</h1>
      <p class="updated">Última atualização: {updated}</p>
      <p>Você pode solicitar a exclusão dos dados associados à sua conta FlashPost e a remoção das contas profissionais do Instagram conectadas ao seu workspace.</p>
      <h2>Como solicitar</h2>
      <ol>
        <li>Envie um e-mail para <a href="mailto:{email}?subject=Exclus%C3%A3o%20de%20dados%20%E2%80%94%20FlashPost">{email}</a> com o assunto “Exclusão de dados — FlashPost”.</li>
        <li>Informe o e-mail cadastrado na conta FlashPost e o apelido público. Se souber, inclua o nome do workspace.</li>
        <li>Se deseja também remover uma conexão Instagram, indique o nome de usuário da conta. O OWNER pode, alternativamente, usar “Desconectar” na aba Contas.</li>
      </ol>
      <p class="notice"><strong>Não inclua sua senha, App Secret, token de acesso ou códigos de autenticação no e-mail.</strong> Podemos pedir confirmação razoável de identidade para proteger a conta.</p>
      <h2>O que acontece</h2>
      <p>A equipe analisa o pedido e coordena a remoção dos dados associados à conta FlashPost e das credenciais Instagram armazenadas. Informações que precisem ser mantidas para cumprir obrigações legais ou proteger direitos poderão ser retidas pelo período aplicável. A solicitação é processada pela equipe; atualmente não há exclusão de conta por autoatendimento no site.</p>
      <h2>Revogar acesso diretamente na Meta</h2>
      <p>Remover uma conexão no FlashPost não garante, por si só, a revogação da autorização mantida pela Meta. Você também pode remover o FlashPost dos aplicativos e sites conectados nas configurações da sua conta Instagram. A desconexão no FlashPost tentará revogar essa autorização e informará se a Meta confirmar a operação.</p>
      <h2>Contato</h2>
      <p>Dúvidas sobre o pedido: <a href="mailto:{email}">{email}</a>.</p>
    """,
}


def _page(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="index,follow">
    <meta name="description" content="{title} — FlashPost.">
    <meta name="theme-color" content="#070809">
    <title>{title} — FlashPost</title>
    {_STYLE}
  </head>
  <body>
    <main>
      <header>
        <a class="brand" href="/">FlashPost<span>.</span></a>
      </header>
      {body.format(updated=_LAST_UPDATED, email=_SUPPORT_EMAIL)}
      <footer>
        FlashPost · <a href="/privacidade">Privacidade</a> ·
        <a href="/termosdeuso">Termos</a> ·
        <a href="/deletar">Exclusão de dados</a>
      </footer>
    </main>
  </body>
</html>"""
    return HTMLResponse(html)


@router.get("/privacidade", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy() -> HTMLResponse:
    return _page("Política de Privacidade", _PAGES["privacy"])


@router.get("/termosdeuso", response_class=HTMLResponse, include_in_schema=False)
async def terms_of_service() -> HTMLResponse:
    return _page("Termos de Serviço", _PAGES["terms"])


@router.get("/deletar", response_class=HTMLResponse, include_in_schema=False)
async def data_deletion_instructions() -> HTMLResponse:
    return _page("Instruções de exclusão de dados", _PAGES["deletion"])

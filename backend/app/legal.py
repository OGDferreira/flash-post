from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public information"])
_SUPPORT_EMAIL = "suporte@flashpost.tech"
_LAST_UPDATED = "22 de novembro de 2026"

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
      <p>Esta Política explica como o FlashPost trata dados pessoais quando você usa a plataforma FlashPost e o FlashBot, em conformidade com a Lei Geral de Proteção de Dados (Lei nº 13.709/2018 — LGPD). Ao criar uma conta ou usar o serviço, você declara ter lido e compreendido esta Política.</p>

      <h2>Quem é o controlador</h2>
      <p>O controlador dos dados tratados na plataforma é o FlashPost, responsável por decidir como e por que os dados pessoais são tratados. Contato do Encarregado pela Proteção de Dados (DPO): <a href="mailto:{email}">{email}</a>.</p>

      <h2>Dados que tratamos</h2>
      <ul>
        <li><strong>Cadastro e perfil:</strong> nome completo, e-mail, CPF, apelido público e, se informado, URL de imagem de perfil.</li>
        <li><strong>Autenticação e segurança:</strong> senha (armazenada apenas como hash, nunca em texto), cookie de sessão protegido, registros técnicos de acesso e dados necessários para prevenir abuso e fraude.</li>
        <li><strong>Workspace e colaboração:</strong> identificador do workspace, participação, função de acesso e convites.</li>
        <li><strong>Assinaturas e pagamentos:</strong> plano contratado, situação da assinatura, valores, identificadores de transação e dados de cobrança processados pelos provedores de pagamento (PIX e cartão). Não armazenamos o número completo do cartão; esse dado é tratado diretamente pelo provedor de pagamento.</li>
        <li><strong>Aplicativos Meta do workspace:</strong> App IDs, nomes internos e App Secrets informados pelo OWNER. Os segredos são criptografados no servidor e não são devolvidos ao navegador após salvos.</li>
        <li><strong>Contas profissionais do Instagram conectadas:</strong> identificador, nome de usuário, foto de perfil, contagens de seguidores e publicações, validade do acesso e token OAuth (armazenado criptografado).</li>
        <li><strong>FlashBot (funis, vendas e automações):</strong> configurações de funis e bots, mensagens e automações do FlashBot e integrações como ManyChat; e, quando um cliente final interage com um funil/bot do OWNER, os dados que esse cliente fornece para concluir a compra ou a interação. Nessas interações o OWNER é o controlador dos dados do seu cliente e o FlashPost atua como operador.</li>
      </ul>

      <h2>Bases legais e finalidades (art. 7º da LGPD)</h2>
      <ul>
        <li><strong>Execução de contrato:</strong> criar e manter a conta, operar workspaces, publicar por Loop, processar assinaturas e pagamentos e prestar suporte.</li>
        <li><strong>Cumprimento de obrigação legal/regulatória:</strong> guarda de registros fiscais e de acesso exigidos por lei.</li>
        <li><strong>Legítimo interesse:</strong> segurança, prevenção à fraude e melhoria do serviço, sempre respeitando seus direitos.</li>
        <li><strong>Consentimento:</strong> cookies não essenciais e comunicações opcionais. Você pode revogar o consentimento a qualquer momento (ver <a href="/cookies">Política de Cookies</a>).</li>
      </ul>

      <h2>Compartilhamento e operadores</h2>
      <p>O FlashPost <strong>não vende</strong> dados pessoais. Compartilhamos dados apenas com operadores necessários para prestar o serviço: provedor de hospedagem/infraestrutura (VPS), provedor de banco de dados e armazenamento (Supabase), provedores de pagamento (PIX e Stripe) e a Meta/Instagram quando você inicia uma conexão. Cada terceiro trata os dados conforme os próprios termos e políticas.</p>

      <h2>Transferência internacional</h2>
      <p>Alguns provedores podem processar dados fora do Brasil. Nesses casos, buscamos provedores que ofereçam garantias adequadas de proteção, conforme a LGPD.</p>

      <h2>Armazenamento e segurança</h2>
      <p>Aplicamos controle de acesso por workspace, criptografia de segredos e tokens, senhas apenas como hash, cabeçalhos de segurança, limitação de tentativas e registro de eventos. Nenhum sistema é 100% seguro. Nunca compartilhe senha, App Secret ou token em mensagens de suporte.</p>

      <h2>Retenção e exclusão</h2>
      <p>Mantemos os dados enquanto a conta ou a conexão estiver ativa e pelo prazo necessário para cumprir obrigações legais. Depois disso, os dados são excluídos ou anonimizados.</p>

      <h2>Seus direitos como titular (art. 18 da LGPD)</h2>
      <p>Você pode solicitar, a qualquer momento: confirmação de tratamento; acesso aos dados; correção de dados incompletos ou desatualizados; anonimização, bloqueio ou eliminação de dados desnecessários; portabilidade; informação sobre compartilhamento; e revogação do consentimento. Para exercer esses direitos, escreva para <a href="mailto:{email}">{email}</a> com o assunto “Privacidade e dados — FlashPost”, informando o e-mail da conta. Podemos pedir confirmação razoável de identidade antes de atender. Para excluir a conta, veja as <a href="/deletar">Instruções de exclusão de dados</a>.</p>

      <h2>Cookies</h2>
      <p>Usamos cookies essenciais e, com seu consentimento, cookies não essenciais. Detalhes e como gerenciar na <a href="/cookies">Política de Cookies</a>.</p>

      <h2>Contato e Encarregado (DPO)</h2>
      <p>Dúvidas ou solicitações de privacidade: <a href="mailto:{email}">{email}</a>.</p>
    """,
    "terms": """
      <h1>Termos de Serviço</h1>
      <p class="updated">Última atualização: {updated}</p>
      <p>Estes termos se aplicam ao uso do FlashPost. Ao criar uma conta ou utilizar o serviço, você concorda com estas condições. Se não concordar, não utilize o serviço.</p>
      <h2>O serviço</h2>
      <p>O FlashPost está em desenvolvimento e oferece contas, workspaces, publicação por Loop e métricas operacionais básicas. Recursos podem estar indisponíveis, em teste ou ser alterados. Métricas de Insights da Meta dependem da elegibilidade da conta e das permissões concedidas. Mensagens e webhooks da Meta não estão habilitados na integração atual.</p>
      <h2>Conta e segurança</h2>
      <p>Você deve fornecer informações corretas, manter suas credenciais seguras e comunicar uso não autorizado. O OWNER é responsável por gerenciar acesso ao workspace e por ações realizadas por seus membros. O cadastro pode exigir confirmação de e-mail antes da liberação da conta.</p>
      <h2>Assinaturas e pagamentos</h2>
      <p>O acesso a recursos pagos depende de assinatura ativa. Os preços, periodicidade e condições são exibidos na contratação. Os pagamentos são processados por provedores externos (PIX e cartão via Stripe); o FlashPost não armazena os dados completos do cartão. A falta de pagamento pode suspender ou encerrar o acesso. Cancelamentos e eventuais reembolsos seguem as condições informadas no momento da contratação e a legislação aplicável, incluindo o Código de Defesa do Consumidor.</p>
      <h2>FlashBot, funis e vendas</h2>
      <p>O FlashBot permite criar funis, bots, automações e cobranças. O OWNER é o único responsável pelo conteúdo que publica, pelos produtos e serviços que vende, pelas mensagens automáticas e por cumprir as leis aplicáveis e os termos das plataformas integradas (Meta, Instagram, ManyChat, provedores de pagamento). Ao usar o FlashBot para tratar dados de seus clientes finais, o OWNER atua como controlador desses dados e o FlashPost como operador. É proibido usar o serviço para conteúdo ilícito, fraude, spam ou violação de direitos de terceiros.</p>
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
    "cookies": """
      <h1>Política de Cookies</h1>
      <p class="updated">Última atualização: {updated}</p>
      <p>Esta Política explica como o FlashPost e o FlashBot usam cookies e tecnologias semelhantes (como armazenamento local no navegador). Ela complementa a <a href="/privacidade">Política de Privacidade</a> e segue a LGPD.</p>

      <h2>O que são cookies</h2>
      <p>Cookies são pequenos arquivos guardados no seu navegador. Também usamos o armazenamento local (localStorage/sessionStorage) para lembrar preferências e manter sua sessão. Neste texto, “cookies” abrange essas tecnologias.</p>

      <h2>Categorias que usamos</h2>
      <ul>
        <li><strong>Essenciais (sempre ativos):</strong> necessários para você entrar, manter a sessão autenticada, proteger contra fraude (CSRF e limitação de tentativas) e fazer o serviço funcionar. Sem eles, a plataforma não opera. Não dependem de consentimento.</li>
        <li><strong>Funcionais (opcionais):</strong> lembram preferências como tema, última tela usada e ajustes de interface, para a sua conveniência.</li>
        <li><strong>Analíticos/de desempenho (opcionais):</strong> ajudam a entender o uso de forma agregada para melhorar o serviço.</li>
      </ul>
      <p>Os cookies opcionais só são ativados com o seu consentimento (opt-in). Enquanto você não aceitar, apenas os cookies essenciais são usados.</p>

      <h2>Como gerenciar o consentimento</h2>
      <p>Ao acessar o FlashPost ou o FlashBot, um aviso permite <strong>Aceitar</strong> ou usar <strong>Apenas essenciais</strong>. Você pode mudar sua escolha a qualquer momento limpando os dados do site no navegador ou acionando novamente o aviso de cookies. Você também pode bloquear ou apagar cookies nas configurações do seu navegador — nesse caso, algumas funções podem não funcionar corretamente.</p>

      <h2>Cookies de terceiros</h2>
      <p>Ao usar integrações (Meta/Instagram, provedores de pagamento), esses serviços podem definir seus próprios cookies, regidos pelas respectivas políticas. Não controlamos esses cookies de terceiros.</p>

      <h2>Contato</h2>
      <p>Dúvidas sobre cookies e privacidade: <a href="mailto:{email}">{email}</a>.</p>
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
        <a href="/cookies">Cookies</a> ·
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


@router.get("/cookies", response_class=HTMLResponse, include_in_schema=False)
async def cookie_policy() -> HTMLResponse:
    return _page("Política de Cookies", _PAGES["cookies"])


@router.get("/deletar", response_class=HTMLResponse, include_in_schema=False)
async def data_deletion_instructions() -> HTMLResponse:
    return _page("Instruções de exclusão de dados", _PAGES["deletion"])

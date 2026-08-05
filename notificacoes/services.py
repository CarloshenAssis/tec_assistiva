"""
Envio de notificações — WhatsApp e Email (RF016, docs/PLANO_DOMINIO_ATIVOS.md §10).

Nesta fase não há credenciais de um provedor real (WhatsApp Business API /
SMTP) configuradas, então o "envio" é feito por um backend de log
estruturado — a operação de negócio (registrar e tentar enviar a
notificação) já fica completa e testável, e trocar por um provedor real é
um ponto de extensão isolado em `_despachar()`, sem tocar em
`ativos.services` nem nas views. Falha aqui nunca bloqueia o fluxo
principal de empréstimo/devolução (RNF016).
"""

import logging

from django.utils import timezone

from notificacoes.models import NotificacaoEnviada, NotificacaoTemplate

logger = logging.getLogger("notificacoes")


def renderizar_corpo(template: NotificacaoTemplate, contexto: dict) -> str:
    """Substitui as variáveis de `template.corpo_texto` pelos valores de `contexto`.

    Se `contexto` não cobrir todas as variáveis usadas no texto (template
    mal cadastrado, ou variável nova ainda não propagada por todos os
    chamadores), devolve o texto bruto em vez de estourar — perde a
    substituição, mas não derruba o envio.

    Args:
        template: Template cujo `corpo_texto` será renderizado.
        contexto: Dicionário com os valores das variáveis (`beneficiario`,
            `ativo`, `codigo`, `data_prevista`, `dias`).

    Returns:
        O texto com as variáveis substituídas, ou `template.corpo_texto`
        sem alteração se faltar alguma variável no `contexto`.
    """
    try:
        return template.corpo_texto.format(**contexto)
    except (KeyError, IndexError):
        return template.corpo_texto


def _despachar(notificacao: NotificacaoEnviada) -> bool:
    """
    Backend "log" — ponto de extensão para um provedor real (Meta Cloud
    API/Twilio para WhatsApp, SMTP para Email). Retorna True em sucesso.

    O log registra apenas identificadores internos. O destinatário (telefone
    ou e-mail) e o corpo renderizado (que traz nome do beneficiário e do
    equipamento) são dados pessoais: colocá-los aqui criaria uma segunda base
    de dados pessoais, sem controle de acesso e sem prazo de retenção, na
    saída padrão da aplicação — que na Vercel é coletada e fica retida fora
    do nosso controle. O conteúdo enviado continua disponível no próprio
    registro `NotificacaoEnviada`, que é tenant-scoped e auditável.

    Args:
        notificacao: O registro já criado (mas ainda não marcado como
            enviado) a despachar.

    Returns:
        `True` em sucesso. Este backend de log nunca falha por conta
        própria — falhas de um provedor real devem ser propagadas como
        exceção, capturada por `enviar`.
    """
    logger.info(
        "[notificação %s] envio #%s via %s",
        notificacao.template.tipo,
        notificacao.pk,
        notificacao.canal,
    )
    return True


def enviar(notificacao: NotificacaoEnviada) -> NotificacaoEnviada:
    """Despacha uma notificação já criada e grava o resultado (RNF016).

    Falha de despacho — inclusive uma exceção do backend — nunca propaga
    para o chamador: é capturada, logada e traduzida em `status=FALHOU`.
    O fluxo principal de empréstimo/devolução não pode ser bloqueado por
    uma notificação que não saiu.

    Args:
        notificacao: O registro já persistido a despachar.

    Returns:
        A mesma instância de `notificacao`, com `status`, `tentativas` e
        `enviado_em` atualizados e já salvos no banco.
    """
    sucesso = False
    try:
        sucesso = _despachar(notificacao)
    except Exception:
        logger.exception("Falha ao despachar notificação %s", notificacao.pk)
    notificacao.tentativas += 1
    if sucesso:
        notificacao.status = NotificacaoEnviada.Status.ENVIADO
        notificacao.enviado_em = timezone.now()
    else:
        notificacao.status = NotificacaoEnviada.Status.FALHOU
    notificacao.save(update_fields=["status", "tentativas", "enviado_em"])
    return notificacao


def criar_e_enviar(tenant, beneficiario, tipo: str, contexto: dict, movimentacao=None) -> list:
    """Cria e despacha uma notificação em cada canal disponível do beneficiário.

    Não faz nada (silenciosamente) se o tenant não tiver um template
    cadastrado para o `tipo` — RF017 permite que a instituição desative um
    tipo de aviso simplesmente não o cadastrando. Da mesma forma, um
    beneficiário sem WhatsApp nem e-mail cadastrados não gera nenhum envio.

    Args:
        tenant: Tenant do beneficiário, gravado em cada `NotificacaoEnviada`.
        beneficiario: Beneficiário a notificar; seus campos `whatsapp`/
            `email` (quando preenchidos) definem os canais disparados.
        tipo: Um dos valores de `NotificacaoTemplate.Tipo`.
        contexto: Variáveis para `renderizar_corpo` (ver
            `NotificacaoTemplate.corpo_texto.help_text`).
        movimentacao: Empréstimo relacionado, se houver — associado a cada
            `NotificacaoEnviada` criada e usado por `ja_notificado_hoje`
            para distinguir avisos de empréstimos diferentes no mesmo dia.

    Returns:
        Lista das instâncias de `NotificacaoEnviada` criadas e já
        despachadas (uma por canal disponível), vazia se não havia
        template ou nenhum canal cadastrado.
    """
    template = NotificacaoTemplate.objects.filter(tipo=tipo).first()
    if template is None:
        return []

    corpo = renderizar_corpo(template, contexto)
    canais = []
    if beneficiario.whatsapp:
        canais.append((NotificacaoEnviada.Canal.WHATSAPP, beneficiario.whatsapp))
    if beneficiario.email:
        canais.append((NotificacaoEnviada.Canal.EMAIL, beneficiario.email))

    enviadas = []
    for canal, destinatario in canais:
        notificacao = NotificacaoEnviada.objects.create(
            tenant=tenant,
            movimentacao=movimentacao,
            beneficiario=beneficiario,
            template=template,
            canal=canal,
            destinatario=destinatario,
            corpo_renderizado=corpo,
        )
        enviadas.append(enviar(notificacao))
    return enviadas


def ja_notificado_hoje(beneficiario, tipo: str, movimentacao=None) -> bool:
    """Verifica se já existe envio de `tipo` para `beneficiario` hoje.

    É a peça que torna `notificacoes.jobs.executar_verificacao_diaria`
    seguro para rodar mais de uma vez no mesmo dia: evita reenviar o mesmo
    aviso (ex.: "em atraso") a cada execução do job diário, sem precisar de
    nenhum controle externo de "já rodei hoje".

    Args:
        beneficiario: Beneficiário a checar.
        tipo: Um dos valores de `NotificacaoTemplate.Tipo`.
        movimentacao: Se informado, restringe a checagem a este empréstimo
            — permite que empréstimos diferentes do mesmo beneficiário
            recebam avisos independentes no mesmo dia.

    Returns:
        `True` se já existe `NotificacaoEnviada` com esse `tipo` para esse
        beneficiário (e, se informado, essa `movimentacao`) criada hoje.
    """
    hoje = timezone.now().date()
    qs = NotificacaoEnviada.objects.filter(
        beneficiario=beneficiario, template__tipo=tipo, criado_em__date=hoje
    )
    if movimentacao is not None:
        qs = qs.filter(movimentacao=movimentacao)
    return qs.exists()

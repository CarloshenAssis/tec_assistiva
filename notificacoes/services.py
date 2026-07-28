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
    try:
        return template.corpo_texto.format(**contexto)
    except (KeyError, IndexError):
        return template.corpo_texto


def _despachar(notificacao: NotificacaoEnviada) -> bool:
    """
    Backend "log" — ponto de extensão para um provedor real (Meta Cloud
    API/Twilio para WhatsApp, SMTP para Email). Retorna True em sucesso.
    """
    logger.info(
        "[notificação %s] para %s via %s: %s",
        notificacao.template.tipo,
        notificacao.destinatario,
        notificacao.canal,
        notificacao.corpo_renderizado,
    )
    return True


def enviar(notificacao: NotificacaoEnviada) -> NotificacaoEnviada:
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
    """
    Cria e despacha uma notificação em cada canal disponível do
    beneficiário (WhatsApp/Email). Não faz nada (silenciosamente) se o
    tenant não tiver um template cadastrado para o `tipo` — RF017 permite
    que a instituição desative um tipo de aviso simplesmente não o
    cadastrando.
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
    """Evita reenviar o mesmo aviso (ex.: 'em atraso') a cada execução do job diário."""
    hoje = timezone.now().date()
    qs = NotificacaoEnviada.objects.filter(
        beneficiario=beneficiario, template__tipo=tipo, criado_em__date=hoje
    )
    if movimentacao is not None:
        qs = qs.filter(movimentacao=movimentacao)
    return qs.exists()

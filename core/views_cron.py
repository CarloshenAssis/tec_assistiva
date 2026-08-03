"""
Endpoints acionados pelo Vercel Cron (`vercel.json`).

A Vercel não executa management commands agendados — cron na Vercel é
sempre uma requisição HTTP a uma rota, no horário configurado. Por isso o
job diário de notificações (`notificacoes/jobs.py`) precisa de uma porta de
entrada HTTP além do `manage.py enviar_notificacoes_diarias`.

Autenticação: não é usuário logado (quem chama é a infraestrutura da
Vercel, não uma sessão de navegador), então a proteção é um segredo
compartilhado — a Vercel envia automaticamente `Authorization: Bearer
<CRON_SECRET>` nas requisições de cron quando a env var `CRON_SECRET` está
configurada no projeto (https://vercel.com/docs/cron-jobs/manage-cron-jobs
#securing-cron-jobs). Sem `CRON_SECRET` configurado, o endpoint recusa
qualquer chamada — nunca roda "aberto" por omissão de configuração.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_GET

from notificacoes.jobs import executar_verificacao_diaria

logger = logging.getLogger(__name__)


def _autorizado(request) -> bool:
    """Confere o segredo compartilhado enviado pela Vercel Cron.

    Args:
        request: A requisição HTTP recebida.

    Returns:
        `True` se `settings.CRON_SECRET` estiver configurado e o
        cabeçalho `Authorization` da requisição corresponder a
        `Bearer <CRON_SECRET>`. `False` caso contrário — inclusive
        quando `CRON_SECRET` não está configurado, para nunca rodar
        "aberto" por omissão de configuração.
    """
    segredo = getattr(settings, "CRON_SECRET", "")
    if not segredo:
        return False
    return request.META.get("HTTP_AUTHORIZATION") == f"Bearer {segredo}"


@require_GET
def notificacoes_diarias(request):
    """Endpoint acionado pelo cron da Vercel para o job diário de notificações.

    Args:
        request: A requisição GET enviada pela infraestrutura da Vercel.

    Returns:
        `HttpResponseForbidden` (403) se a requisição não trouxer o
        segredo correto. Caso contrário, `JsonResponse` com
        `{"notificacoes_enviadas": <total>}` após executar
        `notificacoes.jobs.executar_verificacao_diaria`.
    """
    if not _autorizado(request):
        return HttpResponseForbidden("Não autorizado.")

    total = executar_verificacao_diaria()
    logger.info("Job de notificações diárias via cron: %s enviada(s).", total)
    return JsonResponse({"notificacoes_enviadas": total})

"""
Lógica do job diário de verificação de vencimentos — Fluxo 3 de
docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §4.1 ("Verificação Diária de
Vencimentos").

Isolada aqui (em vez de só no management command) para ter dois pontos de
disparo sem duplicar a regra de negócio: `manage.py
enviar_notificacoes_diarias` (execução manual/local) e o endpoint de cron
(`core.views_cron`, chamado pelo Vercel Cron em produção — Vercel não
executa management commands, só faz requisição HTTP a uma rota agendada).
"""

from __future__ import annotations

from django.utils import timezone

from ativos.domain.enums import StatusAtivo
from ativos.models import DetalheEmprestimo
from core.models import Tenant
from core.tenancy import reset_current_tenant_id, set_current_tenant_id
from notificacoes.services import criar_e_enviar, ja_notificado_hoje


def executar_verificacao_diaria() -> int:
    """Percorre todos os tenants ativos e dispara os avisos de vencimento do dia.

    Idempotência: seguro rodar mais de uma vez no mesmo dia (ex.: um retry
    do cron, ou disparo manual depois da execução automática). Quem garante
    isso é `notificacoes.services.ja_notificado_hoje`, checado por
    empréstimo antes de criar cada notificação — uma segunda passada no
    mesmo dia não encontra nada novo a enviar para quem já foi notificado.
    Isolar por tenant via `set_current_tenant_id`/`reset_current_tenant_id`
    garante que a consulta de empréstimos de um tenant nunca vaza para o
    próximo da lista.

    Returns:
        Total de notificações efetivamente criadas e despachadas na
        execução (soma de todos os tenants, todos os canais).
    """
    hoje = timezone.now().date()
    total_enviadas = 0

    for tenant in Tenant.objects.filter(ativo=True):
        token = set_current_tenant_id(tenant.pk)
        try:
            total_enviadas += _processar_tenant(tenant, hoje)
        finally:
            reset_current_tenant_id(token)

    return total_enviadas


def _processar_tenant(tenant, hoje) -> int:
    """Verifica os empréstimos em aberto de um tenant e dispara os avisos cabíveis.

    Classifica cada empréstimo em aberto pela distância até
    `data_prevista_devolucao`: exatamente 7 dias antes dispara
    `aviso_7_dias`, o dia do vencimento dispara `vencimento`, e qualquer dia
    depois dispara `atraso` (repetido a cada execução enquanto o atraso
    persistir — `ja_notificado_hoje` só evita duplicar o aviso *do mesmo
    dia*, não os de dias diferentes). Fora dessas janelas, o empréstimo é
    ignorado nesta execução.

    Args:
        tenant: O tenant sendo processado (já ativo como tenant corrente
            via `set_current_tenant_id`, chamado por `executar_verificacao_diaria`).
        hoje: Data de referência (`timezone.now().date()`), usada para
            calcular a distância até o vencimento e a checagem de "já
            notificado hoje".

    Returns:
        Quantidade de notificações criadas e despachadas para este tenant.
    """
    enviadas = 0
    detalhes = DetalheEmprestimo.objects.filter(
        movimentacao__ativo__status=StatusAtivo.EMPRESTADO.value
    ).select_related("movimentacao__ativo__categoria", "beneficiario")

    for detalhe in detalhes:
        dias = (detalhe.data_prevista_devolucao - hoje).days
        if dias == 7:
            tipo = "aviso_7_dias"
        elif dias == 0:
            tipo = "vencimento"
        elif dias < 0:
            tipo = "atraso"
        else:
            continue

        beneficiario = detalhe.beneficiario
        if ja_notificado_hoje(beneficiario, tipo, detalhe.movimentacao):
            continue

        ativo = detalhe.movimentacao.ativo
        contexto = {
            "beneficiario": beneficiario.nome,
            "ativo": ativo.categoria.nome,
            "codigo": ativo.patrimonio,
            "data_prevista": detalhe.data_prevista_devolucao.strftime("%d/%m/%Y"),
            "dias": abs(dias),
        }
        enviadas += len(criar_e_enviar(tenant, beneficiario, tipo, contexto, detalhe.movimentacao))

    return enviadas

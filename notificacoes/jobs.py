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
    """Percorre todos os tenants ativos e dispara os avisos de vencimento. Devolve o total enviado."""
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

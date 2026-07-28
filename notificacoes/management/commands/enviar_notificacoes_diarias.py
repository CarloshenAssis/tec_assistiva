"""
Job diário de verificação de vencimentos — Fluxo 3 de
docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §4.1 (fluxograma "Verificação
Diária de Vencimentos").

Nesta fase roda via `manage.py enviar_notificacoes_diarias` (agendável
por cron/Celery Beat numa fase posterior — a lógica de negócio já está
isolada aqui, então trocar o agendador não exige tocar neste código).

    python manage.py enviar_notificacoes_diarias
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from ativos.domain.enums import StatusAtivo
from ativos.models import DetalheEmprestimo
from core.models import Tenant
from core.tenancy import reset_current_tenant_id, set_current_tenant_id
from notificacoes.services import criar_e_enviar, ja_notificado_hoje


class Command(BaseCommand):
    help = "Verifica empréstimos ativos e dispara avisos de 7 dias, vencimento e atraso."

    def handle(self, *args, **options):
        hoje = timezone.now().date()
        total_enviadas = 0

        for tenant in Tenant.objects.filter(ativo=True):
            token = set_current_tenant_id(tenant.pk)
            try:
                total_enviadas += self._processar_tenant(tenant, hoje)
            finally:
                reset_current_tenant_id(token)

        self.stdout.write(self.style.SUCCESS(f"{total_enviadas} notificação(ões) enviada(s)."))

    def _processar_tenant(self, tenant, hoje) -> int:
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

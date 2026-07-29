"""
Expurgo da trilha de auditoria por prazo de retenção.

A trilha também é composta de dados pessoais (identificação do usuário, IP,
qual titular foi consultado). O princípio da necessidade (LGPD Art. 6º, III)
e a limitação temporal do Art. 16 valem para ela igualmente: guardar para
sempre "por precaução" é tratamento sem finalidade definida.

Este é o único caminho pelo qual um `RegistroAuditoria` sai da base — o model
bloqueia `delete()` individual e o Admin é somente-leitura, justamente para
que a remoção seja uma operação deliberada e datada, nunca um clique.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from auditoria.models import RegistroAuditoria


class Command(BaseCommand):
    help = "Remove registros de auditoria mais antigos que o prazo de retenção."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=None,
            help="Prazo de retenção em dias (padrão: AUDITORIA_RETENCAO_DIAS do settings).",
        )
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Executa de fato. Sem esta flag, apenas informa quanto seria removido.",
        )

    def handle(self, *args, **opcoes):
        dias = opcoes["dias"] or getattr(settings, "AUDITORIA_RETENCAO_DIAS", 730)
        corte = timezone.now() - timezone.timedelta(days=dias)

        alvo = RegistroAuditoria.objects.filter(criado_em__lt=corte)
        total = alvo.count()

        if not opcoes["confirmar"]:
            # Simulação por padrão: apagar trilha de auditoria por engano de
            # digitação num parâmetro seria irreversível.
            self.stdout.write(
                f"[simulação] {total} registro(s) anteriores a "
                f"{corte:%d/%m/%Y} seriam removidos. "
                f"Use --confirmar para executar."
            )
            return

        # `QuerySet.delete()` opera em massa no banco e não chama o
        # `delete()` do model — que é bloqueado de propósito. É exatamente o
        # que queremos aqui: o expurgo é a exceção autorizada.
        removidos, _ = alvo.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"{removidos} registro(s) de auditoria anteriores a "
                f"{corte:%d/%m/%Y} removidos (retenção de {dias} dias)."
            )
        )

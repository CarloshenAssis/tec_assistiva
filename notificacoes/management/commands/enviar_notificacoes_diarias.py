"""
Job diário de verificação de vencimentos — Fluxo 3 de
docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §4.1 (fluxograma "Verificação
Diária de Vencimentos").

Execução manual/local. Em produção, o mesmo job roda via Vercel Cron
batendo em `core.views_cron.notificacoes_diarias` — a regra de negócio
fica em `notificacoes/jobs.py` para não duplicar entre os dois disparos.

    python manage.py enviar_notificacoes_diarias
"""

from django.core.management.base import BaseCommand

from notificacoes.jobs import executar_verificacao_diaria


class Command(BaseCommand):
    help = "Verifica empréstimos ativos e dispara avisos de 7 dias, vencimento e atraso."

    def handle(self, *args, **options):
        total_enviadas = executar_verificacao_diaria()
        self.stdout.write(self.style.SUCCESS(f"{total_enviadas} notificação(ões) enviada(s)."))

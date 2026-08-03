"""
Endpoint de verificação de saúde da aplicação.

Serve para monitoramento externo (uptime check, alarme) responder "o
processo está de pé e enxerga o banco?" sem precisar autenticar.

Cuidado deliberado: a resposta é mínima. Um health check verboso — versão do
Django, host do banco, variáveis de ambiente — é presente de reconhecimento
para quem está mapeando a aplicação. Aqui sai apenas o suficiente para um
monitor decidir entre "no ar" e "fora do ar".
"""

from __future__ import annotations

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def saude(request):
    """Endpoint de health check, sem autenticação.

    Args:
        request: A requisição HTTP (não autenticada).

    Returns:
        `JsonResponse` com status HTTP 200 e `{"status": "ok"}` quando a
        aplicação responde e o banco aceita consulta; HTTP 503 e
        `{"status": "indisponivel"}` caso contrário. Sem detalhe do erro
        no corpo — ele vai para o log.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 — qualquer falha de banco é "fora do ar"
        return JsonResponse({"status": "indisponivel"}, status=503)

    return JsonResponse({"status": "ok"})

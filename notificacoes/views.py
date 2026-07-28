from django.shortcuts import render

from core.decorators import tenant_required
from notificacoes.models import NotificacaoEnviada


@tenant_required
def lista(request):
    notificacoes = NotificacaoEnviada.objects.select_related("beneficiario", "template")[:200]
    return render(request, "notificacoes/lista.html", {"nav_atual": "notificacoes", "notificacoes": notificacoes})

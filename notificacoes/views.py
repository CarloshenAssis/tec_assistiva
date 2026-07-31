from django.shortcuts import render

from core.decorators import tenant_required
from core.paginacao import paginar
from notificacoes.models import NotificacaoEnviada


@tenant_required
def lista(request):
    qs = NotificacaoEnviada.objects.select_related("beneficiario", "template")
    pagina = paginar(request, qs)
    return render(
        request,
        "notificacoes/lista.html",
        {"nav_atual": "notificacoes", "notificacoes": pagina.object_list, "pagina": pagina},
    )

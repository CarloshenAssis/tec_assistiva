"""
Views de leitura do histórico de notificações enviadas.

Sem lógica de criação/envio aqui — isso é `notificacoes.jobs` e
`notificacoes.services`, disparados pelo job diário. Esta view só lista o
que já foi enviado.
"""

from django.shortcuts import render

from core.decorators import tenant_required
from core.paginacao import paginar
from core.unidades import filtrar_por_unidade
from notificacoes.models import NotificacaoEnviada


@tenant_required
def lista(request):
    """Lista, paginado, o histórico de notificações do tenant, restrito à unidade do usuário.

    Diferente de toda outra tela de listagem, esta não era filtrada por
    unidade — um Gestor/Funcionário de uma unidade via o histórico de
    notificação de beneficiários de outras unidades que ele nem enxerga em
    Beneficiários. `campo="beneficiario__unidade"` porque a notificação em
    si não tem unidade própria, quem tem é o beneficiário dela (mesma regra
    de nulo inclusivo de `beneficiarios/views.py::_no_escopo`).

    Args:
        request: A requisição autenticada (`@tenant_required` já garante
            usuário vinculado a um tenant).

    Returns:
        `HttpResponse` renderizando `notificacoes/lista.html` com a página
        corrente de `NotificacaoEnviada`.
    """
    qs = filtrar_por_unidade(
        NotificacaoEnviada.objects.select_related("beneficiario", "template"),
        request.user,
        campo="beneficiario__unidade",
        incluir_sem_unidade=True,
    )
    pagina = paginar(request, qs)
    return render(
        request,
        "notificacoes/lista.html",
        {"nav_atual": "notificacoes", "notificacoes": pagina.object_list, "pagina": pagina},
    )

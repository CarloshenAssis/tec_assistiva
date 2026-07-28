from django.shortcuts import render

from ativos.domain.enums import StatusAtivo
from ativos.models import Ativo, DetalheEmprestimo, Movimentacao
from beneficiarios.models import Beneficiario
from core.decorators import tenant_required
from notificacoes.models import NotificacaoEnviada


@tenant_required
def dashboard(request):
    contagem_por_status = [
        {"codigo": status.value, "rotulo": status.rotulo, "total": Ativo.objects.filter(status=status.value).count()}
        for status in StatusAtivo
    ]
    total_ativos = Ativo.objects.count()
    disponiveis = next((c["total"] for c in contagem_por_status if c["codigo"] == "disponivel"), 0)
    emprestados = next((c["total"] for c in contagem_por_status if c["codigo"] == "emprestado"), 0)
    manutencao = next((c["total"] for c in contagem_por_status if c["codigo"] == "manutencao"), 0)
    taxa_utilizacao = round((emprestados / total_ativos) * 100) if total_ativos else 0

    movimentacoes_recentes = (
        Movimentacao.objects.select_related("ativo", "usuario").order_by("-data_hora")[:10]
    )

    return render(
        request,
        "core/dashboard.html",
        {
            "nav_atual": "dashboard",
            "contagem_por_status": contagem_por_status,
            "total_ativos": total_ativos,
            "disponiveis": disponiveis,
            "emprestados": emprestados,
            "manutencao": manutencao,
            "taxa_utilizacao": taxa_utilizacao,
            "movimentacoes_recentes": movimentacoes_recentes,
        },
    )


@tenant_required
def relatorios(request):
    contagem_por_status = [
        {"rotulo": status.rotulo, "total": Ativo.objects.filter(status=status.value).count()}
        for status in StatusAtivo
    ]
    beneficiarios_com_emprestimo = (
        DetalheEmprestimo.objects.filter(movimentacao__ativo__status=StatusAtivo.EMPRESTADO.value)
        .values("beneficiario")
        .distinct()
        .count()
    )

    return render(
        request,
        "core/relatorios.html",
        {
            "nav_atual": "relatorios",
            "contagem_por_status": contagem_por_status,
            "total_ativos": Ativo.objects.count(),
            "total_beneficiarios": Beneficiario.objects.count(),
            "beneficiarios_com_emprestimo": beneficiarios_com_emprestimo,
            "total_notificacoes": NotificacaoEnviada.objects.count(),
        },
    )

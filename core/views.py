from django.shortcuts import redirect, render

from ativos.domain.enums import StatusAtivo
from ativos.models import Ativo, DetalheEmprestimo, Movimentacao
from ativos.selectors import resumo_cores
from beneficiarios.models import Beneficiario
from core.decorators import tenant_required
from notificacoes.models import NotificacaoEnviada


def raiz(request):
    """
    Redirecionamento inicial (`/` e destino padrão pós-login).

    Não pode apontar direto para `app:dashboard`: um usuário da plataforma
    (`is_platform_staff`, sem tenant) recebe 403 lá — a área dele é
    `owner:dashboard`. Descoberto ao testar o login da primeira conta Owner
    em produção: o redirect fixo mandava até o Owner para `/app/dashboard/`.
    """
    if not request.user.is_authenticated:
        return redirect("login")
    if request.user.is_platform_staff:
        return redirect("owner:dashboard")
    return redirect("app:dashboard")

# Rótulos do "resumo colorido" do dashboard (docs — Módulo Mapa Operacional
# de Ativos): a mesma cor identifica a situação em toda a plataforma, aqui
# como um resumo de uma linha só, sem precisar ler texto de status.
_ROTULOS_RESUMO_CORES = [
    ("azul", "disponíveis"),
    ("verde", "emprestados (ok)"),
    ("verde_claro", "vencem em breve"),
    ("amarelo", "manutenção"),
    ("vermelho_claro", "atrasados"),
    ("vermelho_medio", "atrasados"),
    ("vermelho_escuro", "atrasados"),
    ("cinza", "baixados/inativos"),
]


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

    contagem_cores = resumo_cores(Ativo.objects.all())
    resumo_colorido = [
        {"cor": cor, "rotulo": rotulo, "total": contagem_cores.get(cor, 0)}
        for cor, rotulo in _ROTULOS_RESUMO_CORES
        if contagem_cores.get(cor, 0) > 0
    ]

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
            "resumo_colorido": resumo_colorido,
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

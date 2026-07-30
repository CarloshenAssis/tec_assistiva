from django.shortcuts import redirect, render

from ativos.domain.enums import StatusAtivo
from ativos.models import Ativo, DetalheEmprestimo, Movimentacao
from ativos.selectors import (
    indicadores_por_status,
    resumo_cores_agregado,
    resumo_por_unidade,
)
from beneficiarios.models import Beneficiario
from core.decorators import tenant_required
from core.relatorios_export import (
    exportar_ativos_csv,
    exportar_beneficiarios_csv,
    exportar_movimentacoes_csv,
)
from core.unidades import filtrar_por_unidade, unidades_visiveis
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
    """
    Painel do tenant, restrito às unidades que o usuário pode ver
    (docs/business-rules/dashboard.md).

    Todos os números saem de consultas agregadas no banco — nenhuma linha de
    Ativo é trazida para a aplicação só para ser contada, e o custo não cresce
    com o tamanho do acervo. Ver `ativos.selectors.indicadores_por_status` e
    `resumo_cores_agregado`.
    """
    ativos_qs = filtrar_por_unidade(Ativo.objects.all(), request.user)

    por_status = indicadores_por_status(ativos_qs)
    contagem_por_status = [
        {"codigo": status.value, "rotulo": status.rotulo, "total": por_status.get(status.value, 0)}
        for status in StatusAtivo
    ]
    total_ativos = sum(por_status.values())
    disponiveis = por_status.get(StatusAtivo.DISPONIVEL.value, 0)
    emprestados = por_status.get(StatusAtivo.EMPRESTADO.value, 0)
    manutencao = por_status.get(StatusAtivo.MANUTENCAO.value, 0)
    taxa_utilizacao = round((emprestados / total_ativos) * 100) if total_ativos else 0

    movimentacoes_recentes = (
        Movimentacao.objects.filter(ativo__in=ativos_qs)
        .select_related("ativo", "usuario")
        .order_by("-data_hora")[:10]
    )

    contagem_cores = resumo_cores_agregado(ativos_qs)
    resumo_colorido = [
        {"cor": cor, "rotulo": rotulo, "total": contagem_cores.get(cor, 0)}
        for cor, rotulo in _ROTULOS_RESUMO_CORES
        if contagem_cores.get(cor, 0) > 0
    ]

    # A visão por unidade só faz sentido para quem enxerga mais de uma. Para um
    # Gestor de unidade única seria uma tabela de uma linha repetindo os
    # cartões acima.
    unidades = unidades_visiveis(request.user)
    por_unidade = resumo_por_unidade(ativos_qs) if unidades.count() > 1 else []

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
            "por_unidade": por_unidade,
            "status_destaque": [
                StatusAtivo.DISPONIVEL.value,
                StatusAtivo.EMPRESTADO.value,
                StatusAtivo.MANUTENCAO.value,
            ],
        },
    )


@tenant_required
def relatorios(request):
    ativos_qs = filtrar_por_unidade(Ativo.objects.all(), request.user)
    beneficiarios_qs = filtrar_por_unidade(
        Beneficiario.objects.all(), request.user, incluir_sem_unidade=True
    )

    por_status = indicadores_por_status(ativos_qs)
    contagem_por_status = [
        {"rotulo": status.rotulo, "total": por_status.get(status.value, 0)} for status in StatusAtivo
    ]
    beneficiarios_com_emprestimo = (
        DetalheEmprestimo.objects.filter(
            movimentacao__ativo__status=StatusAtivo.EMPRESTADO.value,
            movimentacao__ativo__in=ativos_qs,
        )
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
            "total_ativos": sum(por_status.values()),
            "total_beneficiarios": beneficiarios_qs.count(),
            "beneficiarios_com_emprestimo": beneficiarios_com_emprestimo,
            "total_notificacoes": NotificacaoEnviada.objects.count(),
            "por_unidade": resumo_por_unidade(ativos_qs),
        },
    )


@tenant_required
def relatorios_exportar_ativos(request):
    return exportar_ativos_csv(filtrar_por_unidade(Ativo.objects.all(), request.user))


@tenant_required
def relatorios_exportar_beneficiarios(request):
    beneficiarios_qs = filtrar_por_unidade(
        Beneficiario.objects.all(), request.user, incluir_sem_unidade=True
    )
    return exportar_beneficiarios_csv(beneficiarios_qs, request.tenant.rotulo_beneficiario_singular)


@tenant_required
def relatorios_exportar_movimentacoes(request):
    ativos_qs = filtrar_por_unidade(Ativo.objects.all(), request.user)
    movimentacoes_qs = Movimentacao.objects.filter(ativo__in=ativos_qs)
    return exportar_movimentacoes_csv(movimentacoes_qs)

"""
Cadastro de Unidades — Administração → Unidades
(docs/features/identificacao-patrimonial-e-unidades.md).

Restrito a Admin: cadastrar/editar/desativar unidade é decisão organizacional,
não operacional — Gestor e Funcionário usam as unidades, não as administram.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from ativos.domain.acoes import NIVEL_ADMIN
from core.decorators import nivel_hierarquico, tenant_required
from core.forms import UnidadeForm
from core.models import Unidade
from core.paginacao import paginar


def _exigir_admin(request) -> None:
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode gerenciar unidades.")


@tenant_required
def unidades_lista(request):
    _exigir_admin(request)
    unidades_qs = Unidade.objects.all().order_by("nome")
    pagina = paginar(request, unidades_qs)
    return render(
        request,
        "core/unidades_lista.html",
        {"nav_atual": "unidades", "unidades": pagina.object_list, "pagina": pagina},
    )


@tenant_required
def unidades_criar(request):
    _exigir_admin(request)
    if request.method == "POST":
        form = UnidadeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            unidade = form.save(commit=False)
            unidade.tenant = request.tenant
            unidade.save()
            messages.success(request, f"Unidade {unidade.nome} cadastrada.")
            return redirect("app:unidades:lista")
    else:
        form = UnidadeForm(initial={"ativo": True}, tenant=request.tenant)
    return render(
        request,
        "core/unidades_form.html",
        {"nav_atual": "unidades", "form": form, "titulo": "Nova unidade"},
    )


@tenant_required
def unidades_editar(request, pk):
    _exigir_admin(request)
    unidade = get_object_or_404(Unidade, pk=pk)
    if request.method == "POST":
        form = UnidadeForm(request.POST, instance=unidade, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Unidade atualizada.")
            return redirect("app:unidades:lista")
    else:
        form = UnidadeForm(instance=unidade, tenant=request.tenant)
    return render(
        request,
        "core/unidades_form.html",
        {"nav_atual": "unidades", "form": form, "titulo": f"Editar {unidade.nome}"},
    )


@tenant_required
def unidades_alternar_ativo(request, pk):
    """Ativa/desativa a unidade. Exige POST — afeta quem opera nela e o Mapa Operacional."""
    _exigir_admin(request)
    if request.method != "POST":
        raise PermissionDenied("Esta operação exige confirmação (POST).")
    unidade = get_object_or_404(Unidade, pk=pk)
    unidade.ativo = not unidade.ativo
    unidade.save()
    messages.success(request, f"Unidade {'reativada' if unidade.ativo else 'desativada'}.")
    return redirect("app:unidades:lista")

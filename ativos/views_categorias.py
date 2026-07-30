"""
Cadastro de Categorias de Ativo — Cadastros → Categorias.

Mesmo nível de `criar`/`editar` Ativo (Gestor+): categoria é pré-requisito
direto do cadastro de ativo, não uma configuração organizacional separada
como Unidade (essa sim restrita a Admin — ver core/views_unidades.py).
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from ativos.domain.acoes import NIVEL_GESTOR
from ativos.forms import CategoriaAtivoForm
from ativos.models import CategoriaAtivo
from core.decorators import nivel_hierarquico, tenant_required


def _exigir_gestor(request) -> None:
    if nivel_hierarquico(request) < NIVEL_GESTOR:
        raise PermissionDenied("Somente Gestor ou Admin podem gerenciar categorias.")


@tenant_required
def categorias_lista(request):
    _exigir_gestor(request)
    categorias = CategoriaAtivo.objects.all().order_by("nome")
    return render(
        request,
        "ativos/categorias_lista.html",
        {"nav_atual": "categorias", "categorias": categorias},
    )


@tenant_required
def categorias_criar(request):
    _exigir_gestor(request)
    if request.method == "POST":
        form = CategoriaAtivoForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            categoria = form.save(commit=False)
            categoria.tenant = request.tenant
            categoria.save()
            messages.success(request, f"Categoria {categoria.nome} cadastrada.")
            return redirect("app:ativos:categorias_lista")
    else:
        form = CategoriaAtivoForm(tenant=request.tenant)
    return render(
        request,
        "ativos/categorias_form.html",
        {"nav_atual": "categorias", "form": form, "titulo": "Nova categoria"},
    )


@tenant_required
def categorias_editar(request, pk):
    _exigir_gestor(request)
    categoria = get_object_or_404(CategoriaAtivo, pk=pk)
    if request.method == "POST":
        form = CategoriaAtivoForm(request.POST, instance=categoria, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria atualizada.")
            return redirect("app:ativos:categorias_lista")
    else:
        form = CategoriaAtivoForm(instance=categoria, tenant=request.tenant)
    return render(
        request,
        "ativos/categorias_form.html",
        {"nav_atual": "categorias", "form": form, "titulo": f"Editar {categoria.nome}"},
    )

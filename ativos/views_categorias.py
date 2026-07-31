"""
Cadastro de Categorias de Ativo — Cadastros → Categorias.

Restrito a Admin, mesmo raciocínio de Unidade (core/views_unidades.py):
categoria é taxonomia da organização inteira — vale para todas as
unidades/gestores do tenant —, não uma decisão operacional de cada
Gestor. Se cada Gestor cadastrasse a sua, o mesmo tipo de ativo viraria
duas categorias divergentes (ex.: "Cadeira de Rodas" e "cadeira rodas")
em unidades diferentes da mesma organização.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from ativos.domain.acoes import NIVEL_ADMIN
from ativos.forms import CategoriaAtivoForm, SubcategoriaAtivoForm
from ativos.models import CategoriaAtivo, SubcategoriaAtivo
from core.decorators import nivel_hierarquico, tenant_required
from core.paginacao import paginar


def _exigir_admin(request) -> None:
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode gerenciar categorias.")


@tenant_required
def categorias_lista(request):
    _exigir_admin(request)
    categorias_qs = CategoriaAtivo.objects.all().order_by("nome")
    pagina = paginar(request, categorias_qs)
    return render(
        request,
        "ativos/categorias_lista.html",
        {"nav_atual": "categorias", "categorias": pagina.object_list, "pagina": pagina},
    )


@tenant_required
def categorias_criar(request):
    _exigir_admin(request)
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
    _exigir_admin(request)
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


@tenant_required
def subcategorias_lista(request, categoria_pk):
    _exigir_admin(request)
    categoria = get_object_or_404(CategoriaAtivo, pk=categoria_pk)
    subcategorias_qs = categoria.subcategorias.all().order_by("nome")
    pagina = paginar(request, subcategorias_qs)
    return render(
        request,
        "ativos/subcategorias_lista.html",
        {
            "nav_atual": "categorias",
            "categoria": categoria,
            "subcategorias": pagina.object_list,
            "pagina": pagina,
        },
    )


@tenant_required
def subcategorias_criar(request, categoria_pk):
    _exigir_admin(request)
    categoria = get_object_or_404(CategoriaAtivo, pk=categoria_pk)
    if request.method == "POST":
        form = SubcategoriaAtivoForm(request.POST, categoria=categoria)
        if form.is_valid():
            subcategoria = form.save(commit=False)
            subcategoria.tenant = request.tenant
            subcategoria.categoria = categoria
            subcategoria.save()
            messages.success(request, f"Subcategoria {subcategoria.nome} cadastrada.")
            return redirect("app:ativos:subcategorias_lista", categoria_pk=categoria.pk)
    else:
        form = SubcategoriaAtivoForm(categoria=categoria)
    return render(
        request,
        "ativos/subcategorias_form.html",
        {"nav_atual": "categorias", "form": form, "categoria": categoria, "titulo": f"Nova subcategoria de {categoria.nome}"},
    )


@tenant_required
def subcategorias_editar(request, pk):
    _exigir_admin(request)
    subcategoria = get_object_or_404(SubcategoriaAtivo, pk=pk)
    if request.method == "POST":
        form = SubcategoriaAtivoForm(request.POST, instance=subcategoria, categoria=subcategoria.categoria)
        if form.is_valid():
            form.save()
            messages.success(request, "Subcategoria atualizada.")
            return redirect("app:ativos:subcategorias_lista", categoria_pk=subcategoria.categoria_id)
    else:
        form = SubcategoriaAtivoForm(instance=subcategoria, categoria=subcategoria.categoria)
    return render(
        request,
        "ativos/subcategorias_form.html",
        {
            "nav_atual": "categorias",
            "form": form,
            "categoria": subcategoria.categoria,
            "titulo": f"Editar {subcategoria.nome}",
        },
    )

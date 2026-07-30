"""
Cadastro de Fornecedores — Cadastros → Fornecedores.

Restrito a Admin, mesmo raciocínio de Unidade/Categoria: fornecedor é
cadastro da organização inteira (usado em aquisição e manutenção de
qualquer unidade), não uma decisão operacional de cada Gestor.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from ativos.domain.acoes import NIVEL_ADMIN
from core.decorators import nivel_hierarquico, tenant_required
from core.forms import FornecedorForm
from core.models import Fornecedor


def _exigir_admin(request) -> None:
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode gerenciar fornecedores.")


@tenant_required
def fornecedores_lista(request):
    _exigir_admin(request)
    fornecedores = Fornecedor.objects.all().order_by("nome")
    return render(
        request,
        "core/fornecedores_lista.html",
        {"nav_atual": "fornecedores", "fornecedores": fornecedores},
    )


@tenant_required
def fornecedores_criar(request):
    _exigir_admin(request)
    if request.method == "POST":
        form = FornecedorForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            fornecedor = form.save(commit=False)
            fornecedor.tenant = request.tenant
            fornecedor.save()
            messages.success(request, f"Fornecedor {fornecedor.nome} cadastrado.")
            return redirect("app:fornecedores:lista")
    else:
        form = FornecedorForm(tenant=request.tenant)
    return render(
        request,
        "core/fornecedores_form.html",
        {"nav_atual": "fornecedores", "form": form, "titulo": "Novo fornecedor"},
    )


@tenant_required
def fornecedores_editar(request, pk):
    _exigir_admin(request)
    fornecedor = get_object_or_404(Fornecedor, pk=pk)
    if request.method == "POST":
        form = FornecedorForm(request.POST, instance=fornecedor, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Fornecedor atualizado.")
            return redirect("app:fornecedores:lista")
    else:
        form = FornecedorForm(instance=fornecedor, tenant=request.tenant)
    return render(
        request,
        "core/fornecedores_form.html",
        {"nav_atual": "fornecedores", "form": form, "titulo": f"Editar {fornecedor.nome}"},
    )

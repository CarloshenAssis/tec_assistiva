"""
Cadastro de Fornecedores — Cadastros → Fornecedores.

Tela cheia restrita a Admin, mesmo raciocínio de Unidade/Categoria:
fornecedor é cadastro da organização inteira (usado em aquisição e
manutenção de qualquer unidade), não uma decisão operacional de cada
Gestor.

O link de menu para esta tela foi retirado de `templates/base.html` de
propósito — o cadastro rápido embutido no formulário de Ativo
(`fornecedor_criar_rapido`, abaixo) cobre o uso do dia a dia, e o código
desta tela continua aqui intacto (não apagado) para quem precisar editar
contato/telefone de um fornecedor já existente, via URL direta.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from ativos.domain.acoes import NIVEL_ADMIN, NIVEL_GESTOR
from core.decorators import nivel_hierarquico, tenant_required
from core.forms import FornecedorForm
from core.models import Fornecedor
from core.paginacao import paginar


def _exigir_admin(request) -> None:
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode gerenciar fornecedores.")


@tenant_required
def fornecedores_lista(request):
    _exigir_admin(request)
    fornecedores_qs = Fornecedor.objects.all().order_by("nome")
    pagina = paginar(request, fornecedores_qs)
    return render(
        request,
        "core/fornecedores_lista.html",
        {"nav_atual": "fornecedores", "fornecedores": pagina.object_list, "pagina": pagina},
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


@tenant_required
def fornecedor_criar_rapido(request):
    """Mesmo mecanismo de `ativos.views_categorias.subcategoria_criar_rapida` — ver docstring lá."""
    if nivel_hierarquico(request) < NIVEL_GESTOR:
        raise PermissionDenied("Somente Gestor ou Admin podem cadastrar ativos.")
    if request.method != "POST":
        raise PermissionDenied("Esta operação exige confirmação (POST).")

    nome = (request.POST.get("nome") or "").strip()
    if not nome:
        return JsonResponse({"erro": "Informe um nome."}, status=400)

    fornecedor = Fornecedor.objects.filter(nome__iexact=nome).first()
    if fornecedor is None:
        fornecedor = Fornecedor.objects.create(tenant=request.tenant, nome=nome)
    return JsonResponse({"id": fornecedor.pk, "nome": fornecedor.nome})

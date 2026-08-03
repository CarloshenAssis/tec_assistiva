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
    """Garante que o usuário logado seja Admin (ou nível superior).

    Args:
        request: A requisição corrente, com `request.user` autenticado.

    Raises:
        django.core.exceptions.PermissionDenied: Se o nível hierárquico
            do usuário for menor que `NIVEL_ADMIN`.
    """
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode gerenciar fornecedores.")


@tenant_required
def fornecedores_lista(request):
    """Lista paginada de fornecedores do tenant, restrita a Admin.

    Args:
        request: A requisição GET.

    Returns:
        `HttpResponse` renderizando `core/fornecedores_lista.html`.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin.
    """
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
    """Cadastro de novo fornecedor, restrito a Admin.

    Args:
        request: A requisição GET (exibe o formulário) ou POST (submete).

    Returns:
        Em GET, `HttpResponse` renderizando o formulário vazio. Em POST
        válido, redireciona para a lista de fornecedores. Em POST
        inválido, re-renderiza o formulário com os erros.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin.
    """
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
    """Edição de um fornecedor existente, restrita a Admin.

    Args:
        request: A requisição GET (exibe o formulário preenchido) ou
            POST (submete a edição).
        pk: PK do `Fornecedor` a editar.

    Returns:
        Em GET, `HttpResponse` renderizando o formulário preenchido. Em
        POST válido, redireciona para a lista de fornecedores. Em POST
        inválido, re-renderiza o formulário com os erros.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin.
        django.http.Http404: Se `pk` não corresponder a um fornecedor do
            tenant corrente.
    """
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
    """Cria (ou reaproveita) um fornecedor a partir do formulário de Ativo.

    Mesmo mecanismo de
    `ativos.views_categorias.subcategoria_criar_rapida` — ver docstring
    lá. Endpoint AJAX chamado sem sair da tela de cadastro de ativo.

    Args:
        request: Requisição POST com o campo `nome` no corpo.

    Returns:
        `JsonResponse` com `{"id": ..., "nome": ...}` do fornecedor
        (criado ou já existente com o mesmo nome, case-insensitive), ou
        HTTP 400 com `{"erro": ...}` se `nome` estiver vazio.

    Raises:
        django.core.exceptions.PermissionDenied: Se o método não for
            POST, ou se o usuário for abaixo de Gestor.
    """
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

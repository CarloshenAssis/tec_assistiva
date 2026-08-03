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
    """Garante que o usuário logado seja Admin (ou nível superior).

    Args:
        request: A requisição corrente, com `request.user` autenticado.

    Raises:
        django.core.exceptions.PermissionDenied: Se o nível hierárquico
            do usuário for menor que `NIVEL_ADMIN`.
    """
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode gerenciar unidades.")


@tenant_required
def unidades_lista(request):
    """Lista paginada de unidades do tenant, restrita a Admin.

    Args:
        request: A requisição GET.

    Returns:
        `HttpResponse` renderizando `core/unidades_lista.html`.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin.
    """
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
    """Cadastro de nova unidade, restrito a Admin.

    Args:
        request: A requisição GET (exibe o formulário) ou POST (submete).

    Returns:
        Em GET, `HttpResponse` renderizando o formulário vazio (com
        `ativo=True` pré-marcado). Em POST válido, redireciona para a
        lista de unidades. Em POST inválido, re-renderiza o formulário
        com os erros.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin.
    """
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
    """Edição de uma unidade existente, restrita a Admin.

    Args:
        request: A requisição GET (exibe o formulário preenchido) ou
            POST (submete a edição).
        pk: PK da `Unidade` a editar.

    Returns:
        Em GET, `HttpResponse` renderizando o formulário preenchido. Em
        POST válido, redireciona para a lista de unidades. Em POST
        inválido, re-renderiza o formulário com os erros.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin.
        django.http.Http404: Se `pk` não corresponder a uma unidade do
            tenant corrente.
    """
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
    """Ativa/desativa uma unidade, restrito a Admin.

    Exige POST — afeta quem opera nela e o Mapa Operacional.

    Args:
        request: A requisição POST de confirmação.
        pk: PK da `Unidade` a ativar/desativar.

    Returns:
        Redireciona para a lista de unidades após alternar o campo
        `ativo`.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin, ou se o método não for POST.
        django.http.Http404: Se `pk` não corresponder a uma unidade do
            tenant corrente.
    """
    _exigir_admin(request)
    if request.method != "POST":
        raise PermissionDenied("Esta operação exige confirmação (POST).")
    unidade = get_object_or_404(Unidade, pk=pk)
    unidade.ativo = not unidade.ativo
    unidade.save()
    messages.success(request, f"Unidade {'reativada' if unidade.ativo else 'desativada'}.")
    return redirect("app:unidades:lista")

"""
Logotipo da instituição — Administração → Instituição.

Restrito a Admin, editado no lado `/app/` (mesmo raciocínio de
`core/views_encarregado.py`): a identidade visual da etiqueta patrimonial
é decisão do próprio tenant, não da Ciclartech.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from ativos.domain.acoes import NIVEL_ADMIN
from core.arquivos import resposta_de_imagem
from core.decorators import nivel_hierarquico, tenant_required
from core.forms import LogoForm


@tenant_required
def instituicao_editar(request):
    """Formulário de configuração do logotipo do tenant, restrito a Admin.

    Args:
        request: A requisição GET (exibe o formulário), ou POST para
            enviar um novo logotipo ou removê-lo (campo `remover_logo`
            no corpo do POST).

    Returns:
        Em GET, `HttpResponse` renderizando o formulário com o logotipo
        atual, se houver. Em POST de remoção ou de envio válido,
        redireciona de volta para a mesma tela com mensagem de sucesso.
        Em POST de envio inválido, re-renderiza o formulário com os
        erros.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin.
    """
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode configurar o logotipo da instituição.")
    tenant = request.tenant

    if request.method == "POST":
        if request.POST.get("remover_logo"):
            tenant.logo.delete(save=True)
            messages.success(request, "Logotipo removido.")
            return redirect("app:instituicao")
        form = LogoForm(request.POST, request.FILES, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Logotipo atualizado.")
            return redirect("app:instituicao")
    else:
        form = LogoForm(instance=tenant)
    return render(
        request,
        "core/instituicao_form.html",
        {"nav_atual": "instituicao", "form": form, "tenant": tenant},
    )


@tenant_required
def logo_imagem(request):
    """Serve o logotipo do tenant corrente, autenticado e com cache longo.

    Substitui o link direto ao storage (`Tenant.logo.url`), pelo mesmo
    motivo de `ativos.views.foto_ativo_imagem` — ver docstring lá.

    Args:
        request: A requisição GET.

    Returns:
        `FileResponse` com a imagem, `Cache-Control` de longa duração
        (ver `core.arquivos.resposta_de_imagem`).

    Raises:
        django.http.Http404: Se o tenant não tiver logotipo configurado.
    """
    return resposta_de_imagem(request.tenant.logo)

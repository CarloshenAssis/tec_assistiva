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
from core.decorators import nivel_hierarquico, tenant_required
from core.forms import LogoForm


@tenant_required
def instituicao_editar(request):
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

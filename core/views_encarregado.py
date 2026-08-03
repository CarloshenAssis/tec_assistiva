"""
Encarregado (DPO) do tenant — Administração → Encarregado (LGPD)
(docs/POLITICA_PRIVACIDADE.md).

Restrito a Admin, e editado no lado `/app/` (não em `/owner/`): cada
tenant é controlador dos dados dos seus próprios beneficiários (a
Ciclartech é operadora da plataforma, não controladora — LGPD Art. 5º
VI/VII), então só o próprio tenant sabe quem, na organização dele, deve
responder pelas solicitações de titulares.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from ativos.domain.acoes import NIVEL_ADMIN
from core.decorators import nivel_hierarquico, tenant_required
from core.forms import EncarregadoForm


@tenant_required
def encarregado_editar(request):
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode configurar o Encarregado (DPO).")
    tenant = request.tenant
    if request.method == "POST":
        form = EncarregadoForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Encarregado (DPO) atualizado.")
            return redirect("app:encarregado")
    else:
        form = EncarregadoForm(instance=tenant)
    return render(
        request,
        "core/encarregado_form.html",
        {"nav_atual": "encarregado", "form": form, "tenant": tenant},
    )

"""
Consultas de leitura sobre a trilha de auditoria.

Usada tanto pela visão cross-tenant do Owner (`owner/views.py::auditoria`)
quanto pela visão por tenant do Admin/Gestor
(`contas/views.py::auditoria_lista`) — uma função só, parametrizada, em vez
de duas implementações de filtro que podem divergir com o tempo.
"""

from __future__ import annotations

from typing import Optional

from django.core.paginator import Page, Paginator

from auditoria.models import RegistroAuditoria
from core.paginacao import TAMANHOS_DISPONIVEIS

_ITENS_POR_PAGINA_PADRAO = 50


def listar_registros(
    *,
    tenant_id: Optional[int] = None,
    acao: str = "",
    usuario: str = "",
    somente_sensivel: bool = False,
    pagina=None,
    por_pagina=None,
) -> Page:
    """
    Página de `RegistroAuditoria`, mais recente primeiro.

    `tenant_id=None` não filtra por tenant — é o que dá ao Owner a visão
    cross-tenant; passar um id é o que restringe a visão do Admin de tenant
    ao próprio contrato. `RegistroAuditoria` usa manager padrão do Django
    (não é `TenantModel`, de propósito — ver auditoria/models.py), então o
    filtro por tenant aqui é explícito, não automático.

    `por_pagina` segue a mesma lista fechada de `core.paginacao` — valor
    ausente ou fora dela cai no padrão de 50, nunca vira "sem limite".
    """
    qs = RegistroAuditoria.objects.select_related("tenant", "usuario").all()

    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if acao:
        qs = qs.filter(acao=acao)
    if usuario:
        qs = qs.filter(usuario_identificacao__icontains=usuario)
    if somente_sensivel:
        qs = qs.filter(envolve_dado_sensivel=True)

    try:
        tamanho = int(por_pagina)
    except (TypeError, ValueError):
        tamanho = _ITENS_POR_PAGINA_PADRAO
    if tamanho not in TAMANHOS_DISPONIVEIS:
        tamanho = _ITENS_POR_PAGINA_PADRAO

    return Paginator(qs, tamanho).get_page(pagina)

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


def filtrar_registros(
    *,
    tenant_id: Optional[int] = None,
    acao: str = "",
    usuario: str = "",
    somente_sensivel: bool = False,
):
    """Monta o queryset de `RegistroAuditoria` filtrado, mais recente primeiro.

    Sem paginar de propósito. Usado tanto por `listar_registros` (tela)
    quanto pela exportação em CSV (`owner/views.py::auditoria_exportar`,
    `contas/views.py::auditoria_exportar`), que precisa de **todos** os
    registros do filtro, não só a página em exibição.

    `tenant_id=None` não filtra por tenant — é o que dá ao Owner a visão
    cross-tenant; passar um id é o que restringe a visão do Admin de tenant
    ao próprio contrato. `RegistroAuditoria` usa manager padrão do Django
    (não é `TenantModel`, de propósito — ver auditoria/models.py), então o
    filtro por tenant aqui é explícito, não automático.

    Args:
        tenant_id: Id do tenant a restringir, ou `None` para visão
            cross-tenant (Owner).
        acao: Valor de `AcaoAuditada` a filtrar, ou `""` para não filtrar.
        usuario: Trecho de `usuario_identificacao` a buscar
            (case-insensitive, `icontains`), ou `""` para não filtrar.
        somente_sensivel: Se `True`, restringe a `envolve_dado_sensivel=True`.

    Returns:
        Queryset de `RegistroAuditoria`, mais recente primeiro, com
        `tenant`/`usuario` já pré-carregados via `select_related`.
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

    return qs


def listar_registros(
    *,
    tenant_id: Optional[int] = None,
    acao: str = "",
    usuario: str = "",
    somente_sensivel: bool = False,
    pagina=None,
    por_pagina=None,
) -> Page:
    """Pagina o resultado de `filtrar_registros`, mais recente primeiro.

    `por_pagina` segue a mesma lista fechada de `core.paginacao` — valor
    ausente ou fora dela cai no padrão de 50, nunca vira "sem limite".

    Args:
        tenant_id: Repassado a `filtrar_registros`.
        acao: Repassado a `filtrar_registros`.
        usuario: Repassado a `filtrar_registros`.
        somente_sensivel: Repassado a `filtrar_registros`.
        pagina: Número da página desejada (aceita o que `Paginator.get_page`
            aceitar — inclusive `None`, que cai na primeira página).
        por_pagina: Tamanho de página desejado; validado contra
            `TAMANHOS_DISPONIVEIS`.

    Returns:
        Um `django.core.paginator.Page` com os registros da página pedida.
    """
    qs = filtrar_registros(
        tenant_id=tenant_id, acao=acao, usuario=usuario, somente_sensivel=somente_sensivel
    )

    try:
        tamanho = int(por_pagina)
    except (TypeError, ValueError):
        tamanho = _ITENS_POR_PAGINA_PADRAO
    if tamanho not in TAMANHOS_DISPONIVEIS:
        tamanho = _ITENS_POR_PAGINA_PADRAO

    return Paginator(qs, tamanho).get_page(pagina)

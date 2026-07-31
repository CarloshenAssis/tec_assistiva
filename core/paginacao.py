"""
Paginação padrão das telas de lista.

Antes disto, várias telas (Ativos, Beneficiários, Notificações) cortavam a
consulta em `[:200]` (Etiquetas em `[:500]`) sem paginação nenhuma — acima
do corte, o resto simplesmente não aparecia, sem aviso, sem link para "ver
mais". `paginar()` substitui esses cortes fixos por página de tamanho
escolhível pelo usuário.
"""

from __future__ import annotations

from django.core.paginator import Page, Paginator

#: Únicos tamanhos aceitos em `?por_pagina=` — uma lista fechada em vez de
#: aceitar qualquer inteiro: sem isso, `?por_pagina=999999` vira "traga o
#: acervo inteiro numa página só", exatamente o problema que a paginação
#: existe para evitar.
TAMANHOS_DISPONIVEIS = [10, 15, 25, 30, 50, 100]
TAMANHO_PADRAO = 25


def paginar(request, queryset, *, tamanho_padrao: int = TAMANHO_PADRAO) -> Page:
    """
    Página de `queryset` na posição de `?pagina=` e no tamanho de
    `?por_pagina=` — este último restrito a `TAMANHOS_DISPONIVEIS`; qualquer
    valor fora da lista (ausente, não numérico, ou não permitido) cai no
    padrão, nunca vira "sem limite".
    """
    try:
        tamanho = int(request.GET.get("por_pagina", tamanho_padrao))
    except (TypeError, ValueError):
        tamanho = tamanho_padrao
    if tamanho not in TAMANHOS_DISPONIVEIS:
        tamanho = tamanho_padrao

    return Paginator(queryset, tamanho).get_page(request.GET.get("pagina"))

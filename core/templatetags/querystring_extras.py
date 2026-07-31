"""
Manipular a querystring atual em links/formulários de paginação e filtro,
sem repetir `?campo1=x&campo2=y&pagina=N` na mão em cada template.
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring_trocando(context, **novos):
    """
    `{% querystring_trocando pagina=pagina.next_page_number %}` — devolve a
    querystring atual (`request.GET`) com as chaves passadas sobrepostas
    (ou removidas, se o valor for `None`). Usado nos links de "página
    anterior/seguinte" para preservar filtro/busca/tamanho de página já
    aplicados, trocando só o número da página.
    """
    request = context["request"]
    params = request.GET.copy()
    for chave, valor in novos.items():
        if valor is None:
            params.pop(chave, None)
        else:
            params[chave] = valor
    return params.urlencode()

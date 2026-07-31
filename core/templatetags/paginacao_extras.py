from django import template

from core.paginacao import TAMANHOS_DISPONIVEIS

register = template.Library()


@register.simple_tag
def tamanhos_de_pagina():
    """Única fonte de verdade da lista de opções — core/paginacao.py, não repetida no template."""
    return TAMANHOS_DISPONIVEIS

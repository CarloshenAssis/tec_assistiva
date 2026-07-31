from django import template

register = template.Library()


@register.filter
def split(valor: str, separador: str = ","):
    """`{{ "a,b,c"|split:"," }}` -> `["a", "b", "c"]` — usado em `{% if x in ...|split:"," %}`."""
    return valor.split(separador)

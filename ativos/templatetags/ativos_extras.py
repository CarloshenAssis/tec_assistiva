from django import template

register = template.Library()


@register.filter
def badge_cor(cor: str) -> str:
    """`{{ "verde_claro"|badge_cor }}` -> `badge-cor-verde_claro` (classes definidas em ciclartech.css)."""
    return f"badge-cor-{cor}"


@register.filter
def dot_cor(cor: str) -> str:
    return f"dot-cor dot-cor-{cor}"

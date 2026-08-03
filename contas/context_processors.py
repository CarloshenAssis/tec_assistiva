"""
Variáveis de contexto de template ligadas à hierarquia do usuário logado.
"""

from __future__ import annotations

from ativos.domain.acoes import NIVEL_ADMIN, NIVEL_GESTOR
from core.decorators import nivel_hierarquico


def hierarquia(request):
    """Context processor com flags de hierarquia do usuário logado.

    `pode_gerenciar_usuarios`: controla a exibição do item "Administração"
    na sidebar (templates/base.html). Gestor e Admin gerenciam gente
    (ver `Usuario.pode_gerenciar`); Funcionário não.

    `eh_admin`: controla itens exclusivos de Admin dentro desse grupo (ex.:
    "Unidades" — cadastrar unidade é decisão organizacional, não algo que
    um Gestor também faz, diferente de gerenciar usuário).

    Args:
        request: A requisição corrente.

    Returns:
        Dicionário de contexto injetado em todo template, com as chaves
        `pode_gerenciar_usuarios` e `eh_admin` — ambas `False` para
        usuário anônimo.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"pode_gerenciar_usuarios": False, "eh_admin": False}
    nivel = nivel_hierarquico(request)
    return {
        "pode_gerenciar_usuarios": nivel >= NIVEL_GESTOR,
        "eh_admin": nivel >= NIVEL_ADMIN,
    }

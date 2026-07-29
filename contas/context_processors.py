"""
Variáveis de contexto de template ligadas à hierarquia do usuário logado.
"""

from __future__ import annotations

from ativos.domain.acoes import NIVEL_ADMIN, NIVEL_GESTOR
from core.decorators import nivel_hierarquico


def hierarquia(request):
    """
    `pode_gerenciar_usuarios`: controla a exibição do item "Administração"
    na sidebar (templates/base.html). Gestor e Admin gerenciam gente
    (ver `Usuario.pode_gerenciar`); Funcionário não.

    `eh_admin`: controla itens exclusivos de Admin dentro desse grupo (ex.:
    "Unidades" — cadastrar unidade é decisão organizacional, não algo que
    um Gestor também faz, diferente de gerenciar usuário).
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"pode_gerenciar_usuarios": False, "eh_admin": False}
    nivel = nivel_hierarquico(request)
    return {
        "pode_gerenciar_usuarios": nivel >= NIVEL_GESTOR,
        "eh_admin": nivel >= NIVEL_ADMIN,
    }

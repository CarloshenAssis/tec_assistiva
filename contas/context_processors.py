"""
Variáveis de contexto de template ligadas à hierarquia do usuário logado.
"""

from __future__ import annotations

from ativos.domain.acoes import NIVEL_GESTOR
from core.decorators import nivel_hierarquico


def hierarquia(request):
    """
    `pode_gerenciar_usuarios`: controla a exibição do item "Administração"
    na sidebar (templates/base.html). Gestor e Admin gerenciam gente
    (ver `Usuario.pode_gerenciar`); Funcionário não.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"pode_gerenciar_usuarios": False}
    return {"pode_gerenciar_usuarios": nivel_hierarquico(request) >= NIVEL_GESTOR}

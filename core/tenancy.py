"""
Contexto de tenant corrente da requisição.

Implementa o isolamento multi-tenant descrito em
docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md (§3) e
docs/ESPECIFICACAO_TECNICA.md (§3.3): o tenant do usuário autenticado é
resolvido uma vez por requisição (contas.middleware.TenantMiddleware) e
exposto aqui via ContextVar, para que o `TenantManager` (models.py) filtre
automaticamente toda consulta sem que cada view precise se lembrar disso.

Importante: por padrão, "sem tenant no contexto" resulta em queryset VAZIO
(fail closed), nunca em "todos os tenants" (fail open). O acesso
intencional cross-tenant só existe via `Manager.all_tenants()`, usado
exclusivamente pelo app `owner` (área da plataforma).
"""

import contextvars
from typing import Optional

_current_tenant_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def set_current_tenant_id(tenant_id: Optional[int]) -> contextvars.Token:
    """Define o tenant corrente da requisição em andamento.

    Chamado uma única vez por requisição, por `contas.middleware.
    TenantMiddleware`, logo depois que `request.user` é resolvido.

    Args:
        tenant_id: PK do `Tenant` do usuário autenticado, ou `None` quando
            o usuário é anônimo ou é um Owner (`is_platform_staff=True`),
            que não pertence a nenhum tenant.

    Returns:
        Token opaco do `contextvars`, a ser repassado a
        `reset_current_tenant_id` ao final da requisição — garante que o
        contexto não vaze para a próxima requisição atendida pelo mesmo
        worker.
    """
    return _current_tenant_id.set(tenant_id)


def get_current_tenant_id() -> Optional[int]:
    """Devolve o `tenant_id` da requisição corrente.

    Returns:
        A PK do tenant corrente, ou `None` se não houver tenant no
        contexto (usuário anônimo, Owner, ou execução fora de uma
        requisição HTTP — shell, script, management command).
    """
    return _current_tenant_id.get()


def reset_current_tenant_id(token: contextvars.Token) -> None:
    """Limpa o tenant corrente ao final da requisição.

    Args:
        token: Token devolvido por `set_current_tenant_id`, correspondente
            a esta requisição.
    """
    _current_tenant_id.reset(token)

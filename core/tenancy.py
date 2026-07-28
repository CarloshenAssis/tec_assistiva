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


def set_current_tenant_id(tenant_id: Optional[int]):
    """Define o tenant corrente e devolve um token para reset posterior."""
    return _current_tenant_id.set(tenant_id)


def get_current_tenant_id() -> Optional[int]:
    return _current_tenant_id.get()


def reset_current_tenant_id(token) -> None:
    _current_tenant_id.reset(token)

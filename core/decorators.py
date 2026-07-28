"""
Decorador de acesso ao namespace `/app/*` (produto para os clientes).

Reforça, ao lado do isolamento automático do `TenantManager`, que apenas
usuários vinculados a um tenant acessam essas views — um `is_platform_staff`
(Owner) que por engano tente acessar `/app/*` é bloqueado aqui, e não deve
usar esta área (a dele é `/owner/*`).
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def tenant_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_platform_staff or not request.user.tenant_id:
            raise PermissionDenied("Esta área é exclusiva de usuários vinculados a um tenant.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def nivel_hierarquico(request) -> int:
    """Nível hierárquico do usuário logado (0 se não tiver papel definido)."""
    papel = getattr(request.user, "papel", None)
    return papel.nivel_hierarquico if papel else 0

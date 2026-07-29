"""
Decorador de acesso ao namespace `/owner/*` (área da equipe da plataforma).

Espelha `core.decorators.tenant_required`, na direção oposta: aqui só quem é
`is_platform_staff` (ou superusuário) entra. Um usuário de tenant que por
engano tente acessar `/owner/*` é bloqueado aqui — a área dele é `/app/*`.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def owner_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not (request.user.is_platform_staff or request.user.is_superuser):
            raise PermissionDenied("Esta área é exclusiva da equipe da plataforma.")
        return view_func(request, *args, **kwargs)

    return _wrapped

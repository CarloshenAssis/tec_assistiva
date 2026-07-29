"""
Decorador de acesso ao namespace `/owner/*` (área da equipe da plataforma).

Espelha `core.decorators.tenant_required`, na direção oposta: aqui só quem é
`is_platform_staff` entra. Um usuário de tenant que por engano tente
acessar `/owner/*` é bloqueado aqui — a área dele é `/app/*`.

Checa só `is_platform_staff`, não `is_superuser` — de propósito. Um usuário
pode ter `is_superuser=True` (privilégio geral do Django, ex.: acesso amplo
ao `/admin/`) e ainda pertencer a um tenant (`is_platform_staff=False`) —
são flags independentes. `templates/base.html` escolhe o layout da página
com base em `is_platform_staff`; se este decorador aceitasse `is_superuser`
sozinho, um superusuário de tenant passaria no controle de acesso mas veria
uma página em branco (o shell errado é montado ao redor do conteúdo). As
duas verificações precisam ficar em sincronia.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def owner_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_platform_staff:
            raise PermissionDenied("Esta área é exclusiva da equipe da plataforma.")
        return view_func(request, *args, **kwargs)

    return _wrapped

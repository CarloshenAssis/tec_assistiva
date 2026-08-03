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
    """Decorador que restringe uma view a usuários vinculados a um tenant.

    Combina `django.contrib.auth.decorators.login_required` (exige sessão
    autenticada) com a checagem adicional de que o usuário não é da
    plataforma (`is_platform_staff`) e possui `tenant_id` definido.

    Args:
        view_func: A view Django a ser decorada.

    Returns:
        A view decorada. Requisições de usuário anônimo são redirecionadas
        ao login; requisições de Owner ou usuário sem tenant recebem
        `PermissionDenied` (HTTP 403).

    Raises:
        django.core.exceptions.PermissionDenied: Se `request.user` for
            `is_platform_staff=True` ou não tiver `tenant_id`.
    """

    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_platform_staff or not request.user.tenant_id:
            raise PermissionDenied("Esta área é exclusiva de usuários vinculados a um tenant.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def nivel_hierarquico(request) -> int:
    """Devolve o nível hierárquico do usuário logado na requisição.

    Args:
        request: A requisição Django corrente, com `request.user` já
            resolvido pelo `AuthenticationMiddleware`.

    Returns:
        `Papel.nivel_hierarquico` do usuário, ou `0` se não tiver papel
        definido.
    """
    papel = getattr(request.user, "papel", None)
    return papel.nivel_hierarquico if papel else 0

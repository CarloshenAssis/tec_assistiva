"""
TenantMiddleware — resolve o tenant do usuário autenticado uma vez por
requisição e o expõe via `core.tenancy` para o `TenantManager`.

Deve vir depois de `AuthenticationMiddleware` em MIDDLEWARE (depende de
`request.user`). Usuários de plataforma (`is_platform_staff=True`) nunca
têm tenant definido no contexto — as views do app `owner` não devem
depender deste middleware para o próprio isolamento (elas usam
`all_tenants()` deliberadamente).
"""

from core.tenancy import reset_current_tenant_id, set_current_tenant_id


class TenantMiddleware:
    """Resolve o tenant do usuário autenticado e o expõe para a requisição.

    Popula `request.tenant` e o `ContextVar` de `core.tenancy`
    (consumido pelo `TenantManager`) uma única vez por requisição.
    """

    def __init__(self, get_response):
        """Inicializa o middleware.

        Args:
            get_response: Callable padrão do Django que processa a
                requisição e devolve a resposta.
        """
        self.get_response = get_response

    def __call__(self, request):
        """Resolve o tenant corrente e processa a requisição nesse contexto.

        Args:
            request: A requisição HTTP corrente. Deve já ter
                `request.user` resolvido (middleware precisa vir depois
                de `AuthenticationMiddleware`).

        Returns:
            A resposta HTTP produzida pela cadeia de middlewares/view
            seguinte. `request.tenant` é definido como o `Tenant` do
            usuário (ou `None` para usuário anônimo ou Owner
            `is_platform_staff`), e o `ContextVar` correspondente é
            sempre limpo ao final, mesmo em caso de exceção.
        """
        tenant = None
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            if not getattr(user, "is_platform_staff", False):
                tenant = getattr(user, "tenant", None)

        request.tenant = tenant
        token = set_current_tenant_id(tenant.pk if tenant else None)
        try:
            response = self.get_response(request)
        finally:
            reset_current_tenant_id(token)
        return response

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
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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

from django.contrib import admin

from core.models import Fornecedor, Tenant, Unidade


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "segmento", "cidade", "uf", "ativo", "criado_em")
    list_filter = ("segmento", "ativo", "uf")
    search_fields = ("nome", "slug")
    prepopulated_fields = {"slug": ("nome",)}


class TenantScopedAdmin(admin.ModelAdmin):
    """
    Admin base que restringe listagem/edição ao tenant do usuário logado.

    Reaproveitado por todo model tenant-scoped nos demais apps
    (`TenantAdminMixin` citado em docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3.1).
    Superusuários da plataforma (is_platform_staff) enxergam todos os
    tenants — uso exclusivo de suporte/provisionamento.
    """

    def get_queryset(self, request):
        qs = self.model._default_manager.all_tenants()
        user = request.user
        if getattr(user, "is_platform_staff", False) or user.is_superuser:
            return qs
        tenant = getattr(user, "tenant", None)
        return qs.filter(tenant=tenant) if tenant else qs.none()


@admin.register(Unidade)
class UnidadeAdmin(TenantScopedAdmin):
    list_display = ("nome", "tenant", "ativo")
    list_filter = ("tenant", "ativo")
    search_fields = ("nome",)


@admin.register(Fornecedor)
class FornecedorAdmin(TenantScopedAdmin):
    list_display = ("nome", "tenant", "contato", "telefone")
    list_filter = ("tenant",)
    search_fields = ("nome", "contato")

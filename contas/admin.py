from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from contas.models import Papel, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "tenant",
        "papel",
        "is_platform_staff",
        "is_active",
    )
    list_filter = ("tenant", "papel", "is_platform_staff", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("Ciclartech", {"fields": ("tenant", "papel", "is_platform_staff")}),
    )

    def get_queryset(self, request):
        qs = self.model._default_manager.get_queryset()
        user = request.user
        if user.is_platform_staff or user.is_superuser:
            return qs
        return qs.filter(tenant=user.tenant)


@admin.register(Papel)
class PapelAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "nivel_hierarquico", "pode_gerenciar_manutencao")

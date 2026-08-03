"""Configuração do Django Admin para os models de contas."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from contas.models import Papel, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin do model `Usuario`, restrito ao tenant do usuário logado."""

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
        """Restringe o queryset ao tenant do usuário logado.

        Args:
            request: A requisição do admin, com `request.user` resolvido.

        Returns:
            Queryset completo para staff da plataforma ou superusuário;
            caso contrário, filtrado pelo tenant do usuário.
        """
        qs = self.model._default_manager.get_queryset()
        user = request.user
        if user.is_platform_staff or user.is_superuser:
            return qs
        return qs.filter(tenant=user.tenant)


@admin.register(Papel)
class PapelAdmin(admin.ModelAdmin):
    """Admin do model `Papel` — catálogo global, sem escopo de tenant."""

    list_display = ("nome", "codigo", "nivel_hierarquico", "pode_gerenciar_manutencao")

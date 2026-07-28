from django.contrib import admin

from core.admin import TenantScopedAdmin
from notificacoes.models import NotificacaoEnviada, NotificacaoTemplate


@admin.register(NotificacaoTemplate)
class NotificacaoTemplateAdmin(TenantScopedAdmin):
    list_display = ("titulo", "tipo", "tenant")
    list_filter = ("tenant", "tipo")


@admin.register(NotificacaoEnviada)
class NotificacaoEnviadaAdmin(TenantScopedAdmin):
    list_display = ("beneficiario", "template", "canal", "status", "criado_em", "tenant")
    list_filter = ("tenant", "canal", "status", "template__tipo")
    readonly_fields = [f.name for f in NotificacaoEnviada._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False

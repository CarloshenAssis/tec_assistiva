"""
Cadastro dos models de notificação no Django Admin.

`NotificacaoTemplateAdmin` permite edição normal (é conteúdo configurável
por tenant, RF017). `NotificacaoEnviadaAdmin` é somente-leitura: é o
registro de um envio já ocorrido, e alterá-lo depois do fato apagaria o
histórico real do que foi de fato disparado ao beneficiário.
"""

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
        """Bloqueia a exclusão de registros de envio pelo admin.

        Args:
            request: A requisição corrente (não usada).
            obj: O registro em questão, se houver (não usado).

        Returns:
            `False`, sempre.
        """
        return False

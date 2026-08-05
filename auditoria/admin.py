"""
Consulta da trilha de auditoria pelo Django Admin.

Estritamente somente-leitura. Uma trilha que o próprio administrador do
sistema pode editar ou apagar não vale como evidência — nem numa
investigação interna, nem perante a ANPD. O expurgo por prazo de retenção
existe, mas é operação de linha de comando deliberada
(`manage.py expurgar_auditoria`), não um botão na tela.
"""

from django.contrib import admin

from auditoria.models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = (
        "criado_em",
        "acao",
        "usuario_identificacao",
        "tenant",
        "objeto_tipo",
        "objeto_id",
        "envolve_dado_sensivel",
        "ip",
    )
    list_filter = ("acao", "envolve_dado_sensivel", "tenant", "criado_em")
    search_fields = ("usuario_identificacao", "objeto_id", "descricao", "ip")
    date_hierarchy = "criado_em"

    # Todos os campos em modo leitura — inclusive para superusuário.
    readonly_fields = tuple(
        campo.name for campo in RegistroAuditoria._meta.fields
    )

    def has_add_permission(self, request):
        """Bloqueia a criação manual de registros pelo admin.

        Registros só nascem pela API de serviço (`auditoria.services`).
        Permitir criação manual abriria a porta para forjar evidência.

        Args:
            request: A requisição corrente (não usada — a resposta é
                incondicional).

        Returns:
            `False`, sempre.
        """
        return False

    def has_change_permission(self, request, obj=None):
        """Bloqueia qualquer edição de registro — inclusive por superusuário.

        Args:
            request: A requisição corrente (não usada).
            obj: O registro em questão, se houver (não usado).

        Returns:
            `False`, sempre.
        """
        return False

    def has_delete_permission(self, request, obj=None):
        """Bloqueia exclusão individual pelo admin.

        O expurgo por prazo de retenção é feito pelo comando de linha de
        comando `expurgar_auditoria`, nunca por um botão de tela.

        Args:
            request: A requisição corrente (não usada).
            obj: O registro em questão, se houver (não usado).

        Returns:
            `False`, sempre.
        """
        return False

    def get_queryset(self, request):
        """Restringe a listagem à trilha do tenant do usuário logado.

        Um administrador de tenant só enxerga a trilha do próprio tenant.
        Sem esse filtro, o admin de uma prefeitura veria os eventos de
        outra — inclusive quais titulares foram consultados lá.

        Args:
            request: A requisição corrente, com `request.user` resolvido.

        Returns:
            Queryset de `RegistroAuditoria` já filtrado: sem filtro para
            staff da plataforma/superusuário, filtrado por `tenant` para os
            demais, e vazio se o usuário não tiver tenant associado.
        """
        qs = super().get_queryset(request)
        user = request.user
        if getattr(user, "is_platform_staff", False) or user.is_superuser:
            return qs
        tenant = getattr(user, "tenant", None)
        return qs.filter(tenant=tenant) if tenant else qs.none()

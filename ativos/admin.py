from django.contrib import admin

from ativos.models import (
    Ativo,
    CategoriaAtivo,
    DetalheEmprestimo,
    DetalheManutencao,
    FotoAtivo,
    FotoMovimentacao,
    Movimentacao,
    SubcategoriaAtivo,
)
from core.admin import TenantScopedAdmin


@admin.register(CategoriaAtivo)
class CategoriaAtivoAdmin(TenantScopedAdmin):
    list_display = ("nome", "tenant")
    list_filter = ("tenant",)


@admin.register(SubcategoriaAtivo)
class SubcategoriaAtivoAdmin(TenantScopedAdmin):
    list_display = ("nome", "categoria", "tenant")
    list_filter = ("tenant", "categoria")


class FotoAtivoInline(admin.TabularInline):
    model = FotoAtivo
    extra = 0


@admin.register(Ativo)
class AtivoAdmin(TenantScopedAdmin):
    list_display = ("patrimonio", "categoria", "status", "unidade", "tenant", "qr_token")
    list_filter = ("tenant", "categoria", "status", "unidade")
    search_fields = ("patrimonio", "numero_serie", "qr_token")
    readonly_fields = ("qr_token",)
    inlines = [FotoAtivoInline]


@admin.register(Movimentacao)
class MovimentacaoAdmin(TenantScopedAdmin):
    list_display = ("ativo", "tipo", "status_anterior", "status_novo", "data_hora", "usuario", "tenant")
    list_filter = ("tenant", "tipo")
    readonly_fields = [f.name for f in Movimentacao._meta.fields]

    def has_delete_permission(self, request, obj=None):
        # Movimentacao é append-only — reforça no Admin o que o model já impede.
        return False


@admin.register(FotoMovimentacao)
class FotoMovimentacaoAdmin(TenantScopedAdmin):
    list_display = ("movimentacao", "tipo", "tenant")


@admin.register(DetalheEmprestimo)
class DetalheEmprestimoAdmin(TenantScopedAdmin):
    list_display = ("movimentacao", "beneficiario", "data_prevista_devolucao", "assinatura_tipo")


@admin.register(DetalheManutencao)
class DetalheManutencaoAdmin(TenantScopedAdmin):
    list_display = ("movimentacao", "fornecedor", "motivo", "valor", "data_conclusao")

"""
Registro do `Beneficiario` e seus documentos no Django Admin.

Uso interno (suporte/staff da plataforma), não a tela operacional dos
usuários do tenant — essa é `beneficiarios/views.py`. `TenantScopedAdmin`
garante o isolamento entre tenants também aqui.
"""

from django.contrib import admin

from beneficiarios.models import Beneficiario, DocumentoBeneficiario
from core.admin import TenantScopedAdmin


class DocumentoBeneficiarioInline(admin.TabularInline):
    """Edição dos documentos do titular direto na página do `Beneficiario`."""

    model = DocumentoBeneficiario
    extra = 0


@admin.register(Beneficiario)
class BeneficiarioAdmin(TenantScopedAdmin):
    """Admin do titular, com seus documentos anexados como inline."""

    list_display = ("nome", "documento", "tipo_relacao", "cidade", "tenant")
    list_filter = ("tenant", "tipo_relacao")
    search_fields = ("nome", "documento", "telefone")
    inlines = [DocumentoBeneficiarioInline]

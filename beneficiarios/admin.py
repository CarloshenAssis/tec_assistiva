from django.contrib import admin

from beneficiarios.models import Beneficiario, DocumentoBeneficiario
from core.admin import TenantScopedAdmin


class DocumentoBeneficiarioInline(admin.TabularInline):
    model = DocumentoBeneficiario
    extra = 0


@admin.register(Beneficiario)
class BeneficiarioAdmin(TenantScopedAdmin):
    list_display = ("nome", "cpf", "tipo_relacao", "cidade", "tenant")
    list_filter = ("tenant", "tipo_relacao")
    search_fields = ("nome", "cpf", "telefone")
    inlines = [DocumentoBeneficiarioInline]

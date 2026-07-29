from django.apps import AppConfig


class OwnerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "owner"
    verbose_name = "Ciclartech · Plataforma (Owner)"

    # Controle de contratos (Tenant) e geração do primeiro acesso do
    # administrador de cada B2G/B2B — ver owner/views.py. Métricas de SaaS,
    # Planos, Feature Flags e Billing continuam escopo da Fase 4 (ver
    # docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §6).
    #
    # Este é o ÚNICO app (além do mixin de admin em core/admin.py)
    # autorizado a chamar `Manager.all_tenants()`
    # (core/tests/test_architecture.py garante isso via CI).

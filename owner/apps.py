from django.apps import AppConfig


class OwnerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "owner"
    verbose_name = "Ciclartech · Plataforma (Owner)"

    # App reservado nesta fase (Fase 0): namespace de URL e app registrados,
    # sem views/models de negócio ainda. Conteúdo (dashboard de métricas
    # SaaS, Planos, Feature Flags, Billing) é escopo da Fase 4 — ver
    # docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §6.
    #
    # A única coisa que já existe aqui é o compromisso arquitetural: este
    # é o ÚNICO app autorizado a chamar `Manager.all_tenants()`
    # (core/tests/test_architecture.py garante isso via CI).

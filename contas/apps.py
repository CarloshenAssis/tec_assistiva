from django.apps import AppConfig


class ContasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contas"
    verbose_name = "Contas e Acessos"

    def ready(self):
        # Registra os receivers de auditoria de autenticação. O import
        # tardio aqui é o padrão do Django para signals: no topo do módulo
        # ele rodaria antes do app registry estar pronto.
        from contas import signals  # noqa: F401

from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auditoria"
    verbose_name = "Auditoria"

    def ready(self):
        # Import tardio, padrão do Django para sinais: no topo do módulo
        # rodaria antes do app registry estar pronto. É este import que liga
        # a captura automática de criação/alteração/exclusão — ver
        # auditoria/rastreamento.py.
        from auditoria import rastreamento  # noqa: F401

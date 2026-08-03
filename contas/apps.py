"""Configuração de aplicação do app `contas`."""

from django.apps import AppConfig


class ContasConfig(AppConfig):
    """Configuração Django do app `contas`.

    Attributes:
        default_auto_field: Tipo padrão de chave primária auto-incrementada.
        name: Nome do app (label de import).
        verbose_name: Nome de exibição no Django Admin.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "contas"
    verbose_name = "Contas e Acessos"

    def ready(self):
        """Registra os signal receivers de auditoria de autenticação.

        O import tardio aqui é o padrão do Django para signals: no topo
        do módulo ele rodaria antes do app registry estar pronto.
        """
        from contas import signals  # noqa: F401

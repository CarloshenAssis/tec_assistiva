"""Configuração de aplicação do app `core`."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuração Django do app `core`.

    Attributes:
        default_auto_field: Tipo padrão de chave primária auto-incrementada.
        name: Nome do app (label de import).
        verbose_name: Nome de exibição no Django Admin.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Plataforma · Núcleo"

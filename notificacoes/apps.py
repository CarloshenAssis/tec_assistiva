from django.apps import AppConfig


class NotificacoesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notificacoes"
    verbose_name = "Notificações"

    # App reservado nesta fase (Fase 0): sem models ainda.
    # Conteúdo (NotificacaoTemplate, NotificacaoEnviada, tarefas Celery de
    # WhatsApp/Email) é escopo da Fase 1 — ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md.

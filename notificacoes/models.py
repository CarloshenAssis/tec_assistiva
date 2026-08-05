"""
Notificações automáticas (RF016/RF017, docs/ESPECIFICACAO_TECNICA.md) —
WhatsApp e Email (docs/PLANO_DOMINIO_ATIVOS.md §10).

`NotificacaoTemplate` é tenant-scoped (RF017 — cada instituição pode
editar seus próprios textos). `NotificacaoEnviada` é o registro de cada
envio, para auditoria e para o painel "Notificações" mostrar o que já foi
disparado.
"""

from django.db import models

from core.models import TenantModel


class NotificacaoTemplate(TenantModel):
    """Texto configurável de um tipo de aviso, por tenant.

    Um tenant sem template cadastrado para um `Tipo` simplesmente não
    recebe aquele aviso (ver `notificacoes.services.criar_e_enviar`) — é
    assim que RF017 deixa a instituição desativar um tipo de notificação,
    sem precisar de um campo "ativo" à parte.
    """

    class Tipo(models.TextChoices):
        CONFIRMACAO_EMPRESTIMO = "confirmacao_emprestimo", "Confirmação de empréstimo"
        AVISO_7_DIAS = "aviso_7_dias", "Aviso 7 dias antes do vencimento"
        VENCIMENTO = "vencimento", "Vencimento hoje"
        ATRASO = "atraso", "Em atraso"

    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    titulo = models.CharField(max_length=150)
    corpo_texto = models.TextField(
        help_text="Variáveis disponíveis: {beneficiario}, {ativo}, {codigo}, {data_prevista}, {dias}."
    )

    class Meta:
        verbose_name = "Template de Notificação"
        verbose_name_plural = "Templates de Notificação"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "tipo"], name="notificacaotemplate_unico_por_tenant")
        ]

    def __str__(self) -> str:
        return self.titulo


class NotificacaoEnviada(TenantModel):
    """Registro de uma tentativa de envio de notificação a um beneficiário.

    Uma linha por canal disparado (um empréstimo com WhatsApp e Email
    cadastrados gera duas linhas). É tanto o histórico mostrado no painel
    "Notificações" quanto a base de deduplicação que
    `notificacoes.services.ja_notificado_hoje` consulta para não reenviar
    o mesmo aviso no mesmo dia.
    """

    class Canal(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        ENVIADO = "enviado", "Enviado"
        FALHOU = "falhou", "Falhou"

    movimentacao = models.ForeignKey(
        "ativos.Movimentacao", null=True, blank=True, on_delete=models.SET_NULL, related_name="notificacoes"
    )
    beneficiario = models.ForeignKey(
        "beneficiarios.Beneficiario", on_delete=models.CASCADE, related_name="notificacoes"
    )
    template = models.ForeignKey(NotificacaoTemplate, on_delete=models.PROTECT, related_name="envios")
    canal = models.CharField(max_length=10, choices=Canal.choices)
    destinatario = models.CharField(max_length=150)
    corpo_renderizado = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE)
    tentativas = models.PositiveIntegerField(default=0)
    enviado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notificação Enviada"
        verbose_name_plural = "Notificações Enviadas"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return f"{self.template.tipo} · {self.beneficiario.nome} · {self.canal}"

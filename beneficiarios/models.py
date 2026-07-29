"""
Beneficiario — generalizado conceitualmente para "a pessoa/entidade para
quem o ativo é destinado" (beneficiário social, paciente, cliente
locatário), via `tipo_relacao`, em vez de três models distintos por
segmento. Ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §7.
"""

from django.db import models

from core.models import TenantModel
from core.validadores import validar_upload


class Beneficiario(TenantModel):
    class TipoRelacao(models.TextChoices):
        BENEFICIARIO = "beneficiario", "Beneficiário"
        PACIENTE = "paciente", "Paciente"
        CLIENTE = "cliente", "Cliente"

    class BaseLegal(models.TextChoices):
        """
        Hipótese que autoriza o tratamento (LGPD Art. 7º para dado pessoal
        comum, Art. 11 para dado sensível — que é o caso quando há laudo ou
        receita médica anexados).

        O campo é obrigatório por desenho: sem base legal declarada não há
        tratamento lícito, e registrar "qual era a justificativa" só depois
        do incidente não convence ninguém.
        """

        CONSENTIMENTO = "consentimento", "Consentimento do titular (Art. 7º I / 11 I)"
        OBRIGACAO_LEGAL = "obrigacao_legal", "Obrigação legal ou regulatória (Art. 7º II)"
        POLITICA_PUBLICA = "politica_publica", "Execução de política pública (Art. 7º III)"
        TUTELA_SAUDE = "tutela_saude", "Tutela da saúde (Art. 11 II 'f')"
        EXECUCAO_CONTRATO = "execucao_contrato", "Execução de contrato (Art. 7º V)"

    tipo_relacao = models.CharField(
        max_length=20, choices=TipoRelacao.choices, default=TipoRelacao.BENEFICIARIO
    )
    nome = models.CharField(max_length=150)
    cpf = models.CharField(max_length=14)
    rg = models.CharField(max_length=20, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    cep = models.CharField(max_length=9, blank=True)
    contato_emergencia_nome = models.CharField(max_length=150, blank=True)
    contato_emergencia_telefone = models.CharField(max_length=20, blank=True)
    contato_emergencia_parentesco = models.CharField(max_length=50, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    # ----------------------------------------------------- LGPD ----
    base_legal = models.CharField(
        max_length=30,
        choices=BaseLegal.choices,
        default=BaseLegal.CONSENTIMENTO,
        help_text="Hipótese legal que autoriza o tratamento dos dados deste titular.",
    )
    consentimento_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Momento em que o titular consentiu. Obrigatório quando a base legal é consentimento.",
    )
    consentimento_revogado_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Revogação do consentimento (Art. 8º §5º). Não apaga o histórico operacional já constituído.",
    )
    anonimizado_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Quando os dados identificáveis foram removidos a pedido do titular (Art. 18 VI).",
    )

    class Meta:
        verbose_name = "Beneficiário"
        verbose_name_plural = "Beneficiários"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "cpf"], name="beneficiario_cpf_unico_por_tenant")
        ]
        ordering = ["nome"]

    @property
    def esta_anonimizado(self) -> bool:
        return self.anonimizado_em is not None

    @property
    def consentimento_vigente(self) -> bool:
        """
        Só faz sentido quando a base legal é consentimento — nas demais
        hipóteses o tratamento não depende dele (Art. 7º/11), e perguntar
        "há consentimento?" levaria à conclusão errada de que o tratamento
        é ilícito.
        """
        if self.base_legal != self.BaseLegal.CONSENTIMENTO:
            return True
        return self.consentimento_em is not None and self.consentimento_revogado_em is None

    def __str__(self) -> str:
        return self.nome


class DocumentoBeneficiario(TenantModel):
    class Tipo(models.TextChoices):
        RG = "rg", "RG"
        CPF = "cpf", "CPF"
        COMPROVANTE_RESIDENCIA = "comprovante_residencia", "Comprovante de Residência"
        RECEITA_MEDICA = "receita_medica", "Receita Médica"
        LAUDO = "laudo", "Laudo"

    beneficiario = models.ForeignKey(
        Beneficiario, on_delete=models.CASCADE, related_name="documentos"
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    # Validador no campo (e não só no formulário) para que a restrição valha
    # em qualquer caminho de escrita — form, admin, importação, API futura.
    arquivo = models.FileField(
        upload_to="beneficiarios/documentos/%Y/%m/",
        validators=[validar_upload],
    )
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Documento do Beneficiário"
        verbose_name_plural = "Documentos do Beneficiário"

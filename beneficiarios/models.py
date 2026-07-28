"""
Beneficiario — generalizado conceitualmente para "a pessoa/entidade para
quem o ativo é destinado" (beneficiário social, paciente, cliente
locatário), via `tipo_relacao`, em vez de três models distintos por
segmento. Ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §7.
"""

from django.db import models

from core.models import TenantModel


class Beneficiario(TenantModel):
    class TipoRelacao(models.TextChoices):
        BENEFICIARIO = "beneficiario", "Beneficiário"
        PACIENTE = "paciente", "Paciente"
        CLIENTE = "cliente", "Cliente"

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

    class Meta:
        verbose_name = "Beneficiário"
        verbose_name_plural = "Beneficiários"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "cpf"], name="beneficiario_cpf_unico_por_tenant")
        ]
        ordering = ["nome"]

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
    arquivo = models.FileField(upload_to="beneficiarios/documentos/%Y/%m/")
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Documento do Beneficiário"
        verbose_name_plural = "Documentos do Beneficiário"

"""
Modelos do domínio de Ativos — aggregate `Ativo`, `Movimentacao` e as
tabelas de apoio, conforme docs/PLANO_DOMINIO_ATIVOS.md.

Os `choices` de status/tipo de movimentação são derivados dos enums puros
de `ativos.domain.enums`, para nunca haver duas fontes de verdade sobre os
valores válidos entre a camada de domínio e a camada de persistência.
"""

import uuid

from django.db import models

from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from core.models import Fornecedor, TenantManager, TenantModel, TenantQuerySet, Unidade


def _choices(enum_cls):
    return [(item.value, item.rotulo) for item in enum_cls]


def gerar_qr_token() -> str:
    """
    Token do QR Code — único globalmente na plataforma, não por tenant.

    Ver docs/PLANO_DOMINIO_ATIVOS.md §3.2 para a justificativa: uma
    etiqueta impressa pode circular fisicamente além do controle do
    sistema, e a unicidade global permite resolver o ativo a partir do
    token antes mesmo de saber a que tenant ele pertence.
    """
    return uuid.uuid4().hex


class CategoriaAtivo(TenantModel):
    nome = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Categoria de Ativo"
        verbose_name_plural = "Categorias de Ativo"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nome"], name="categoria_ativo_unica_por_tenant")
        ]
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class SubcategoriaAtivo(TenantModel):
    categoria = models.ForeignKey(
        CategoriaAtivo, on_delete=models.CASCADE, related_name="subcategorias"
    )
    nome = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Subcategoria de Ativo"
        verbose_name_plural = "Subcategorias de Ativo"
        constraints = [
            models.UniqueConstraint(
                fields=["categoria", "nome"], name="subcategoria_ativo_unica_por_categoria"
            )
        ]
        ordering = ["nome"]

    def __str__(self) -> str:
        return f"{self.categoria.nome} · {self.nome}"


class Ativo(TenantModel):
    patrimonio = models.CharField(max_length=50)
    qr_token = models.CharField(max_length=64, unique=True, editable=False, default=gerar_qr_token)
    categoria = models.ForeignKey(CategoriaAtivo, on_delete=models.PROTECT, related_name="ativos")
    subcategoria = models.ForeignKey(
        SubcategoriaAtivo, null=True, blank=True, on_delete=models.SET_NULL, related_name="ativos"
    )
    modelo = models.CharField(max_length=100, blank=True)
    fabricante = models.CharField(max_length=100, blank=True)
    numero_serie = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20, choices=_choices(StatusAtivo), default=StatusAtivo.DISPONIVEL.value
    )
    unidade = models.ForeignKey(
        Unidade, null=True, blank=True, on_delete=models.SET_NULL, related_name="ativos"
    )
    fornecedor = models.ForeignKey(
        Fornecedor, null=True, blank=True, on_delete=models.SET_NULL, related_name="ativos"
    )
    data_aquisicao = models.DateField(null=True, blank=True)
    vida_util_meses = models.PositiveIntegerField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ativo"
        verbose_name_plural = "Ativos"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "patrimonio"], name="ativo_patrimonio_unico_por_tenant")
        ]
        ordering = ["-criado_em"]

    @property
    def status_enum(self) -> StatusAtivo:
        return StatusAtivo(self.status)

    def __str__(self) -> str:
        return f"{self.patrimonio} · {self.categoria.nome}"


class FotoAtivo(TenantModel):
    """Fotos de cadastro do ativo (não vinculadas a uma movimentação específica)."""

    class Tipo(models.TextChoices):
        PRINCIPAL = "principal", "Principal"
        LATERAL = "lateral", "Lateral"
        TRASEIRA = "traseira", "Traseira"
        ETIQUETA = "etiqueta", "Etiqueta de Patrimônio"

    ativo = models.ForeignKey(Ativo, on_delete=models.CASCADE, related_name="fotos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    arquivo = models.ImageField(upload_to="ativos/fotos/%Y/%m/")
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Foto do Ativo"
        verbose_name_plural = "Fotos do Ativo"


class MovimentacaoQuerySet(TenantQuerySet):
    def mais_recente_do_tipo(self, ativo, tipo: TipoMovimentacao):
        return self.filter(ativo=ativo, tipo=tipo.value).order_by("-data_hora").first()


class MovimentacaoManager(TenantManager.from_queryset(MovimentacaoQuerySet)):
    """
    `from_queryset` expõe `mais_recente_do_tipo` diretamente no manager
    (proxy para `self.get_queryset().mais_recente_do_tipo(...)`), mantendo
    o isolamento por tenant de `TenantManager.get_queryset()` intacto.
    """

    queryset_class = MovimentacaoQuerySet


class Movimentacao(TenantModel):
    """
    Registro imutável de tudo que acontece com um Ativo — a fonte de
    verdade da Timeline (docs/PLANO_DOMINIO_ATIVOS.md §4).

    Nunca é apagada: `delete()` é bloqueado abaixo. A revogação do
    privilégio de DELETE a nível de banco de dados para o usuário da
    aplicação é uma tarefa de infraestrutura complementar (fora do escopo
    desta migration), documentada aqui como ponto de atenção operacional.
    """

    ativo = models.ForeignKey(Ativo, on_delete=models.PROTECT, related_name="movimentacoes")
    tipo = models.CharField(max_length=20, choices=_choices(TipoMovimentacao))
    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        "contas.Usuario", null=True, on_delete=models.SET_NULL, related_name="movimentacoes"
    )
    unidade = models.ForeignKey(
        Unidade, null=True, blank=True, on_delete=models.SET_NULL, related_name="movimentacoes"
    )
    observacoes = models.TextField(blank=True)
    status_anterior = models.CharField(max_length=20, choices=_choices(StatusAtivo))
    status_novo = models.CharField(max_length=20, choices=_choices(StatusAtivo))
    dados_especificos = models.JSONField(default=dict, blank=True)

    objects = MovimentacaoManager()

    class Meta:
        verbose_name = "Movimentação"
        verbose_name_plural = "Movimentações"
        ordering = ["-data_hora"]

    def delete(self, *args, **kwargs):
        raise RuntimeError(
            "Movimentacao é um registro imutável (append-only) — nunca deve ser "
            "excluída. Ver docs/PLANO_DOMINIO_ATIVOS.md §4.1."
        )

    def __str__(self) -> str:
        return f"{self.ativo.patrimonio} · {self.tipo} · {self.data_hora:%d/%m/%Y %H:%M}"


class FotoMovimentacao(TenantModel):
    class Tipo(models.TextChoices):
        FRONTAL = "frontal", "Frontal"
        LATERAL = "lateral", "Lateral"
        DETALHE = "detalhe", "Detalhe"
        ETIQUETA = "etiqueta", "Etiqueta"

    movimentacao = models.ForeignKey(Movimentacao, on_delete=models.CASCADE, related_name="fotos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    arquivo = models.ImageField(upload_to="movimentacoes/fotos/%Y/%m/")

    class Meta:
        verbose_name = "Foto da Movimentação"
        verbose_name_plural = "Fotos da Movimentação"


class DetalheEmprestimo(TenantModel):
    """Dados específicos de uma Movimentacao do tipo `emprestimo` (1:1)."""

    class AssinaturaTipo(models.TextChoices):
        FISICA = "fisica", "Física (padrão)"
        DIGITAL = "digital", "Digital (módulo opcional)"

    movimentacao = models.OneToOneField(
        Movimentacao, on_delete=models.CASCADE, related_name="detalhe_emprestimo"
    )
    beneficiario = models.ForeignKey(
        "beneficiarios.Beneficiario", on_delete=models.PROTECT, related_name="emprestimos"
    )
    prazo_dias = models.PositiveIntegerField()
    data_prevista_devolucao = models.DateField()
    assinatura_tipo = models.CharField(
        max_length=10, choices=AssinaturaTipo.choices, default=AssinaturaTipo.FISICA
    )
    assinatura_arquivo = models.FileField(upload_to="assinaturas/%Y/%m/", blank=True, null=True)

    class Meta:
        verbose_name = "Detalhe de Empréstimo"
        verbose_name_plural = "Detalhes de Empréstimo"


class DetalheManutencao(TenantModel):
    """Dados específicos de uma Movimentacao do tipo `manutencao` (1:1)."""

    movimentacao = models.OneToOneField(
        Movimentacao, on_delete=models.CASCADE, related_name="detalhe_manutencao"
    )
    fornecedor = models.ForeignKey(
        Fornecedor, null=True, blank=True, on_delete=models.SET_NULL, related_name="manutencoes"
    )
    motivo = models.CharField(max_length=255)
    valor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    data_conclusao = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Detalhe de Manutenção"
        verbose_name_plural = "Detalhes de Manutenção"

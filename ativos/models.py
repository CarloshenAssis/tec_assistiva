"""
Modelos do domínio de Ativos — aggregate `Ativo`, `Movimentacao` e as
tabelas de apoio, conforme docs/PLANO_DOMINIO_ATIVOS.md.

Os `choices` de status/tipo de movimentação são derivados dos enums puros
de `ativos.domain.enums`, para nunca haver duas fontes de verdade sobre os
valores válidos entre a camada de domínio e a camada de persistência.
"""

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone

from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from core.models import Fornecedor, TenantManager, TenantModel, TenantQuerySet, Unidade
from core.validadores import validar_upload, validar_upload_imagem


def _choices(enum_cls):
    """Converte um enum de domínio em `choices` no formato do Django.

    Args:
        enum_cls: Uma classe de enum com propriedade `.rotulo` em cada
            membro (ver `ativos.domain.enums`).

    Returns:
        Lista de tuplas `(valor, rótulo)`, no formato esperado por
        `models.CharField(choices=...)`.
    """
    return [(item.value, item.rotulo) for item in enum_cls]


def gerar_qr_token() -> str:
    """Gera o token do QR Code de um Ativo.

    Único globalmente na plataforma, não por tenant — ver
    docs/PLANO_DOMINIO_ATIVOS.md §3.2 para a justificativa: uma etiqueta
    impressa pode circular fisicamente além do controle do sistema, e a
    unicidade global permite resolver o ativo a partir do token antes
    mesmo de saber a que tenant ele pertence.

    Returns:
        Uma string hexadecimal de 32 caracteres (UUID4 sem hífens).
    """
    return uuid.uuid4().hex


class CategoriaAtivo(TenantModel):
    """Categoria de ativo (ex.: Cadeira de Rodas, Muletas), por tenant.

    Attributes:
        nome: Nome da categoria, único dentro do tenant.
        prefixo: Prefixo do código patrimonial gerado automaticamente
            para ativos desta categoria (ex.: `"CAD"` → `CAD-000001` —
            docs/features/identificacao-patrimonial-e-unidades.md). Em
            branco, é derivado do nome na hora (3 primeiras letras
            maiúsculas) — ver `ativos.services.gerar_codigo_patrimonial`.
    """

    nome = models.CharField(max_length=100)
    prefixo = models.CharField(
        max_length=10,
        blank=True,
        help_text="Ex.: CAD para Cadeira de Rodas. Em branco, é derivado do nome da categoria.",
    )

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
    """Subcategoria de ativo, aninhada a uma `CategoriaAtivo`.

    Attributes:
        categoria: FK para a `CategoriaAtivo` pai.
        nome: Nome da subcategoria, único dentro da categoria.
    """

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
    """Um ativo assistivo do acervo do tenant — o aggregate central do domínio.

    O estado operacional (`status`) só muda através da máquina de
    estados (`ativos.domain.state_machine`), nunca por atribuição direta
    fora dela.

    Attributes:
        patrimonio: Código patrimonial, único dentro do tenant.
        qr_token: Token único globalmente, usado na URL do QR Code (ver
            `gerar_qr_token`).
        categoria: FK para `CategoriaAtivo`.
        subcategoria: FK opcional para `SubcategoriaAtivo`.
        modelo: Modelo do equipamento (texto livre, opcional).
        fabricante: Fabricante do equipamento (texto livre, opcional).
        numero_serie: Número de série (texto livre, opcional).
        status: Estado operacional corrente — um dos valores de
            `StatusAtivo`.
        unidade: FK obrigatória para `core.Unidade` — nenhum ativo existe
            sem unidade responsável (docs/business-rules/unidades.md).
            `PROTECT` em vez de `SET_NULL`: uma unidade com ativos não
            pode ser apagada sem antes transferi-los.
        fornecedor: FK opcional para `core.Fornecedor` (aquisição).
        data_aquisicao: Data de aquisição do ativo (opcional).
        vida_util_meses: Vida útil estimada em meses (opcional).
        observacoes: Observações livres (opcional).
        criado_em: Data de cadastro do registro.
        atualizado_em: Data da última alteração do registro.
    """

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
    #: Unidade responsável pelo ativo — OBRIGATÓRIA (regra de negócio
    #: "nenhum ativo existe sem unidade, mesmo que exista apenas uma":
    #: docs/business-rules/unidades.md). `PROTECT` em vez de `SET_NULL`
    #: porque uma unidade com ativos não pode ser apagada sem antes
    #: transferi-los — apagar deixaria o ativo órfão, exatamente o estado
    #: que a obrigatoriedade existe para impedir. Para tirar uma unidade de
    #: operação use o campo `Unidade.ativo` (desativar), não exclusão.
    unidade = models.ForeignKey(Unidade, on_delete=models.PROTECT, related_name="ativos")
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
        """O status do ativo como membro de `StatusAtivo`.

        Returns:
            O `StatusAtivo` correspondente ao valor persistido em
            `status`.
        """
        return StatusAtivo(self.status)

    @property
    def ultima_impressao(self):
        """Data/hora da última etiqueta impressa deste ativo.

        Derivado de `ImpressaoEtiqueta` em vez de um contador
        desnormalizado no próprio Ativo: o histórico é a fonte de
        verdade única e não pode divergir do total. Em listagens, use a
        anotação de `ativos.selectors.anotar_impressoes` para não gerar
        N+1.

        Returns:
            O `datetime` da impressão mais recente, ou `None` se o ativo
            nunca foi impresso (está na "fila de impressão" —
            docs/business-rules/etiquetas.md).
        """
        impressao = self.impressoes.order_by("-impresso_em").first()
        return impressao.impresso_em if impressao else None

    @property
    def total_impressoes(self) -> int:
        """Quantidade total de vezes que a etiqueta deste ativo foi impressa.

        Returns:
            A contagem de registros em `ImpressaoEtiqueta` para este
            ativo.
        """
        return self.impressoes.count()

    def __str__(self) -> str:
        return f"{self.patrimonio} · {self.categoria.nome}"


class FotoAtivo(TenantModel):
    """Fotos de cadastro do ativo (não vinculadas a uma movimentação específica).

    Attributes:
        ativo: FK para o `Ativo` fotografado.
        tipo: Um dos ângulos de `FotoAtivo.Tipo`.
        arquivo: A imagem enviada.
        enviado_em: Data de envio da foto.
    """

    class Tipo(models.TextChoices):
        PRINCIPAL = "principal", "Principal"
        LATERAL = "lateral", "Lateral"
        TRASEIRA = "traseira", "Traseira"
        ETIQUETA = "etiqueta", "Etiqueta de Patrimônio"

    ativo = models.ForeignKey(Ativo, on_delete=models.CASCADE, related_name="fotos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    arquivo = models.ImageField(
        upload_to="ativos/fotos/%Y/%m/", validators=[validar_upload_imagem]
    )
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Foto do Ativo"
        verbose_name_plural = "Fotos do Ativo"


class MovimentacaoQuerySet(TenantQuerySet):
    """QuerySet de `Movimentacao`, com consultas específicas do domínio."""

    def mais_recente_do_tipo(self, ativo, tipo: TipoMovimentacao):
        """Busca a movimentação mais recente de um tipo específico para um ativo.

        Args:
            ativo: O `Ativo` a consultar.
            tipo: O `TipoMovimentacao` desejado.

        Returns:
            A `Movimentacao` mais recente que corresponda a `ativo` e
            `tipo`, ou `None` se não houver nenhuma.
        """
        return self.filter(ativo=ativo, tipo=tipo.value).order_by("-data_hora").first()


class MovimentacaoManager(TenantManager.from_queryset(MovimentacaoQuerySet)):
    """Manager de `Movimentacao`.

    `from_queryset` expõe `mais_recente_do_tipo` diretamente no manager
    (proxy para `self.get_queryset().mais_recente_do_tipo(...)`), mantendo
    o isolamento por tenant de `TenantManager.get_queryset()` intacto.
    """

    queryset_class = MovimentacaoQuerySet


class Movimentacao(TenantModel):
    """Registro imutável de tudo que acontece com um Ativo.

    A fonte de verdade da Timeline (docs/PLANO_DOMINIO_ATIVOS.md §4).

    Nunca é apagada: `delete()` é bloqueado abaixo. A revogação do
    privilégio de DELETE a nível de banco de dados para o usuário da
    aplicação é uma tarefa de infraestrutura complementar (fora do escopo
    desta migration), documentada aqui como ponto de atenção operacional.

    Attributes:
        ativo: FK para o `Ativo` movimentado.
        tipo: Um dos valores de `TipoMovimentacao`.
        data_hora: Momento em que a movimentação foi registrada.
        usuario: FK para o `contas.Usuario` que registrou, ou `None` se o
            usuário foi excluído posteriormente.
        unidade: FK opcional para a `core.Unidade` envolvida.
        observacoes: Observações livres (opcional).
        status_anterior: O `StatusAtivo` antes da movimentação.
        status_novo: O `StatusAtivo` depois da movimentação.
        dados_especificos: Dados adicionais específicos do tipo de
            movimentação, em JSON — usado pelos tipos mais simples que
            não têm tabela de detalhe dedicada (`DetalheEmprestimo`,
            `DetalheManutencao`).
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
        """Bloqueia a exclusão — `Movimentacao` é append-only.

        Raises:
            RuntimeError: Sempre — a exclusão nunca é permitida.
        """
        raise RuntimeError(
            "Movimentacao é um registro imutável (append-only) — nunca deve ser "
            "excluída. Ver docs/PLANO_DOMINIO_ATIVOS.md §4.1."
        )

    def __str__(self) -> str:
        return f"{self.ativo.patrimonio} · {self.tipo} · {self.data_hora:%d/%m/%Y %H:%M}"


class FotoMovimentacao(TenantModel):
    """Foto associada a uma movimentação específica (ex.: entrega, devolução).

    Attributes:
        movimentacao: FK para a `Movimentacao` fotografada.
        tipo: Um dos ângulos de `FotoMovimentacao.Tipo`.
        arquivo: A imagem enviada.
    """

    class Tipo(models.TextChoices):
        FRONTAL = "frontal", "Frontal"
        LATERAL = "lateral", "Lateral"
        DETALHE = "detalhe", "Detalhe"
        ETIQUETA = "etiqueta", "Etiqueta"

    movimentacao = models.ForeignKey(Movimentacao, on_delete=models.CASCADE, related_name="fotos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    arquivo = models.ImageField(
        upload_to="movimentacoes/fotos/%Y/%m/", validators=[validar_upload_imagem]
    )

    class Meta:
        verbose_name = "Foto da Movimentação"
        verbose_name_plural = "Fotos da Movimentação"


class DetalheEmprestimo(TenantModel):
    """Dados específicos de uma Movimentacao do tipo `emprestimo` (1:1).

    Attributes:
        movimentacao: FK 1:1 para a `Movimentacao` de empréstimo.
        beneficiario: FK para o `beneficiarios.Beneficiario` que recebeu
            o ativo.
        prazo_dias: Prazo do empréstimo, em dias.
        data_prevista_devolucao: Data limite de devolução.
        assinatura_tipo: Um dos valores de
            `DetalheEmprestimo.AssinaturaTipo`.
        assinatura_arquivo: Arquivo do termo assinado, quando aplicável
            (opcional).
        valor_diaria: Valor cobrado por dia de locação — só preenchido
            quando o tenant tem o módulo `locacao_financeiro` habilitado
            (docs/business-rules/modulos.md).
        caucao: Valor retido como caução, conferido na devolução (mesmo
            módulo opcional de `valor_diaria`).
        percentual_multa_atraso_dia: Percentual sobre o valor total do
            período, cobrado por dia de atraso na devolução (mesmo
            módulo opcional).
    """

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
    assinatura_arquivo = models.FileField(
        upload_to="assinaturas/%Y/%m/", blank=True, null=True, validators=[validar_upload]
    )

    # ------------------------------------- Locação financeira (opcional) ----
    # Só preenchidos quando o tenant tem o módulo `locacao_financeiro`
    # habilitado (docs/business-rules/modulos.md — ligado por padrão para o
    # segmento Locadora). Ficam aqui, não num model `ContratoLocacao`
    # separado: são três campos opcionais do mesmo empréstimo, não um
    # conceito de negócio com ciclo de vida próprio — criar uma tabela e um
    # join a mais para isso seria complexidade sem contrapartida.
    valor_diaria = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor cobrado por dia de locação.",
    )
    caucao = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor retido como caução, conferido na devolução.",
    )
    percentual_multa_atraso_dia = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentual sobre o valor total do período, cobrado por dia de atraso na devolução.",
    )

    class Meta:
        verbose_name = "Detalhe de Empréstimo"
        verbose_name_plural = "Detalhes de Empréstimo"

    @property
    def valor_total_periodo(self):
        """Valor total do período de locação (diária × prazo).

        Returns:
            `valor_diaria * prazo_dias`, ou `None` quando o tenant não
            usa o módulo financeiro — nunca `0`, que pareceria "gratuito".
        """
        if self.valor_diaria is None:
            return None
        return self.valor_diaria * self.prazo_dias

    def valor_multa_atraso(self, hoje=None):
        """Calcula a multa estimada por atraso na devolução.

        É uma estimativa informativa para a tela de devolução — quem
        decide o valor final cobrado é o operador, o sistema não
        desconta nada automaticamente.

        Args:
            hoje: Data de referência para o cálculo do atraso. Default a
                data corrente — parametrizável para testes
                determinísticos.

        Returns:
            `None` se o tenant não usa o módulo financeiro (sem
            `percentual_multa_atraso_dia` ou `valor_diaria`
            configurados). `Decimal("0")` se não há atraso. Caso
            contrário, o valor da multa proporcional aos dias de atraso.
        """
        if self.percentual_multa_atraso_dia is None or self.valor_diaria is None:
            return None

        hoje = hoje or timezone.now().date()
        dias_atraso = (hoje - self.data_prevista_devolucao).days
        if dias_atraso <= 0:
            return Decimal("0")
        return (
            self.valor_total_periodo * self.percentual_multa_atraso_dia / Decimal("100")
        ) * dias_atraso


class LayoutEtiqueta(models.TextChoices):
    """Tamanhos de etiqueta suportados pelo Centro de Etiquetas.

    A folha inteira é sempre impressa em papel A4 padrão, com as etiquetas
    lado a lado (ver `templates/ativos/etiquetas_folha.html`) — o tamanho
    aqui só define quanto espaço cada etiqueta ocupa na folha (CSS
    `.etiqueta` por `layout`), a ser recortada depois de impressa. Mudar um
    valor aqui exige mudar o CSS correspondente.

    Todo tamanho mostra o mesmo conteúdo (QR, patrimônio, categoria, nome e
    logotipo da instituição) — só a escala física muda, não o que cabe na
    etiqueta (docs/business-rules/etiquetas.md).
    """

    PEQUENO = "pequeno", "Pequeno — 33×22 mm"
    MEDIO = "medio", "Médio — 50×30 mm"
    GRANDE = "grande", "Grande — 80×50 mm"


class ImpressaoEtiqueta(TenantModel):
    """Histórico de impressão de etiquetas patrimoniais.

    Ver docs/business-rules/etiquetas.md.

    Existe para responder três perguntas do dia a dia do inventário: quais
    ativos ainda não têm etiqueta impressa (a "fila"), quando a etiqueta de
    um ativo foi impressa pela última vez, e quem imprimiu. Como qualquer
    histórico do produto, é append-only — `delete()` é bloqueado.

    Attributes:
        ativo: FK para o `Ativo` etiquetado.
        layout: Um dos valores de `LayoutEtiqueta`.
        usuario: FK para o `contas.Usuario` que imprimiu, ou `None` se o
            usuário foi excluído posteriormente.
        impresso_em: Data/hora da impressão.
        lote: UUID que agrupa as etiquetas geradas numa mesma folha,
            permitindo mostrar o histórico como "lote de 40 etiquetas em
            12/03" em vez de 40 linhas soltas, e reimprimir exatamente o
            mesmo lote.
    """

    ativo = models.ForeignKey(Ativo, on_delete=models.CASCADE, related_name="impressoes")
    layout = models.CharField(max_length=10, choices=LayoutEtiqueta.choices)
    usuario = models.ForeignKey(
        "contas.Usuario", null=True, on_delete=models.SET_NULL, related_name="impressoes_etiqueta"
    )
    impresso_em = models.DateTimeField(auto_now_add=True)
    lote = models.UUIDField(default=uuid.uuid4, editable=False)

    class Meta:
        verbose_name = "Impressão de Etiqueta"
        verbose_name_plural = "Impressões de Etiqueta"
        ordering = ["-impresso_em"]
        indexes = [models.Index(fields=["tenant", "lote"])]

    def delete(self, *args, **kwargs):
        """Bloqueia a exclusão — `ImpressaoEtiqueta` é append-only.

        Raises:
            RuntimeError: Sempre — a exclusão nunca é permitida.
        """
        raise RuntimeError(
            "ImpressaoEtiqueta é histórico append-only — nunca deve ser excluída "
            "(ver docs/business-rules/etiquetas.md)."
        )

    def __str__(self) -> str:
        return f"{self.ativo.patrimonio} · {self.get_layout_display()} · {self.impresso_em:%d/%m/%Y %H:%M}"


class DetalheManutencao(TenantModel):
    """Dados específicos de uma Movimentacao do tipo `manutencao` (1:1).

    Attributes:
        movimentacao: FK 1:1 para a `Movimentacao` de manutenção.
        fornecedor: FK opcional para o `core.Fornecedor`/oficina
            responsável.
        motivo: Motivo da manutenção.
        valor: Valor cobrado pela manutenção (opcional).
        data_conclusao: Data em que a manutenção foi concluída (opcional
            — vazio enquanto em andamento).
    """

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

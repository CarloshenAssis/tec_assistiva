"""
Modelos centrais: Tenant (instituição cliente) e a infraestrutura de
isolamento multi-tenant (TenantModel/TenantManager) reutilizada por todos
os apps de domínio.

Ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3 para a justificativa da
estratégia (schema compartilhado + tenant_id, isolamento por manager).
"""

from django.db import models

from core.tenancy import get_current_tenant_id
from core.validadores import validar_upload_imagem


class Tenant(models.Model):
    """
    Uma instituição cliente da plataforma (prefeitura, fundo social, home
    care, locadora, hospital, ONG, ...).

    O campo `segmento` aqui é deliberadamente um CharField simples nesta
    fase (não uma FK para uma tabela `Segmento`) — a modelagem completa de
    Segmento/Módulo/FeatureFlag é conteúdo da Fase 2 do roadmap. Não
    antecipamos essa tabela agora para não versionar um catálogo que ainda
    pode mudar de nome/granularidade antes de ter um segundo tenant real.
    """

    class Segmento(models.TextChoices):
        FUNDO_SOCIAL = "fundo_social", "Fundo Social / Prefeitura"
        HOME_CARE = "home_care", "Home Care"
        LOCADORA = "locadora", "Locadora"
        HOSPITAL = "hospital", "Hospital"
        ONG = "ong", "ONG"

    #: Como cada segmento chama a pessoa/entidade atendida pelos ativos —
    #: só rotula a tela (nav, títulos, botões, `docs/business-rules/`
    #: nenhum ainda cobre isto pois é diferenciação de vocabulário, não de
    #: regra). O dado continua sendo o mesmo `Beneficiario` em todos os
    #: segmentos — não há campo/fluxo diferente por trás do rótulo.
    _ROTULO_BENEFICIARIO_POR_SEGMENTO = {
        Segmento.FUNDO_SOCIAL: ("Beneficiário", "Beneficiários"),
        Segmento.ONG: ("Beneficiário", "Beneficiários"),
        Segmento.HOME_CARE: ("Paciente", "Pacientes"),
        Segmento.HOSPITAL: ("Paciente", "Pacientes"),
        Segmento.LOCADORA: ("Cliente", "Clientes"),
    }

    nome = models.CharField(max_length=150)
    slug = models.SlugField(max_length=60, unique=True)
    segmento = models.CharField(
        max_length=20, choices=Segmento.choices, default=Segmento.FUNDO_SOCIAL
    )
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    # --------------------------------------------------- LGPD (Art. 41) ----
    #: Cada tenant é o controlador dos dados dos SEUS beneficiários (a
    #: Ciclartech é operadora da plataforma, não controladora) — por isso o
    #: Encarregado é por tenant, não um único DPO global. Ver
    #: docs/POLITICA_PRIVACIDADE.md.
    dpo_nome = models.CharField(
        "Nome do Encarregado (DPO)",
        max_length=150,
        blank=True,
        help_text="Pessoa responsável por atender solicitações de titulares deste tenant (LGPD Art. 41).",
    )
    dpo_email = models.EmailField("E-mail do Encarregado (DPO)", blank=True)
    dpo_telefone = models.CharField("Telefone do Encarregado (DPO)", max_length=30, blank=True)

    #: Logotipo da instituição — aparece nas etiquetas patrimoniais
    #: (ativos/etiquetas.py) embutido como data URI, pela mesma razão do QR
    #: Code (folha de impressão autocontida, sem requisição de rede extra).
    #: Autoatendimento do Admin do tenant em `/app/instituicao/`
    #: (core/views_instituicao.py) — mesma lógica do Encarregado (DPO): só o
    #: próprio tenant decide a identidade visual da sua etiqueta.
    logo = models.ImageField(
        "Logotipo",
        upload_to="tenants/logos/",
        blank=True,
        null=True,
        validators=[validar_upload_imagem],
        help_text="Aparece nas etiquetas patrimoniais dos ativos.",
    )

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        ordering = ["nome"]

    @property
    def rotulo_beneficiario_singular(self) -> str:
        return self._ROTULO_BENEFICIARIO_POR_SEGMENTO.get(self.segmento, ("Beneficiário", "Beneficiários"))[0]

    @property
    def rotulo_beneficiario_plural(self) -> str:
        return self._ROTULO_BENEFICIARIO_POR_SEGMENTO.get(self.segmento, ("Beneficiário", "Beneficiários"))[1]

    def __str__(self) -> str:
        return self.nome


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant) -> "TenantQuerySet":
        tenant_id = tenant.pk if isinstance(tenant, models.Model) else tenant
        return self.filter(tenant_id=tenant_id)


class TenantManager(models.Manager):
    """
    Manager padrão de todo model multi-tenant.

    Filtra automaticamente pelo tenant corrente da requisição (definido
    pelo TenantMiddleware). Se não houver tenant no contexto, devolve um
    queryset VAZIO — isolamento "fail closed": um bug que esqueça de
    popular o contexto nunca resulta em vazamento de dado entre tenants,
    na pior hipótese resulta em uma tela vazia (defeito visível, não uma
    falha silenciosa de segurança).

    `all_tenants()` é a única forma de obter uma consulta cross-tenant, e
    deve ser usada exclusivamente dentro do app `owner`. Isso é reforçado
    por um teste de arquitetura automatizado — ver core/tests/test_architecture.py.
    """

    #: Subclasses podem trocar por um QuerySet mais específico (que
    #: estenda `TenantQuerySet`) para adicionar métodos de consulta sem
    #: perder o isolamento automático — ver `ativos.models.MovimentacaoManager`.
    queryset_class = TenantQuerySet

    def get_queryset(self) -> TenantQuerySet:
        qs = self.queryset_class(self.model, using=self._db)
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)

    def all_tenants(self) -> TenantQuerySet:
        """Uso exclusivo do app `owner` — consulta explicitamente cross-tenant."""
        return self.queryset_class(self.model, using=self._db)


class TenantModel(models.Model):
    """
    Base abstrata para todo model de domínio pertencente a um tenant.

    Reaproveitada por `core.Unidade`/`core.Fornecedor` e por todos os
    models dos apps `ativos` e `beneficiarios`.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")

    objects = TenantManager()

    class Meta:
        abstract = True


class Unidade(TenantModel):
    """
    Unidade física de um tenant (ex.: um posto/CRAS de uma prefeitura, uma
    filial de home care, uma loja de locadora — docs/features/
    identificacao-patrimonial-e-unidades.md).
    """

    nome = models.CharField(max_length=150)
    tipo = models.CharField(
        max_length=100,
        blank=True,
        help_text="Ex.: Matriz, Filial, Loja, Fundo Social — texto livre, varia por segmento.",
    )
    responsavel = models.CharField(max_length=150, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Unidade"
        verbose_name_plural = "Unidades"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nome"], name="unidade_unica_por_tenant")
        ]
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class Modulo(models.Model):
    """
    Catálogo de funcionalidades que podem ser ligadas/desligadas por tenant
    (docs/business-rules/modulos.md).

    Cross-tenant por natureza (é catálogo da plataforma, o mesmo para
    todos) — por isso não herda `TenantModel`. Populado por migration de
    dados (mesmo padrão de `contas.Papel`, ver
    `contas/migrations/0002_seed_papeis.py`), não por tela de cadastro:
    criar um módulo é decisão de produto, não operação de cliente.
    """

    codigo = models.SlugField(max_length=50, unique=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)

    class Meta:
        verbose_name = "Módulo"
        verbose_name_plural = "Módulos"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class TenantModulo(TenantModel):
    """
    Ativação explícita de um módulo para um tenant — sobrepõe o padrão do
    segmento (ver `core.features.modulo_habilitado`).

    Herda `TenantModel` só pelo campo `tenant` e pelo `TenantManager`
    (que dá `all_tenants()`) — a leitura de "este tenant específico tem
    este módulo?" é sempre feita com `tenant` explícito no filtro (nunca
    via ContextVar do tenant corrente), porque é chamada tanto de dentro
    de uma requisição quanto da tela do Owner (cross-tenant por definição).
    Ver `core.features` para a função que usa isto.
    """

    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="tenants")
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Módulo do Tenant"
        verbose_name_plural = "Módulos do Tenant"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "modulo"], name="tenant_modulo_unico")
        ]

    def __str__(self) -> str:
        return f"{self.tenant.nome} · {self.modulo.nome} · {'ativo' if self.ativo else 'inativo'}"


class Fornecedor(TenantModel):
    """Fornecedor/oficina/prestador usado em aquisição e manutenção de ativos."""

    nome = models.CharField(max_length=150)
    contato = models.CharField(max_length=150, blank=True)
    telefone = models.CharField(max_length=30, blank=True)

    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nome"], name="fornecedor_unico_por_tenant")
        ]
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome

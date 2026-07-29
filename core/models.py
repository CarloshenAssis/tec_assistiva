"""
Modelos centrais: Tenant (instituição cliente) e a infraestrutura de
isolamento multi-tenant (TenantModel/TenantManager) reutilizada por todos
os apps de domínio.

Ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3 para a justificativa da
estratégia (schema compartilhado + tenant_id, isolamento por manager).
"""

from django.db import models

from core.tenancy import get_current_tenant_id


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

    nome = models.CharField(max_length=150)
    slug = models.SlugField(max_length=60, unique=True)
    segmento = models.CharField(
        max_length=20, choices=Segmento.choices, default=Segmento.FUNDO_SOCIAL
    )
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        ordering = ["nome"]

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

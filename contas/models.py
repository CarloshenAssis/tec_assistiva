"""
Usuário e hierarquia de papéis (Owner/Admin/Gestor/Funcionário).

Ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3 — ponto arquitetural
crítico: o Owner é da plataforma, não de um tenant. Por isso
`Usuario.tenant` é nullable e `is_platform_staff` é o que diferencia um
usuário de equipe Ciclartech de um usuário de cliente.

`Papel` modela Admin/Gestor/Funcionário como um catálogo fixo e global
(não por tenant): a hierarquia em si (quem pode gerenciar quem) é uma
regra de produto, não uma configuração por cliente. As permissões finas
de "o que cada papel pode fazer em cada tela" continuam usando
`django.contrib.auth.Group`/`Permission` (padrão já decidido na v1.1),
combinadas ao `nivel_hierarquico` do papel para as regras de gestão de
usuários e para o serviço `AcoesDisponiveis` do app `ativos`.
"""

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Papel(models.Model):
    """Catálogo fixo e global de papéis (Admin/Gestor/Funcionário).

    Não é por tenant: a hierarquia em si (quem pode gerenciar quem) é
    regra de produto, não configuração por cliente.

    Attributes:
        codigo: Identificador único do papel (`Papel.Codigo`).
        nome: Nome de exibição do papel.
        nivel_hierarquico: Nível numérico único, usado para comparação de
            hierarquia (`Usuario.pode_gerenciar`) e para as regras de
            `ativos.domain.acoes`.
        pode_gerenciar_manutencao: Permissão adicional transversal
            (substitui o papel "Manutenção" do protótipo original — ver
            docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3.2).
    """

    class Codigo(models.TextChoices):
        ADMIN = "admin", "Administrador"
        GESTOR = "gestor", "Gestor"
        FUNCIONARIO = "funcionario", "Funcionário"

    codigo = models.CharField(max_length=20, choices=Codigo.choices, unique=True)
    nome = models.CharField(max_length=50)
    nivel_hierarquico = models.PositiveSmallIntegerField(unique=True)
    pode_gerenciar_manutencao = models.BooleanField(
        default=False,
        help_text="Permissão adicional transversal (substitui o papel "
        "'Manutenção' do protótipo original — ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3.2).",
    )

    class Meta:
        verbose_name = "Papel"
        verbose_name_plural = "Papéis"
        ordering = ["-nivel_hierarquico"]

    def __str__(self) -> str:
        return self.nome


class Usuario(AbstractUser):
    """Usuário customizado da plataforma — equipe Ciclartech ou de um tenant.

    Ponto arquitetural crítico (docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md
    §3): o Owner é da plataforma, não de um tenant. Por isso `tenant` é
    nullable e `is_platform_staff` é o que diferencia um usuário de
    equipe Ciclartech de um usuário de cliente.

    Attributes:
        tenant: FK para o `Tenant` do usuário. `None` para Owner.
        is_platform_staff: `True` para equipe Ciclartech (Owner), que não
            pertence a nenhum tenant.
        papel: FK para `Papel` — define a hierarquia deste usuário dentro
            do seu tenant. `None` para Owner.
        unidades: M2M para `core.Unidade` — unidades que este usuário
            pode operar/visualizar. Só tem efeito para Gestor/
            Funcionário; Admin sempre enxerga todas as unidades do
            tenant, independentemente do que estiver marcado aqui
            (docs/features/identificacao-patrimonial-e-unidades.md).

            Atenção: `usuario.unidades.all()` resolve pelo manager
            padrão de `Unidade` (`TenantManager`, fail-closed pelo
            ContextVar de tenant corrente — ver `core/tenancy.py`). Fora
            de uma view protegida por `tenant_required` (teste, shell,
            management command), isso devolve vazio mesmo com a
            atribuição existindo no banco. Para ler a atribuição fora de
            request context, use `core.unidades.unidades_do_usuario()`;
            para decidir "o que este usuário pode ver" (regra "Admin vê
            tudo" incluída), use `core.unidades.unidades_visiveis()`.
    """

    tenant = models.ForeignKey(
        "core.Tenant",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="usuarios",
    )
    is_platform_staff = models.BooleanField(
        default=False,
        help_text="Equipe Ciclartech (Owner). Não pertence a nenhum tenant.",
    )
    papel = models.ForeignKey(
        Papel, null=True, blank=True, on_delete=models.PROTECT, related_name="usuarios"
    )
    unidades = models.ManyToManyField(
        "core.Unidade",
        blank=True,
        related_name="usuarios_permitidos",
        help_text=(
            "Unidades que este usuário pode operar/visualizar. Só tem efeito para "
            "Gestor/Funcionário — Admin sempre enxerga todas as unidades do tenant, "
            "independentemente do que estiver marcado aqui (docs/features/"
            "identificacao-patrimonial-e-unidades.md)."
        ),
    )
    # ATENÇÃO: `usuario.unidades.all()` resolve pelo manager padrão de
    # `Unidade` (`TenantManager`, fail-closed pelo ContextVar de tenant
    # corrente — ver core/tenancy.py). Fora de uma view protegida por
    # `tenant_required` (teste, shell, management command), isso devolve
    # vazio mesmo com a atribuição existindo no banco. Para ler a atribuição
    # fora de request context, use `core.unidades.unidades_do_usuario()`; para
    # decidir "o que este usuário pode ver" (regra "Admin vê tudo" incluída),
    # use `core.unidades.unidades_visiveis()`.

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~(models.Q(is_platform_staff=True) & models.Q(tenant__isnull=False)),
                name="owner_nao_pertence_a_tenant",
            ),
        ]

    def clean(self):
        """Valida a consistência entre `is_platform_staff` e `tenant`.

        Raises:
            django.core.exceptions.ValidationError: Se um usuário da
                plataforma (Owner) tiver `tenant_id` definido, ou se um
                usuário de cliente (não Owner, não superusuário) não
                tiver `tenant_id`.
        """
        super().clean()
        if self.is_platform_staff and self.tenant_id:
            raise ValidationError(
                "Um usuário da plataforma (Owner) não pode pertencer a um tenant."
            )
        if not self.is_platform_staff and not self.is_superuser and self.tenant_id is None:
            raise ValidationError("Usuário de cliente precisa estar vinculado a um tenant.")

    def pode_gerenciar(self, outro_usuario: "Usuario") -> bool:
        """Verifica se este usuário pode gerenciar `outro_usuario`.

        Regra de hierarquia: Admin gerencia Gestor/Funcionário; Gestor
        não gerencia Admin; ninguém gerencia usuário de outro tenant.
        Owner gerencia toda a plataforma.

        Args:
            outro_usuario: O `Usuario` a ser gerenciado (editado,
                desativado, etc.).

        Returns:
            `True` se este usuário for Owner (`is_platform_staff`).
            Caso contrário, `True` somente se ambos pertencerem ao mesmo
            tenant, ambos tiverem `papel` definido, e o
            `nivel_hierarquico` deste usuário for maior ou igual ao de
            `outro_usuario`.
        """
        if self.is_platform_staff:
            return True
        if outro_usuario.tenant_id != self.tenant_id:
            return False
        if not self.papel or not outro_usuario.papel:
            return False
        return self.papel.nivel_hierarquico >= outro_usuario.papel.nivel_hierarquico

    def __str__(self) -> str:
        return self.get_username()

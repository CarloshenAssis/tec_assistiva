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

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~(models.Q(is_platform_staff=True) & models.Q(tenant__isnull=False)),
                name="owner_nao_pertence_a_tenant",
            ),
        ]

    def clean(self):
        super().clean()
        if self.is_platform_staff and self.tenant_id:
            raise ValidationError(
                "Um usuário da plataforma (Owner) não pode pertencer a um tenant."
            )
        if not self.is_platform_staff and not self.is_superuser and self.tenant_id is None:
            raise ValidationError("Usuário de cliente precisa estar vinculado a um tenant.")

    def pode_gerenciar(self, outro_usuario: "Usuario") -> bool:
        """
        Regra de hierarquia: Admin gerencia Gestor/Funcionário; Gestor não
        gerencia Admin; ninguém gerencia usuário de outro tenant. Owner
        gerencia toda a plataforma.
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

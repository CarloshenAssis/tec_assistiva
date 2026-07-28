from django.core.exceptions import ValidationError
from django.test import TestCase

from contas.models import Papel, Usuario
from core.models import Tenant


class HierarquiaOwnerAdminGestorFuncionarioTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura A", slug="prefeitura-a")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura B", slug="prefeitura-b")

        # Os três papéis já existem via migration de dados (0002_seed_papeis) —
        # ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3.2.
        self.admin = Papel.objects.get(codigo="admin")
        self.gestor = Papel.objects.get(codigo="gestor")
        self.funcionario = Papel.objects.get(codigo="funcionario")

    def _criar_usuario(self, username, tenant, papel):
        return Usuario.objects.create_user(
            username=username, password="senha-teste-123", tenant=tenant, papel=papel
        )

    def test_owner_nao_pode_ter_tenant(self):
        owner = Usuario(username="owner1", is_platform_staff=True, tenant=self.tenant_a)
        with self.assertRaises(ValidationError):
            owner.full_clean()

    def test_usuario_de_tenant_precisa_de_tenant(self):
        usuario = Usuario(username="sem-tenant")
        with self.assertRaises(ValidationError):
            usuario.full_clean()

    def test_admin_gerencia_gestor_e_funcionario(self):
        admin = self._criar_usuario("admin1", self.tenant_a, self.admin)
        gestor = self._criar_usuario("gestor1", self.tenant_a, self.gestor)
        funcionario = self._criar_usuario("func1", self.tenant_a, self.funcionario)

        self.assertTrue(admin.pode_gerenciar(gestor))
        self.assertTrue(admin.pode_gerenciar(funcionario))

    def test_gestor_nao_gerencia_admin(self):
        admin = self._criar_usuario("admin2", self.tenant_a, self.admin)
        gestor = self._criar_usuario("gestor2", self.tenant_a, self.gestor)

        self.assertFalse(gestor.pode_gerenciar(admin))

    def test_ninguem_gerencia_usuario_de_outro_tenant(self):
        admin_a = self._criar_usuario("admin3", self.tenant_a, self.admin)
        funcionario_b = self._criar_usuario("func-b", self.tenant_b, self.funcionario)

        self.assertFalse(admin_a.pode_gerenciar(funcionario_b))

    def test_owner_gerencia_qualquer_usuario_de_qualquer_tenant(self):
        owner = Usuario.objects.create_user(username="owner2", password="x", is_platform_staff=True)
        funcionario_b = self._criar_usuario("func-b2", self.tenant_b, self.funcionario)

        self.assertTrue(owner.pode_gerenciar(funcionario_b))

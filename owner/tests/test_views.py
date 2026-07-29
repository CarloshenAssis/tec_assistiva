"""
Área da plataforma (Owner) — controle de contratos e geração do primeiro
acesso do administrador de cada B2G/B2B.
"""

from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.urls import reverse

from auditoria.models import AcaoAuditada, RegistroAuditoria
from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"


class AcessoRestritoTest(TestCase):
    """`/owner/*` é exclusivo de is_platform_staff — o espelho de tenant_required."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Owner", slug="pref-owner-acesso")
        self.usuario_tenant = Usuario.objects.create_user(
            username="func_owner_teste",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.owner = Usuario.objects.create_user(
            username="owner_teste", password=SENHA, is_platform_staff=True
        )

    def test_usuario_de_tenant_e_bloqueado(self):
        self.client.login(username="func_owner_teste", password=SENHA)
        resposta = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(403, resposta.status_code)

    def test_platform_staff_acessa(self):
        self.client.login(username="owner_teste", password=SENHA)
        resposta = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(200, resposta.status_code)

    def test_anonimo_e_redirecionado_para_login(self):
        resposta = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(302, resposta.status_code)


class DashboardTest(TestCase):
    def setUp(self):
        self.owner = Usuario.objects.create_user(
            username="owner_dash", password=SENHA, is_platform_staff=True
        )
        Tenant.objects.create(nome="Prefeitura Dash A", slug="pref-dash-a", ativo=True)
        Tenant.objects.create(nome="Prefeitura Dash B", slug="pref-dash-b", ativo=False)

    def test_lista_todos_os_contratos(self):
        self.client.login(username="owner_dash", password=SENHA)
        resposta = self.client.get(reverse("owner:dashboard"))
        self.assertContains(resposta, "Prefeitura Dash A")
        self.assertContains(resposta, "Prefeitura Dash B")

    def test_conta_contratos_ativos_corretamente(self):
        self.client.login(username="owner_dash", password=SENHA)
        resposta = self.client.get(reverse("owner:dashboard"))
        self.assertEqual(1, resposta.context["total_ativos"])
        self.assertEqual(2, resposta.context["total_tenants"])


class CriarTenantTest(TestCase):
    def setUp(self):
        self.owner = Usuario.objects.create_user(
            username="owner_criar_tenant", password=SENHA, is_platform_staff=True
        )

    def test_cria_novo_contrato(self):
        self.client.login(username="owner_criar_tenant", password=SENHA)
        resposta = self.client.post(
            reverse("owner:criar_tenant"),
            {
                "nome": "Fundo Social XPTO",
                "slug": "fundo-social-xpto",
                "segmento": "fundo_social",
                "cidade": "Campinas",
                "uf": "SP",
                "ativo": "on",
            },
        )
        tenant = Tenant.objects.get(slug="fundo-social-xpto")
        self.assertRedirects(resposta, reverse("owner:tenant_detalhe", args=[tenant.pk]))


class AlternarAtivoTest(TestCase):
    def setUp(self):
        self.owner = Usuario.objects.create_user(
            username="owner_alt", password=SENHA, is_platform_staff=True
        )
        self.tenant = Tenant.objects.create(nome="Prefeitura Alt", slug="pref-alt-owner", ativo=True)

    def test_suspende_contrato_ativo(self):
        self.client.login(username="owner_alt", password=SENHA)
        self.client.post(reverse("owner:alternar_tenant_ativo", args=[self.tenant.pk]))
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.ativo)

    def test_exige_post(self):
        self.client.login(username="owner_alt", password=SENHA)
        resposta = self.client.get(reverse("owner:alternar_tenant_ativo", args=[self.tenant.pk]))
        self.assertEqual(403, resposta.status_code)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.ativo)


class CriarAdministradorTest(TestCase):
    """
    O caso central do pedido: o Owner gera o primeiro acesso do
    administrador de um contrato B2G/B2B.
    """

    def setUp(self):
        self.owner = Usuario.objects.create_user(
            username="owner_criar_admin", password=SENHA, is_platform_staff=True
        )
        self.tenant = Tenant.objects.create(nome="Prefeitura Admin", slug="pref-admin-novo")

    def _criar(self):
        self.client.login(username="owner_criar_admin", password=SENHA)
        return self.client.post(
            reverse("owner:criar_administrador", args=[self.tenant.pk]),
            {
                "username": "admin_novo_contrato",
                "email": "admin@prefeitura.gov.br",
                "first_name": "Ana",
                "last_name": "Souza",
            },
        )

    def test_cria_usuario_com_papel_admin_no_tenant_certo(self):
        self._criar()
        usuario = Usuario.objects.get(username="admin_novo_contrato")
        self.assertEqual(self.tenant, usuario.tenant)
        self.assertEqual("admin", usuario.papel.codigo)
        self.assertTrue(usuario.is_active)

    def test_mostra_a_senha_uma_vez_na_tela_de_sucesso(self):
        resposta = self._criar()
        self.assertContains(resposta, "admin_novo_contrato")
        self.assertContains(resposta, "Senha temporária")
        self.assertEqual(16, len(resposta.context["senha"]))

    def test_senha_gerada_nao_e_previsivel(self):
        """A senha não pode ser derivada do username/e-mail — é aleatória."""
        self._criar()
        usuario = Usuario.objects.get(username="admin_novo_contrato")
        self.assertFalse(check_password("admin_novo_contrato", usuario.password))
        self.assertFalse(check_password("admin@prefeitura.gov.br", usuario.password))

    def test_username_duplicado_e_rejeitado(self):
        Usuario.objects.create_user(username="admin_novo_contrato", password=SENHA)
        resposta = self._criar()
        self.assertEqual(200, resposta.status_code)  # reexibe com erro
        self.assertEqual(
            1, Usuario.objects.filter(username="admin_novo_contrato").count()
        )

    def test_criacao_e_auditada(self):
        self._criar()
        usuario = Usuario.objects.get(username="admin_novo_contrato")
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.CRIACAO,
                objeto_tipo="contas.Usuario",
                objeto_id=str(usuario.pk),
                tenant=self.tenant,
            ).exists()
        )


class AuditoriaGeralTest(TestCase):
    """Visão cross-tenant — só o Owner enxerga registros de todos os contratos juntos."""

    def setUp(self):
        self.owner = Usuario.objects.create_user(
            username="owner_audit", password=SENHA, is_platform_staff=True
        )
        self.tenant_a = Tenant.objects.create(nome="Prefeitura Aud A", slug="pref-aud-a")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura Aud B", slug="pref-aud-b")

    def test_mostra_registros_de_tenants_diferentes(self):
        RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO, tenant=self.tenant_a, usuario_identificacao="a"
        )
        RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO, tenant=self.tenant_b, usuario_identificacao="b"
        )
        self.client.login(username="owner_audit", password=SENHA)
        resposta = self.client.get(reverse("owner:auditoria"))
        registros = list(resposta.context["pagina"])
        tenants_vistos = {r.tenant_id for r in registros}
        self.assertIn(self.tenant_a.pk, tenants_vistos)
        self.assertIn(self.tenant_b.pk, tenants_vistos)

    def test_filtro_por_contrato(self):
        RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO, tenant=self.tenant_a, usuario_identificacao="a"
        )
        RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO, tenant=self.tenant_b, usuario_identificacao="b"
        )
        self.client.login(username="owner_audit", password=SENHA)
        resposta = self.client.get(reverse("owner:auditoria"), {"tenant": self.tenant_a.pk})
        registros = list(resposta.context["pagina"])
        self.assertTrue(all(r.tenant_id == self.tenant_a.pk for r in registros))

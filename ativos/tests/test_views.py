"""
Testes de integração das views (Fase 1) — cobrindo login/RBAC, isolamento
multi-tenant na camada HTTP e o fluxo do wizard de empréstimo ponta a ponta.
"""

from django.test import Client, TestCase
from django.urls import reverse

from ativos.models import Ativo, CategoriaAtivo
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant


class BaseViewTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura A", slug="pref-a-views")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura B", slug="pref-b-views")

        self.papel_admin = Papel.objects.get(codigo="admin")
        self.papel_gestor = Papel.objects.get(codigo="gestor")
        self.papel_funcionario = Papel.objects.get(codigo="funcionario")

        self.gestor_a = Usuario.objects.create_user(
            username="gestor_a", password="senha-teste-123", tenant=self.tenant_a, papel=self.papel_gestor
        )
        self.funcionario_a = Usuario.objects.create_user(
            username="func_a", password="senha-teste-123", tenant=self.tenant_a, papel=self.papel_funcionario
        )
        self.gestor_b = Usuario.objects.create_user(
            username="gestor_b", password="senha-teste-123", tenant=self.tenant_b, papel=self.papel_gestor
        )

        self.categoria_a = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Cadeira de Rodas"
        )
        self.ativo_a = Ativo.objects.all_tenants().create(
            tenant=self.tenant_a, patrimonio="CAD-0001", categoria=self.categoria_a
        )
        self.beneficiario_a = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Maria Silva", cpf="123.456.789-00"
        )

        categoria_b = CategoriaAtivo.objects.all_tenants().create(tenant=self.tenant_b, nome="Muletas")
        self.ativo_b = Ativo.objects.all_tenants().create(
            tenant=self.tenant_b, patrimonio="MUL-0001", categoria=categoria_b
        )


class AutenticacaoTest(BaseViewTest):
    def test_dashboard_exige_login(self):
        response = self.client.get(reverse("app:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_dashboard_acessivel_apos_login(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.get(reverse("app:dashboard"))
        self.assertEqual(response.status_code, 200)


class IsolamentoMultiTenantNasViewsTest(BaseViewTest):
    def test_lista_de_ativos_nao_mostra_ativo_de_outro_tenant(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.get(reverse("app:ativos:lista"))
        self.assertContains(response, "CAD-0001")
        self.assertNotContains(response, "MUL-0001")

    def test_ficha_de_ativo_de_outro_tenant_devolve_404(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.get(reverse("app:ativos:ficha", args=[self.ativo_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_qr_de_ativo_de_outro_tenant_nao_e_encontrado(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.get(reverse("app:ativos:resolver_qr", args=[self.ativo_b.qr_token]))
        self.assertEqual(response.status_code, 404)

    def test_qr_do_proprio_tenant_e_resolvido(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.get(reverse("app:ativos:resolver_qr", args=[self.ativo_a.qr_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CAD-0001")


class RBACNasViewsTest(BaseViewTest):
    def test_funcionario_nao_pode_criar_ativo(self):
        self.client.login(username="func_a", password="senha-teste-123")
        response = self.client.get(reverse("app:ativos:criar"))
        self.assertEqual(response.status_code, 403)

    def test_gestor_pode_criar_ativo(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.post(
            reverse("app:ativos:criar"),
            {"patrimonio": "CAD-9999", "categoria": self.categoria_a.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Ativo.objects.all_tenants().filter(tenant=self.tenant_a, patrimonio="CAD-9999").exists())

    def test_funcionario_nao_ve_botao_editar_na_ficha(self):
        self.client.login(username="func_a", password="senha-teste-123")
        response = self.client.get(reverse("app:ativos:ficha", args=[self.ativo_a.pk]))
        self.assertNotContains(response, "Editar</a>")

    def test_funcionario_nao_pode_executar_acao_de_gestor_diretamente(self):
        self.client.login(username="func_a", password="senha-teste-123")
        response = self.client.post(reverse("app:ativos:executar_acao", args=[self.ativo_a.pk, "dar_baixa"]))
        self.assertEqual(response.status_code, 403)


class WizardEmprestimoTest(BaseViewTest):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username="func_a", password="senha-teste-123")

    def test_fluxo_completo_do_wizard(self):
        url = reverse("app:ativos:wizard_emprestimo")

        resposta = self.client.post(
            url, {"wizard_acao": "selecionar_beneficiario", "beneficiario_id": self.beneficiario_a.pk}
        )
        self.assertEqual(resposta.status_code, 302)

        resposta = self.client.get(url)
        self.assertContains(resposta, "Passo 2")

        resposta = self.client.post(
            url, {"wizard_acao": "selecionar_ativo", "ativo_id": self.ativo_a.pk}
        )
        self.assertEqual(resposta.status_code, 302)

        resposta = self.client.get(url)
        self.assertContains(resposta, "Passo 3")

        resposta = self.client.post(url, {"wizard_acao": "definir_prazo", "prazo_dias": "30"})
        self.assertEqual(resposta.status_code, 302)

        resposta = self.client.get(url)
        self.assertContains(resposta, "Passo 4")

        resposta = self.client.post(
            url,
            {
                "wizard_acao": "confirmar",
                "checklist_termo_impresso": "on",
                "checklist_termo_assinado": "on",
            },
        )
        self.assertContains(resposta, "Empréstimo registrado")

        self.ativo_a.refresh_from_db()
        self.assertEqual(self.ativo_a.status, "emprestado")

    def test_voltar_limpa_o_passo_atual(self):
        url = reverse("app:ativos:wizard_emprestimo")
        self.client.post(url, {"wizard_acao": "selecionar_beneficiario", "beneficiario_id": self.beneficiario_a.pk})
        self.client.post(url, {"wizard_acao": "selecionar_ativo", "ativo_id": self.ativo_a.pk})

        self.client.post(url, {"wizard_acao": "voltar"})
        resposta = self.client.get(url)
        self.assertContains(resposta, "Passo 2")


class TelasComplementaresTest(BaseViewTest):
    def test_agenda_acessivel(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.get(reverse("app:ativos:agenda"))
        self.assertEqual(response.status_code, 200)

    def test_relatorios_acessivel(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.get(reverse("app:relatorios"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total de ativos")

    def test_notificacoes_acessivel(self):
        self.client.login(username="gestor_a", password="senha-teste-123")
        response = self.client.get(reverse("app:notificacoes:lista"))
        self.assertEqual(response.status_code, 200)

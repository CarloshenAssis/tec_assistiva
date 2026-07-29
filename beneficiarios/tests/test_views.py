from django.test import TestCase
from django.urls import reverse

from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant


class BeneficiarioViewsTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura A", slug="pref-a-benef")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura B", slug="pref-b-benef")
        papel_funcionario = Papel.objects.get(codigo="funcionario")

        self.usuario_a = Usuario.objects.create_user(
            username="func_benef_a", password="senha-teste-123", tenant=self.tenant_a, papel=papel_funcionario
        )
        self.beneficiario_a = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Maria Silva", cpf="123.456.789-09"
        )
        self.beneficiario_b = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_b, nome="João Pedro", cpf="234.567.891-73"
        )

    def test_lista_isolada_por_tenant(self):
        self.client.login(username="func_benef_a", password="senha-teste-123")
        response = self.client.get(reverse("app:beneficiarios:lista"))
        self.assertContains(response, "Maria Silva")
        self.assertNotContains(response, "João Pedro")

    def test_ficha_de_beneficiario_de_outro_tenant_devolve_404(self):
        self.client.login(username="func_benef_a", password="senha-teste-123")
        response = self.client.get(reverse("app:beneficiarios:ficha", args=[self.beneficiario_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_criar_beneficiario(self):
        self.client.login(username="func_benef_a", password="senha-teste-123")
        response = self.client.post(
            reverse("app:beneficiarios:criar"),
            {
                "tipo_relacao": "beneficiario",
                "nome": "Ana Costa",
                "cpf": "456.789.123-64",
                # Declarar a base legal do tratamento passou a ser obrigatório
                # no cadastro (LGPD Art. 7º/11) — ver beneficiarios/forms.py.
                "base_legal": "consentimento",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Beneficiario.objects.all_tenants().filter(tenant=self.tenant_a, cpf="456.789.123-64").exists()
        )

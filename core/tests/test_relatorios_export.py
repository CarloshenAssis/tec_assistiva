"""
Exportação de relatórios em CSV (docs/business-rules/relatorios.md).
"""

from django.test import TestCase
from django.urls import reverse

from ativos import services
from ativos.models import Ativo, CategoriaAtivo
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id

SENHA = "senha-bem-longa-2026"


class ExportarRelatoriosTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Export", slug="pref-export")
        token = set_current_tenant_id(self.tenant.pk)
        self.addCleanup(reset_current_tenant_id, token)

        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.outra_unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Filial")

        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-0001", categoria=self.categoria, unidade=self.unidade
        )
        self.ativo_de_outra_unidade = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-9999", categoria=self.categoria, unidade=self.outra_unidade
        )
        self.beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Maria da Silva", documento="123.456.789-09", unidade=self.unidade
        )
        self.beneficiario_de_outra_unidade = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="João de Outra Unidade", documento="987.654.321-00",
            unidade=self.outra_unidade,
        )
        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=10)

        self.func = Usuario.objects.create_user(
            username="func_export", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="funcionario")
        )
        self.func.unidades.add(self.unidade)

    def test_exportar_ativos_e_csv_com_escopo_de_unidade(self):
        self.client.login(username="func_export", password=SENHA)
        resposta = self.client.get(reverse("app:relatorios_exportar_ativos"))
        self.assertEqual(200, resposta.status_code)
        self.assertEqual("text/csv; charset=utf-8-sig", resposta["Content-Type"])
        conteudo = resposta.content.decode("utf-8-sig")
        self.assertIn("CAD-0001", conteudo)
        self.assertNotIn("CAD-9999", conteudo)

    def test_exportar_beneficiarios_e_csv_com_escopo_de_unidade(self):
        self.client.login(username="func_export", password=SENHA)
        resposta = self.client.get(reverse("app:relatorios_exportar_beneficiarios"))
        conteudo = resposta.content.decode("utf-8-sig")
        self.assertIn("Maria da Silva", conteudo)
        self.assertNotIn("João de Outra Unidade", conteudo)

    def test_exportar_movimentacoes_e_csv_com_escopo_de_unidade(self):
        self.client.login(username="func_export", password=SENHA)
        resposta = self.client.get(reverse("app:relatorios_exportar_movimentacoes"))
        conteudo = resposta.content.decode("utf-8-sig")
        self.assertIn("CAD-0001", conteudo)
        self.assertIn("Maria da Silva", conteudo)
        self.assertIn("Empréstimo", conteudo)

    def test_exportacao_exige_login(self):
        resposta = self.client.get(reverse("app:relatorios_exportar_ativos"))
        self.assertEqual(302, resposta.status_code)

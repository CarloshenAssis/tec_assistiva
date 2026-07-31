"""
Cadastro rápido de Subcategoria/Fornecedor embutido no formulário de Ativo
(ativos/views_categorias.py::subcategoria_criar_rapida,
core/views_fornecedores.py::fornecedor_criar_rapido).
"""

from django.test import TestCase
from django.urls import reverse

from ativos.models import CategoriaAtivo, SubcategoriaAtivo
from contas.models import Papel, Usuario
from core.models import Fornecedor, Tenant

SENHA = "senha-bem-longa-2026"


class SubcategoriaCriarRapidaTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Cad Rapido", slug="pref-cad-rapido")
        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_cad_rapido", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="gestor")
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_cad_rapido",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_funcionario_nao_pode(self):
        self.client.login(username="func_cad_rapido", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:subcategoria_criar_rapida"),
            {"categoria_id": self.categoria.pk, "nome": "4 rodas"},
        )
        self.assertEqual(403, resposta.status_code)

    def test_gestor_cadastra_e_recebe_json(self):
        self.client.login(username="gestor_cad_rapido", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:subcategoria_criar_rapida"),
            {"categoria_id": self.categoria.pk, "nome": "4 rodas"},
        )
        self.assertEqual(200, resposta.status_code)
        dados = resposta.json()
        self.assertEqual("4 rodas", dados["nome"])
        subcategoria = SubcategoriaAtivo.objects.all_tenants().get(pk=dados["id"])
        self.assertEqual(self.categoria, subcategoria.categoria)
        self.assertEqual(self.tenant, subcategoria.tenant)

    def test_nome_repetido_reaproveita_em_vez_de_duplicar(self):
        self.client.login(username="gestor_cad_rapido", password=SENHA)
        url = reverse("app:ativos:subcategoria_criar_rapida")
        r1 = self.client.post(url, {"categoria_id": self.categoria.pk, "nome": "4 rodas"})
        r2 = self.client.post(url, {"categoria_id": self.categoria.pk, "nome": "4 RODAS"})
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(
            1, SubcategoriaAtivo.objects.all_tenants().filter(categoria=self.categoria).count()
        )

    def test_nome_vazio_e_erro_amigavel(self):
        self.client.login(username="gestor_cad_rapido", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:subcategoria_criar_rapida"),
            {"categoria_id": self.categoria.pk, "nome": "  "},
        )
        self.assertEqual(400, resposta.status_code)
        self.assertIn("erro", resposta.json())

    def test_exige_post(self):
        self.client.login(username="gestor_cad_rapido", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:subcategoria_criar_rapida"))
        self.assertEqual(403, resposta.status_code)

    def test_categoria_de_outro_tenant_404(self):
        outro_tenant = Tenant.objects.create(nome="Outra Cad Rapido", slug="outra-cad-rapido")
        categoria_de_outro = CategoriaAtivo.objects.all_tenants().create(tenant=outro_tenant, nome="Muletas")
        self.client.login(username="gestor_cad_rapido", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:subcategoria_criar_rapida"),
            {"categoria_id": categoria_de_outro.pk, "nome": "Axilar"},
        )
        self.assertEqual(404, resposta.status_code)


class FornecedorCriarRapidoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Forn Rapido", slug="pref-forn-rapido")
        self.gestor = Usuario.objects.create_user(
            username="gestor_forn_rapido", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="gestor")
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_forn_rapido",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_funcionario_nao_pode(self):
        self.client.login(username="func_forn_rapido", password=SENHA)
        resposta = self.client.post(reverse("app:fornecedores:criar_rapido"), {"nome": "Ortobras"})
        self.assertEqual(403, resposta.status_code)

    def test_gestor_cadastra_e_recebe_json(self):
        self.client.login(username="gestor_forn_rapido", password=SENHA)
        resposta = self.client.post(reverse("app:fornecedores:criar_rapido"), {"nome": "Ortobras"})
        self.assertEqual(200, resposta.status_code)
        dados = resposta.json()
        self.assertEqual("Ortobras", dados["nome"])
        fornecedor = Fornecedor.objects.all_tenants().get(pk=dados["id"])
        self.assertEqual(self.tenant, fornecedor.tenant)

    def test_nome_repetido_reaproveita_em_vez_de_duplicar(self):
        self.client.login(username="gestor_forn_rapido", password=SENHA)
        url = reverse("app:fornecedores:criar_rapido")
        r1 = self.client.post(url, {"nome": "Ortobras"})
        r2 = self.client.post(url, {"nome": "ortobras"})
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(
            1, Fornecedor.objects.all_tenants().filter(tenant=self.tenant).count()
        )


class LinkFornecedoresRetiradoDoMenuTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Menu Forn", slug="pref-menu-forn")
        self.admin = Usuario.objects.create_user(
            username="admin_menu_forn", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="admin")
        )

    def test_menu_nao_mostra_mais_o_link_mas_url_continua_no_ar(self):
        self.client.login(username="admin_menu_forn", password=SENHA)
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertNotIn(reverse("app:fornecedores:lista"), resposta.content.decode())

        resposta_tela_cheia = self.client.get(reverse("app:fornecedores:lista"))
        self.assertEqual(200, resposta_tela_cheia.status_code)

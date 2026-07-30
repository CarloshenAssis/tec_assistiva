"""
Localizar Ativo — tela única reunindo QR/patrimônio/categoria/nome
(docs/business-rules/qrcode.md).
"""

from django.test import TestCase
from django.urls import reverse

from ativos.models import Ativo, CategoriaAtivo
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade

SENHA = "senha-bem-longa-2026"


class LocalizarAtivoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Localizar", slug="pref-localizar")
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.outra_unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Filial")

        self.cadeiras = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.muletas = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Muletas", prefixo="MUL"
        )
        self.cadeira = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-0001", categoria=self.cadeiras,
            fabricante="Ortobras", unidade=self.unidade,
        )
        self.muleta = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="MUL-0001", categoria=self.muletas, unidade=self.unidade
        )
        self.ativo_de_outra_unidade = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-9999", categoria=self.cadeiras, unidade=self.outra_unidade
        )

        self.func = Usuario.objects.create_user(
            username="func_localizar", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="funcionario")
        )
        self.func.unidades.add(self.unidade)

    def test_sem_filtro_nao_lista_nada(self):
        """Localizar não é um browser do acervo inteiro — só resultado de busca."""
        self.client.login(username="func_localizar", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:localizar"))
        self.assertNotContains(resposta, "CAD-0001")
        self.assertContains(resposta, "Digite um termo")

    def test_busca_por_patrimonio(self):
        self.client.login(username="func_localizar", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:localizar"), {"q": "CAD-0001"})
        self.assertContains(resposta, "CAD-0001")
        self.assertNotContains(resposta, "MUL-0001")

    def test_busca_por_categoria_texto(self):
        self.client.login(username="func_localizar", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:localizar"), {"q": "Muletas"})
        self.assertContains(resposta, "MUL-0001")
        self.assertNotContains(resposta, "CAD-0001")

    def test_busca_por_fabricante(self):
        self.client.login(username="func_localizar", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:localizar"), {"q": "Ortobras"})
        self.assertContains(resposta, "CAD-0001")

    def test_filtro_por_categoria_dropdown(self):
        self.client.login(username="func_localizar", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:localizar"), {"categoria": self.muletas.pk})
        self.assertContains(resposta, "MUL-0001")
        self.assertNotContains(resposta, "CAD-0001")

    def test_busca_respeita_escopo_de_unidade(self):
        """Ativo de outra unidade não aparece mesmo batendo o texto buscado."""
        self.client.login(username="func_localizar", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:localizar"), {"q": "CAD"})
        self.assertContains(resposta, "CAD-0001")
        self.assertNotContains(resposta, "CAD-9999")

    def test_resultado_linka_para_a_ficha(self):
        self.client.login(username="func_localizar", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:localizar"), {"q": "CAD-0001"})
        self.assertContains(resposta, reverse("app:ativos:ficha", args=[self.cadeira.pk]))

    def test_formulario_de_codigo_manual_ainda_posta_para_scan(self):
        """A busca por câmera/código continua usando o mesmo backend já testado."""
        self.client.login(username="func_localizar", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:localizar"))
        self.assertContains(resposta, reverse("app:ativos:scan"))

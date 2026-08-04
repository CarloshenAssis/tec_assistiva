"""
Views de imagem autenticadas (fotos de ativo/movimentação, logotipo do
tenant) — servidas por view, nunca por link direto ao storage, para o
navegador conseguir cachear (ver core/arquivos.py::resposta_de_imagem).

Cobre também o escopo de tenant/unidade: uma foto de outro tenant/unidade
tem que responder 404, do mesmo jeito que qualquer outro recurso de Ativo.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from ativos import services
from ativos.models import Ativo, CategoriaAtivo, FotoAtivo
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id

SENHA = "senha-bem-longa-2026"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class BaseFotos(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Fotos", slug="pref-fotos")
        token = set_current_tenant_id(self.tenant.pk)
        self.addCleanup(reset_current_tenant_id, token)

        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-0001", categoria=self.categoria, unidade=self.unidade
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_fotos",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.funcionario.unidades.add(self.unidade)

        self.foto = FotoAtivo.objects.create(
            tenant=self.tenant,
            ativo=self.ativo,
            tipo=FotoAtivo.Tipo.PRINCIPAL,
            arquivo=SimpleUploadedFile("foto.png", PNG),
        )

    def logar(self):
        self.assertTrue(self.client.login(username="func_fotos", password=SENHA))


class FotoAtivoImagemTest(BaseFotos):
    def test_serve_a_imagem_com_cache_longo(self):
        self.logar()
        resposta = self.client.get(reverse("app:ativos:foto_ativo_imagem", args=[self.foto.pk]))
        self.assertEqual(200, resposta.status_code)
        self.assertIn("image/png", resposta["Content-Type"])
        self.assertIn("max-age=31536000", resposta["Cache-Control"])
        self.assertIn("private", resposta["Cache-Control"])

    def test_exige_login(self):
        resposta = self.client.get(reverse("app:ativos:foto_ativo_imagem", args=[self.foto.pk]))
        self.assertNotEqual(200, resposta.status_code)

    def test_foto_de_ativo_de_outra_unidade_e_404(self):
        outra_unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Filial")
        ativo_alheio = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-ALHEIO", categoria=self.categoria, unidade=outra_unidade
        )
        foto_alheia = FotoAtivo.objects.create(
            tenant=self.tenant,
            ativo=ativo_alheio,
            tipo=FotoAtivo.Tipo.PRINCIPAL,
            arquivo=SimpleUploadedFile("foto2.png", PNG),
        )
        self.logar()
        resposta = self.client.get(reverse("app:ativos:foto_ativo_imagem", args=[foto_alheia.pk]))
        self.assertEqual(404, resposta.status_code)

    def test_foto_de_outro_tenant_e_404(self):
        outro_tenant = Tenant.objects.create(nome="Outra Prefeitura", slug="outra-pref")
        token = set_current_tenant_id(outro_tenant.pk)
        try:
            outra_unidade = Unidade.objects.all_tenants().create(tenant=outro_tenant, nome="Sede")
            outra_categoria = CategoriaAtivo.objects.all_tenants().create(
                tenant=outro_tenant, nome="Muletas", prefixo="MUL"
            )
            ativo_outro_tenant = Ativo.objects.all_tenants().create(
                tenant=outro_tenant, patrimonio="MUL-0001", categoria=outra_categoria, unidade=outra_unidade
            )
            foto_outro_tenant = FotoAtivo.objects.create(
                tenant=outro_tenant,
                ativo=ativo_outro_tenant,
                tipo=FotoAtivo.Tipo.PRINCIPAL,
                arquivo=SimpleUploadedFile("foto3.png", PNG),
            )
        finally:
            reset_current_tenant_id(token)

        self.logar()
        resposta = self.client.get(reverse("app:ativos:foto_ativo_imagem", args=[foto_outro_tenant.pk]))
        self.assertEqual(404, resposta.status_code)


class FotoMovimentacaoImagemTest(BaseFotos):
    def test_serve_a_imagem_de_uma_foto_de_movimentacao(self):
        self.logar()
        movimentacao = services.enviar_manutencao(self.ativo, self.funcionario, motivo="Roda solta")
        movimentacao = services.retornar_manutencao(self.ativo, self.funcionario)
        foto_mov = services.anexar_foto(movimentacao, SimpleUploadedFile("mov.png", PNG))

        resposta = self.client.get(reverse("app:ativos:foto_movimentacao_imagem", args=[foto_mov.pk]))
        self.assertEqual(200, resposta.status_code)
        self.assertIn("image/png", resposta["Content-Type"])


class LogoImagemTest(BaseFotos):
    def test_404_quando_tenant_nao_tem_logo(self):
        self.logar()
        resposta = self.client.get(reverse("app:logo_imagem"))
        self.assertEqual(404, resposta.status_code)

    def test_serve_o_logo_quando_configurado(self):
        self.tenant.logo = SimpleUploadedFile("logo.png", PNG)
        self.tenant.save()
        self.logar()
        resposta = self.client.get(reverse("app:logo_imagem"))
        self.assertEqual(200, resposta.status_code)
        self.assertIn("image/png", resposta["Content-Type"])
        self.assertIn("max-age=31536000", resposta["Cache-Control"])

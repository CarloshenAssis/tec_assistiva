"""
Vocabulário de tela por segmento do tenant (`core.context_processors.vocabulario`).

O front muda de nome ("Beneficiário" vs "Cliente" vs "Paciente") conforme o
segmento — mesmo model, mesmas regras, só o rótulo muda. Cobre o motivo
concreto que gerou o pedido: confirmar que o front de uma Locadora não é
idêntico ao de uma prefeitura.
"""

from django.test import TestCase
from django.urls import reverse

from contas.models import Papel, Usuario
from core.models import Tenant


class RotuloPorSegmentoNoModelTest(TestCase):
    def test_locadora_usa_cliente(self):
        tenant = Tenant.objects.create(nome="Locadora X", slug="locadora-x", segmento=Tenant.Segmento.LOCADORA)
        self.assertEqual("Cliente", tenant.rotulo_beneficiario_singular)
        self.assertEqual("Clientes", tenant.rotulo_beneficiario_plural)

    def test_home_care_e_hospital_usam_paciente(self):
        for segmento in (Tenant.Segmento.HOME_CARE, Tenant.Segmento.HOSPITAL):
            tenant = Tenant.objects.create(
                nome=f"Tenant {segmento}", slug=f"tenant-{segmento}", segmento=segmento
            )
            self.assertEqual("Paciente", tenant.rotulo_beneficiario_singular)
            self.assertEqual("Pacientes", tenant.rotulo_beneficiario_plural)

    def test_fundo_social_e_ong_usam_beneficiario(self):
        for segmento in (Tenant.Segmento.FUNDO_SOCIAL, Tenant.Segmento.ONG):
            tenant = Tenant.objects.create(
                nome=f"Tenant {segmento}", slug=f"tenant-b-{segmento}", segmento=segmento
            )
            self.assertEqual("Beneficiário", tenant.rotulo_beneficiario_singular)


class VocabularioNasTelasTest(TestCase):
    """O rótulo aparece de fato na tela renderizada, não só no model."""

    SENHA = "senha-bem-longa-2026"

    def setUp(self):
        self.locadora = Tenant.objects.create(
            nome="Locadora Y", slug="locadora-y", segmento=Tenant.Segmento.LOCADORA
        )
        self.prefeitura = Tenant.objects.create(
            nome="Prefeitura Z", slug="prefeitura-z", segmento=Tenant.Segmento.FUNDO_SOCIAL
        )
        self.admin_locadora = Usuario.objects.create_user(
            username="admin_locadora",
            password=self.SENHA,
            tenant=self.locadora,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.admin_prefeitura = Usuario.objects.create_user(
            username="admin_prefeitura",
            password=self.SENHA,
            tenant=self.prefeitura,
            papel=Papel.objects.get(codigo="admin"),
        )

    def test_nav_da_locadora_mostra_clientes(self):
        self.client.login(username="admin_locadora", password=self.SENHA)
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertContains(resposta, "Clientes")
        self.assertNotContains(resposta, ">Beneficiários<")

    def test_nav_da_prefeitura_mostra_beneficiarios(self):
        self.client.login(username="admin_prefeitura", password=self.SENHA)
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertContains(resposta, "Beneficiários")

    def test_lista_da_locadora_usa_titulo_cliente(self):
        self.client.login(username="admin_locadora", password=self.SENHA)
        resposta = self.client.get(reverse("app:beneficiarios:lista"))
        self.assertContains(resposta, "Novo Cliente")

    def test_cadastro_na_locadora_pre_seleciona_tipo_cliente(self):
        self.client.login(username="admin_locadora", password=self.SENHA)
        resposta = self.client.get(reverse("app:beneficiarios:criar"))
        self.assertEqual("cliente", resposta.context["form"].fields["tipo_relacao"].initial)

    def test_cadastro_na_prefeitura_nao_forca_tipo_cliente(self):
        self.client.login(username="admin_prefeitura", password=self.SENHA)
        resposta = self.client.get(reverse("app:beneficiarios:criar"))
        self.assertNotEqual("cliente", resposta.context["form"].fields["tipo_relacao"].initial)

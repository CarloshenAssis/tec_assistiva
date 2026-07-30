"""
Módulos/feature flags por tenant (docs/business-rules/modulos.md).
"""

from django.test import TestCase
from django.urls import reverse

from contas.models import Usuario
from core import features
from core.models import Tenant


class ModuloHabilitadoPorPadraoDeSegmentoTest(TestCase):
    def test_locadora_ja_nasce_com_locacao_financeiro_ligado(self):
        tenant = Tenant.objects.create(
            nome="Locadora Padrao", slug="locadora-padrao-feat", segmento=Tenant.Segmento.LOCADORA
        )
        self.assertTrue(features.modulo_habilitado(tenant, features.LOCACAO_FINANCEIRO))
        self.assertTrue(features.modulo_habilitado(tenant, features.DOCUMENTO_PESSOA_JURIDICA))

    def test_prefeitura_nasce_sem_modulo_nenhum(self):
        tenant = Tenant.objects.create(
            nome="Prefeitura Padrao", slug="pref-padrao-feat", segmento=Tenant.Segmento.FUNDO_SOCIAL
        )
        self.assertFalse(features.modulo_habilitado(tenant, features.LOCACAO_FINANCEIRO))

    def test_tenant_none_nunca_tem_modulo(self):
        self.assertFalse(features.modulo_habilitado(None, features.LOCACAO_FINANCEIRO))

    def test_codigo_desconhecido_e_falso(self):
        tenant = Tenant.objects.create(
            nome="Locadora Desconhecido", slug="locadora-desconhecido-feat", segmento=Tenant.Segmento.LOCADORA
        )
        self.assertFalse(features.modulo_habilitado(tenant, "nao-existe"))


class DefinirModuloSobrepoeOPadraoTest(TestCase):
    def setUp(self):
        self.locadora = Tenant.objects.create(
            nome="Locadora Override", slug="locadora-override-feat", segmento=Tenant.Segmento.LOCADORA
        )
        self.prefeitura = Tenant.objects.create(
            nome="Prefeitura Override", slug="pref-override-feat", segmento=Tenant.Segmento.FUNDO_SOCIAL
        )

    def test_desliga_modulo_ligado_por_padrao(self):
        features.definir_modulo(self.locadora, features.LOCACAO_FINANCEIRO, False)
        self.assertFalse(features.modulo_habilitado(self.locadora, features.LOCACAO_FINANCEIRO))
        # O outro módulo, sem override, continua no padrão do segmento.
        self.assertTrue(features.modulo_habilitado(self.locadora, features.DOCUMENTO_PESSOA_JURIDICA))

    def test_liga_modulo_desligado_por_padrao(self):
        features.definir_modulo(self.prefeitura, features.LOCACAO_FINANCEIRO, True)
        self.assertTrue(features.modulo_habilitado(self.prefeitura, features.LOCACAO_FINANCEIRO))

    def test_override_e_isolado_por_tenant(self):
        """Ligar para um tenant não vaza para outro do mesmo segmento."""
        outra_locadora = Tenant.objects.create(
            nome="Outra Locadora", slug="outra-locadora-feat", segmento=Tenant.Segmento.LOCADORA
        )
        features.definir_modulo(self.locadora, features.LOCACAO_FINANCEIRO, False)
        self.assertTrue(features.modulo_habilitado(outra_locadora, features.LOCACAO_FINANCEIRO))

    def test_definir_de_novo_atualiza_em_vez_de_duplicar(self):
        features.definir_modulo(self.locadora, features.LOCACAO_FINANCEIRO, False)
        features.definir_modulo(self.locadora, features.LOCACAO_FINANCEIRO, True)
        self.assertTrue(features.modulo_habilitado(self.locadora, features.LOCACAO_FINANCEIRO))


class ModulosDoTenantTest(TestCase):
    def test_lista_todo_o_catalogo_com_o_estado_efetivo(self):
        tenant = Tenant.objects.create(
            nome="Locadora Catalogo", slug="locadora-catalogo-feat", segmento=Tenant.Segmento.LOCADORA
        )
        codigos_ativos = {
            item["modulo"].codigo for item in features.modulos_do_tenant(tenant) if item["ativo"]
        }
        self.assertEqual({features.LOCACAO_FINANCEIRO, features.DOCUMENTO_PESSOA_JURIDICA}, codigos_ativos)


class TelaDoOwnerAlternaModuloTest(TestCase):
    SENHA = "senha-bem-longa-2026"

    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Locadora Owner UI", slug="locadora-owner-ui-feat", segmento=Tenant.Segmento.LOCADORA
        )
        self.owner = Usuario.objects.create_user(
            username="owner_feat", password=self.SENHA, is_platform_staff=True
        )

    def test_owner_desliga_modulo_pela_tela(self):
        self.client.login(username="owner_feat", password=self.SENHA)
        resposta = self.client.post(
            reverse("owner:alternar_modulo", args=[self.tenant.pk]),
            {"modulo": features.LOCACAO_FINANCEIRO},
        )
        self.assertEqual(302, resposta.status_code)
        self.assertFalse(features.modulo_habilitado(self.tenant, features.LOCACAO_FINANCEIRO))

    def test_exige_post(self):
        self.client.login(username="owner_feat", password=self.SENHA)
        resposta = self.client.get(reverse("owner:alternar_modulo", args=[self.tenant.pk]))
        self.assertEqual(403, resposta.status_code)

    def test_admin_de_tenant_nao_acessa(self):
        from contas.models import Papel

        Usuario.objects.create_user(
            username="admin_tentativa_feat",
            password=self.SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.client.login(username="admin_tentativa_feat", password=self.SENHA)
        resposta = self.client.post(
            reverse("owner:alternar_modulo", args=[self.tenant.pk]),
            {"modulo": features.LOCACAO_FINANCEIRO},
        )
        self.assertEqual(403, resposta.status_code)

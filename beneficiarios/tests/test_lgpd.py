"""
Direitos do titular (LGPD Art. 18) e proteção dos documentos anexados.

O teste mais importante deste arquivo é o de download de documento entre
tenants: laudo e receita médica são dados sobre saúde, categoria em que um
vazamento não tem correção possível depois.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from auditoria.models import AcaoAuditada, RegistroAuditoria
from beneficiarios.lgpd import MARCADOR_ANONIMO, anonimizar, exportar_dados, revogar_consentimento
from beneficiarios.models import Beneficiario, DocumentoBeneficiario
from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class BaseLgpdTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura A", slug="pref-a-lgpd")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura B", slug="pref-b-lgpd")

        self.admin_a = Usuario.objects.create_user(
            username="admin_lgpd_a",
            password=SENHA,
            tenant=self.tenant_a,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.func_a = Usuario.objects.create_user(
            username="func_lgpd_a",
            password=SENHA,
            tenant=self.tenant_a,
            papel=Papel.objects.get(codigo="funcionario"),
        )

        self.titular_a = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_a,
            nome="Maria Silva",
            documento="123.456.789-09",
            telefone="(12) 99999-0000",
            email="maria@exemplo.br",
            bairro="Centro",
        )
        self.titular_b = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_b, nome="João Pedro", documento="234.567.891-73"
        )


class AnonimizacaoTest(BaseLgpdTest):
    def test_remove_dados_identificaveis(self):
        anonimizar(self.titular_a)
        self.titular_a.refresh_from_db()

        self.assertIn(MARCADOR_ANONIMO, self.titular_a.nome)
        self.assertNotIn("Maria", self.titular_a.nome)
        self.assertEqual("", self.titular_a.telefone)
        self.assertEqual("", self.titular_a.email)
        self.assertEqual("", self.titular_a.bairro)
        self.assertIsNotNone(self.titular_a.anonimizado_em)

    def test_cpf_nao_e_preservado(self):
        anonimizar(self.titular_a)
        self.titular_a.refresh_from_db()
        self.assertNotIn("123456789", self.titular_a.documento.replace(".", "").replace("-", ""))

    def test_apaga_documentos_com_dado_de_saude(self):
        DocumentoBeneficiario.objects.all_tenants().create(
            tenant=self.tenant_a,
            beneficiario=self.titular_a,
            tipo=DocumentoBeneficiario.Tipo.LAUDO,
            arquivo=SimpleUploadedFile("laudo.png", PNG),
        )
        anonimizar(self.titular_a)
        self.assertEqual(0, self.titular_a.documentos.count())

    def test_preserva_o_historico_patrimonial(self):
        """
        O registro de que um equipamento foi emprestado continua existindo —
        ele responde a outra finalidade (prestação de contas sobre o
        patrimônio) e o Art. 16, I autoriza a conservação.
        """
        anonimizar(self.titular_a)
        self.assertTrue(Beneficiario.objects.all_tenants().filter(pk=self.titular_a.pk).exists())

    def test_e_idempotente(self):
        anonimizar(self.titular_a)
        nome_apos_primeira = Beneficiario.objects.all_tenants().get(pk=self.titular_a.pk).nome

        self.titular_a.refresh_from_db()
        anonimizar(self.titular_a)

        self.assertEqual(
            nome_apos_primeira,
            Beneficiario.objects.all_tenants().get(pk=self.titular_a.pk).nome,
        )
        self.assertEqual(
            1, RegistroAuditoria.objects.filter(acao=AcaoAuditada.ANONIMIZACAO).count()
        )

    def test_gera_registro_de_auditoria(self):
        anonimizar(self.titular_a)
        registro = RegistroAuditoria.objects.filter(acao=AcaoAuditada.ANONIMIZACAO).first()
        self.assertIsNotNone(registro)
        self.assertTrue(registro.envolve_dado_sensivel)


class ExportacaoTest(BaseLgpdTest):
    def test_pacote_contem_os_dados_do_titular(self):
        dados = exportar_dados(self.titular_a)
        self.assertEqual("Maria Silva", dados["titular"]["nome"])
        self.assertEqual("123.456.789-09", dados["titular"]["documento"])
        self.assertIn("base_legal", dados["tratamento"])

    def test_funcionario_nao_pode_exportar(self):
        """Ver a ficha para atender é uma coisa; baixar o dossiê é outra."""
        self.client.login(username="func_lgpd_a", password=SENHA)
        resposta = self.client.get(
            reverse("app:beneficiarios:exportar", args=[self.titular_a.pk])
        )
        self.assertEqual(403, resposta.status_code)

    def test_admin_pode_exportar(self):
        self.client.login(username="admin_lgpd_a", password=SENHA)
        resposta = self.client.get(
            reverse("app:beneficiarios:exportar", args=[self.titular_a.pk])
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("attachment", resposta["Content-Disposition"])

    def test_exportacao_e_auditada(self):
        self.client.login(username="admin_lgpd_a", password=SENHA)
        self.client.get(reverse("app:beneficiarios:exportar", args=[self.titular_a.pk]))
        self.assertTrue(
            RegistroAuditoria.objects.filter(acao=AcaoAuditada.EXPORTACAO_DADOS).exists()
        )

    def test_nao_exporta_titular_de_outro_tenant(self):
        self.client.login(username="admin_lgpd_a", password=SENHA)
        resposta = self.client.get(
            reverse("app:beneficiarios:exportar", args=[self.titular_b.pk])
        )
        self.assertEqual(404, resposta.status_code)


class AnonimizacaoViaViewTest(BaseLgpdTest):
    def test_exige_post(self):
        """Operação irreversível não pode ser disparada por GET."""
        self.client.login(username="admin_lgpd_a", password=SENHA)
        resposta = self.client.get(
            reverse("app:beneficiarios:anonimizar", args=[self.titular_a.pk])
        )
        self.assertEqual(403, resposta.status_code)

    def test_funcionario_nao_pode_anonimizar(self):
        self.client.login(username="func_lgpd_a", password=SENHA)
        resposta = self.client.post(
            reverse("app:beneficiarios:anonimizar", args=[self.titular_a.pk])
        )
        self.assertEqual(403, resposta.status_code)

    def test_admin_anonimiza(self):
        self.client.login(username="admin_lgpd_a", password=SENHA)
        self.client.post(reverse("app:beneficiarios:anonimizar", args=[self.titular_a.pk]))
        self.titular_a.refresh_from_db()
        self.assertTrue(self.titular_a.esta_anonimizado)


class ConsentimentoTest(BaseLgpdTest):
    def test_revogacao_registrada(self):
        revogar_consentimento(self.titular_a)
        self.titular_a.refresh_from_db()
        self.assertIsNotNone(self.titular_a.consentimento_revogado_em)
        self.assertFalse(self.titular_a.consentimento_vigente)

    def test_base_legal_diferente_de_consentimento_nao_depende_dele(self):
        self.titular_a.base_legal = Beneficiario.BaseLegal.TUTELA_SAUDE
        self.assertTrue(self.titular_a.consentimento_vigente)


class DocumentoProtegidoTest(BaseLgpdTest):
    def setUp(self):
        super().setUp()
        self.laudo_a = DocumentoBeneficiario.objects.all_tenants().create(
            tenant=self.tenant_a,
            beneficiario=self.titular_a,
            tipo=DocumentoBeneficiario.Tipo.LAUDO,
            arquivo=SimpleUploadedFile("laudo.png", PNG),
        )
        self.laudo_b = DocumentoBeneficiario.objects.all_tenants().create(
            tenant=self.tenant_b,
            beneficiario=self.titular_b,
            tipo=DocumentoBeneficiario.Tipo.RECEITA_MEDICA,
            arquivo=SimpleUploadedFile("receita.png", PNG),
        )

    def test_exige_autenticacao(self):
        resposta = self.client.get(
            reverse("app:beneficiarios:baixar_documento", args=[self.laudo_a.pk])
        )
        self.assertIn(resposta.status_code, (302, 403))

    def test_nao_entrega_documento_de_outro_tenant(self):
        """Laudo de paciente de outra instituição não existe para esta consulta."""
        self.client.login(username="func_lgpd_a", password=SENHA)
        resposta = self.client.get(
            reverse("app:beneficiarios:baixar_documento", args=[self.laudo_b.pk])
        )
        self.assertEqual(404, resposta.status_code)

    def test_entrega_sempre_como_anexo(self):
        """
        Um SVG/HTML renderizado na origem da aplicação executaria script com a
        sessão de quem abriu. Como anexo, o navegador baixa e não renderiza.
        """
        self.client.login(username="func_lgpd_a", password=SENHA)
        resposta = self.client.get(
            reverse("app:beneficiarios:baixar_documento", args=[self.laudo_a.pk])
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("attachment", resposta["Content-Disposition"])
        self.assertEqual("application/octet-stream", resposta["Content-Type"])
        self.assertEqual("nosniff", resposta["X-Content-Type-Options"])

    def test_documento_nao_fica_em_cache(self):
        self.client.login(username="func_lgpd_a", password=SENHA)
        resposta = self.client.get(
            reverse("app:beneficiarios:baixar_documento", args=[self.laudo_a.pk])
        )
        self.assertIn("no-store", resposta["Cache-Control"])

    def test_acesso_a_laudo_e_marcado_como_dado_sensivel(self):
        self.client.login(username="func_lgpd_a", password=SENHA)
        self.client.get(reverse("app:beneficiarios:baixar_documento", args=[self.laudo_a.pk]))
        registro = RegistroAuditoria.objects.filter(
            acao=AcaoAuditada.ACESSO_DADO_PESSOAL, envolve_dado_sensivel=True
        ).first()
        self.assertIsNotNone(registro)

    def test_consulta_de_ficha_e_auditada(self):
        self.client.login(username="func_lgpd_a", password=SENHA)
        self.client.get(reverse("app:beneficiarios:ficha", args=[self.titular_a.pk]))
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.ACESSO_DADO_PESSOAL,
                objeto_id=str(self.titular_a.pk),
            ).exists()
        )

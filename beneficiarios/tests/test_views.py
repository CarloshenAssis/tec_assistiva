from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from beneficiarios.models import Beneficiario, DocumentoBeneficiario
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class BeneficiarioViewsTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura A", slug="pref-a-benef")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura B", slug="pref-b-benef")
        papel_funcionario = Papel.objects.get(codigo="funcionario")

        self.usuario_a = Usuario.objects.create_user(
            username="func_benef_a", password="senha-teste-123", tenant=self.tenant_a, papel=papel_funcionario
        )
        self.beneficiario_a = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Maria Silva", documento="123.456.789-09"
        )
        self.beneficiario_b = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_b, nome="João Pedro", documento="234.567.891-73"
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
                "tipo_documento": "cpf",
                "documento": "456.789.123-64",
                # Declarar a base legal do tratamento passou a ser obrigatório
                # no cadastro (LGPD Art. 7º/11) — ver beneficiarios/forms.py.
                "base_legal": "consentimento",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Beneficiario.objects.all_tenants().filter(tenant=self.tenant_a, documento="456.789.123-64").exists()
        )


class BaixarDocumentoEscopoPorUnidadeTest(TestCase):
    """
    `baixar_documento` era o único ponto de Beneficiário que só filtrava por
    tenant, não por unidade — um Funcionário lotado numa unidade não
    enxergava (404) a ficha de beneficiário de outra unidade, mas
    conseguia baixar o documento dele sabendo/adivinhando o id, porque o
    endpoint de download não aplicava o mesmo filtro.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Doc Unid", slug="pref-doc-unid")
        self.centro = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Centro")
        self.sul = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sul")

        self.func_centro = Usuario.objects.create_user(
            username="func_centro_doc",
            password="senha-teste-123",
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.func_centro.unidades.add(self.centro)

        self.beneficiario_sul = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Beneficiário do Sul", documento="345.678.912-06", unidade=self.sul
        )
        self.documento_sul = DocumentoBeneficiario.objects.all_tenants().create(
            tenant=self.tenant,
            beneficiario=self.beneficiario_sul,
            tipo=DocumentoBeneficiario.Tipo.LAUDO,
            arquivo=SimpleUploadedFile("laudo.png", PNG),
        )

    def test_ficha_de_beneficiario_de_outra_unidade_e_404(self):
        self.client.login(username="func_centro_doc", password="senha-teste-123")
        resposta = self.client.get(
            reverse("app:beneficiarios:ficha", args=[self.beneficiario_sul.pk])
        )
        self.assertEqual(404, resposta.status_code)

    def test_download_de_documento_de_outra_unidade_tambem_e_404(self):
        self.client.login(username="func_centro_doc", password="senha-teste-123")
        resposta = self.client.get(
            reverse("app:beneficiarios:baixar_documento", args=[self.documento_sul.pk])
        )
        self.assertEqual(404, resposta.status_code)

    def test_admin_baixa_de_qualquer_unidade(self):
        admin = Usuario.objects.create_user(
            username="admin_doc_unid",
            password="senha-teste-123",
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.client.login(username="admin_doc_unid", password="senha-teste-123")
        resposta = self.client.get(
            reverse("app:beneficiarios:baixar_documento", args=[self.documento_sul.pk])
        )
        self.assertEqual(200, resposta.status_code)


class DocumentoFlexivelPorModuloTest(TestCase):
    """
    CNPJ como tipo de documento só é oferecido a tenant com o módulo
    `documento_pessoa_juridica` habilitado (docs/business-rules/modulos.md).
    """

    def setUp(self):
        self.locadora = Tenant.objects.create(
            nome="Locadora Doc", slug="locadora-doc-benef", segmento=Tenant.Segmento.LOCADORA
        )
        self.prefeitura = Tenant.objects.create(
            nome="Prefeitura Doc", slug="pref-doc-benef", segmento=Tenant.Segmento.FUNDO_SOCIAL
        )
        papel_gestor = Papel.objects.get(codigo="gestor")
        self.gestor_locadora = Usuario.objects.create_user(
            username="gestor_locadora_doc", password="senha-teste-123", tenant=self.locadora, papel=papel_gestor
        )
        self.gestor_prefeitura = Usuario.objects.create_user(
            username="gestor_prefeitura_doc", password="senha-teste-123", tenant=self.prefeitura, papel=papel_gestor
        )

    def test_locadora_cadastra_cliente_com_cnpj(self):
        self.client.login(username="gestor_locadora_doc", password="senha-teste-123")
        resposta = self.client.post(
            reverse("app:beneficiarios:criar"),
            {
                "tipo_relacao": "cliente",
                "nome": "Transportadora XYZ",
                "tipo_documento": "cnpj",
                "documento": "11.222.333/0001-81",
                "base_legal": "execucao_contrato",
            },
        )
        self.assertEqual(302, resposta.status_code)
        self.assertTrue(
            Beneficiario.objects.all_tenants()
            .filter(tenant=self.locadora, documento="11.222.333/0001-81", tipo_documento="cnpj")
            .exists()
        )

    def test_prefeitura_nao_pode_forjar_cnpj_mesmo_no_post_direto(self):
        """
        O form nem oferece a opção CNPJ pra quem não tem o módulo — um POST
        forjado com `tipo_documento=cnpj` ainda assim vira `cpf` (única
        opção válida do campo), então o CNPJ digitado falha a validação de
        CPF em vez de ser aceito por uma porta lateral.
        """
        self.client.login(username="gestor_prefeitura_doc", password="senha-teste-123")
        resposta = self.client.post(
            reverse("app:beneficiarios:criar"),
            {
                "tipo_relacao": "beneficiario",
                "nome": "Tentativa CNPJ",
                "tipo_documento": "cnpj",
                "documento": "11.222.333/0001-81",
                "base_legal": "consentimento",
            },
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("tipo_documento", resposta.context["form"].errors)
        self.assertFalse(
            Beneficiario.objects.all_tenants().filter(tenant=self.prefeitura, nome="Tentativa CNPJ").exists()
        )

    def test_formulario_da_prefeitura_so_oferece_cpf(self):
        self.client.login(username="gestor_prefeitura_doc", password="senha-teste-123")
        resposta = self.client.get(reverse("app:beneficiarios:criar"))
        opcoes = list(resposta.context["form"].fields["tipo_documento"].choices)
        self.assertEqual([("cpf", "CPF")], opcoes)

    def test_formulario_da_locadora_oferece_cpf_e_cnpj(self):
        self.client.login(username="gestor_locadora_doc", password="senha-teste-123")
        resposta = self.client.get(reverse("app:beneficiarios:criar"))
        opcoes = {valor for valor, _ in resposta.context["form"].fields["tipo_documento"].choices}
        self.assertEqual({"cpf", "cnpj"}, opcoes)


class EditarBeneficiarioTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura Edit A", slug="pref-edit-a")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura Edit B", slug="pref-edit-b")
        self.usuario_a = Usuario.objects.create_user(
            username="func_edit_a",
            password="senha-teste-123",
            tenant=self.tenant_a,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.beneficiario_a = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Maria Silva", documento="123.456.789-09", base_legal="consentimento"
        )
        self.beneficiario_b = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_b, nome="João Pedro", documento="234.567.891-73"
        )

    def test_editar_corrige_dado_do_titular(self):
        self.client.login(username="func_edit_a", password="senha-teste-123")
        resposta = self.client.post(
            reverse("app:beneficiarios:editar", args=[self.beneficiario_a.pk]),
            {
                "tipo_relacao": "beneficiario",
                "nome": "Maria da Silva",
                "tipo_documento": "cpf",
                "documento": "123.456.789-09",
                "base_legal": "consentimento",
            },
        )
        self.assertEqual(302, resposta.status_code)
        self.beneficiario_a.refresh_from_db()
        self.assertEqual("Maria da Silva", self.beneficiario_a.nome)

    def test_editar_beneficiario_de_outro_tenant_devolve_404(self):
        self.client.login(username="func_edit_a", password="senha-teste-123")
        resposta = self.client.get(reverse("app:beneficiarios:editar", args=[self.beneficiario_b.pk]))
        self.assertEqual(404, resposta.status_code)

    def test_editar_exige_login(self):
        resposta = self.client.get(reverse("app:beneficiarios:editar", args=[self.beneficiario_a.pk]))
        self.assertEqual(302, resposta.status_code)


class DocumentoNovoTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura Doc Novo A", slug="pref-doc-novo-a")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura Doc Novo B", slug="pref-doc-novo-b")
        self.usuario_a = Usuario.objects.create_user(
            username="func_doc_novo_a",
            password="senha-teste-123",
            tenant=self.tenant_a,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.beneficiario_a = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Maria Silva", documento="123.456.789-09"
        )
        self.beneficiario_b = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_b, nome="João Pedro", documento="234.567.891-73"
        )

    def test_anexa_documento_ao_titular(self):
        self.client.login(username="func_doc_novo_a", password="senha-teste-123")
        resposta = self.client.post(
            reverse("app:beneficiarios:documento_novo", args=[self.beneficiario_a.pk]),
            {"tipo": "rg", "arquivo": SimpleUploadedFile("rg.png", PNG)},
        )
        self.assertEqual(302, resposta.status_code)
        self.assertTrue(
            DocumentoBeneficiario.objects.all_tenants()
            .filter(beneficiario=self.beneficiario_a, tipo="rg")
            .exists()
        )

    def test_nao_anexa_documento_a_titular_de_outro_tenant(self):
        self.client.login(username="func_doc_novo_a", password="senha-teste-123")
        resposta = self.client.post(
            reverse("app:beneficiarios:documento_novo", args=[self.beneficiario_b.pk]),
            {"tipo": "rg", "arquivo": SimpleUploadedFile("rg.png", PNG)},
        )
        self.assertEqual(404, resposta.status_code)

    def test_upload_exige_post(self):
        self.client.login(username="func_doc_novo_a", password="senha-teste-123")
        resposta = self.client.get(
            reverse("app:beneficiarios:documento_novo", args=[self.beneficiario_a.pk])
        )
        self.assertEqual(403, resposta.status_code)

"""
Exportação da trilha de auditoria em CSV — mesmo filtro da tela, sem paginar
(docs/business-rules/auditoria.md).
"""

from django.test import TestCase
from django.urls import reverse

from auditoria.models import AcaoAuditada, RegistroAuditoria
from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"


class ExportarAuditoriaTenantTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Export Audit", slug="pref-export-audit")
        self.outro_tenant = Tenant.objects.create(nome="Outra Prefeitura", slug="outra-pref-export-audit")

        self.admin = Usuario.objects.create_user(
            username="admin_export_audit", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="admin")
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_export_audit",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

        RegistroAuditoria.objects.create(
            tenant=self.tenant,
            usuario=self.admin,
            usuario_identificacao="admin_export_audit",
            acao=AcaoAuditada.LOGIN_SUCESSO,
        )
        RegistroAuditoria.objects.create(
            tenant=self.tenant,
            usuario=self.admin,
            usuario_identificacao="admin_export_audit",
            acao=AcaoAuditada.EXPORTACAO_DADOS,
            envolve_dado_sensivel=True,
            descricao="Exportação de dados a pedido do titular",
        )
        # De outro tenant — não pode vazar para o CSV do primeiro.
        RegistroAuditoria.objects.create(
            tenant=self.outro_tenant,
            usuario_identificacao="alguem_de_outro_tenant",
            acao=AcaoAuditada.LOGIN_SUCESSO,
        )

    def test_exige_gestor_ou_admin(self):
        self.client.login(username="func_export_audit", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:auditoria_exportar"))
        self.assertEqual(403, resposta.status_code)

    def test_admin_baixa_csv_com_cabecalho_e_sem_coluna_de_organizacao(self):
        self.client.login(username="admin_export_audit", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:auditoria_exportar"))
        self.assertEqual(200, resposta.status_code)
        self.assertEqual("text/csv; charset=utf-8", resposta["Content-Type"])
        conteudo = resposta.content.decode("utf-8-sig")
        cabecalho = conteudo.splitlines()[0]
        self.assertEqual("Quando;Usuário;Ação;Objeto;Sensível;Descrição;IP", cabecalho)

    def test_bom_aparece_uma_unica_vez_no_arquivo(self):
        # Regressão: `_resposta_csv` chegou a inserir um BOM extra a cada
        # linha (ver core/relatorios_export.py) — com 2+ linhas de dados,
        # isso teria aparecido no meio do arquivo, não só no início.
        self.client.login(username="admin_export_audit", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:auditoria_exportar"))
        self.assertEqual(1, resposta.content.count(b"\xef\xbb\xbf"))
        self.assertTrue(resposta.content.startswith(b"\xef\xbb\xbf"))

    def test_nao_inclui_registro_de_outro_tenant(self):
        self.client.login(username="admin_export_audit", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:auditoria_exportar"))
        conteudo = resposta.content.decode("utf-8-sig")
        self.assertNotIn("alguem_de_outro_tenant", conteudo)
        self.assertIn("admin_export_audit", conteudo)

    def test_filtro_de_acao_e_aplicado_no_export(self):
        self.client.login(username="admin_export_audit", password=SENHA)
        resposta = self.client.get(
            reverse("app:usuarios:auditoria_exportar"), {"acao": AcaoAuditada.EXPORTACAO_DADOS}
        )
        conteudo = resposta.content.decode("utf-8-sig")
        linhas = [l for l in conteudo.splitlines()[1:] if l.strip()]
        self.assertEqual(1, len(linhas))
        self.assertIn("Dados do titular exportados", linhas[0])


class ExportarAuditoriaOwnerTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Owner Export", slug="pref-owner-export")
        self.owner = Usuario.objects.create_user(
            username="owner_export_audit", password=SENHA, is_platform_staff=True, is_superuser=True
        )
        self.admin = Usuario.objects.create_user(
            username="admin_owner_export", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="admin")
        )
        RegistroAuditoria.objects.create(
            tenant=self.tenant, usuario_identificacao="admin_owner_export", acao=AcaoAuditada.LOGIN_SUCESSO
        )

    def test_exige_owner(self):
        self.client.login(username="admin_owner_export", password=SENHA)
        resposta = self.client.get(reverse("owner:auditoria_exportar"))
        self.assertEqual(403, resposta.status_code)

    def test_owner_baixa_csv_com_coluna_de_organizacao(self):
        self.client.login(username="owner_export_audit", password=SENHA)
        resposta = self.client.get(reverse("owner:auditoria_exportar"))
        self.assertEqual(200, resposta.status_code)
        conteudo = resposta.content.decode("utf-8-sig")
        cabecalho = conteudo.splitlines()[0]
        self.assertEqual("Quando;Organização;Usuário;Ação;Objeto;Sensível;Descrição;IP", cabecalho)
        self.assertIn("Prefeitura Owner Export", conteudo)

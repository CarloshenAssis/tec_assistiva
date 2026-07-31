"""
Limite de taxa em exportar/anonimizar (auditoria/limitador.py) — bem mais
apertado que o de movimentação de ativo: são operações raras e, no caso da
anonimização, irreversíveis.
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from auditoria.models import AcaoAuditada, RegistroAuditoria
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"


class LimiteExportacaoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Limite Exp", slug="pref-limite-exp")
        self.admin = Usuario.objects.create_user(
            username="admin_limite_exp", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="admin")
        )
        self.beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Maria Silva", documento="123.456.789-09"
        )
        self.client.login(username="admin_limite_exp", password=SENHA)

    @patch("beneficiarios.views._LIMITE_EXPORTACOES", 3)
    @patch("beneficiarios.views._LIMITE_EXPORTACOES_JANELA_MINUTOS", 60)
    def test_bloqueia_apos_o_limite(self):
        url = reverse("app:beneficiarios:exportar", args=[self.beneficiario.pk])
        for _ in range(3):
            resposta = self.client.get(url)
            self.assertEqual(200, resposta.status_code)
            self.assertEqual("application/json; charset=utf-8", resposta["Content-Type"])

        resposta = self.client.get(url, follow=True)
        self.assertEqual(200, resposta.status_code)
        # A 4ª não deve gerar um novo EXPORTACAO_DADOS — foi recusada antes.
        self.assertEqual(
            3,
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.EXPORTACAO_DADOS, objeto_id=str(self.beneficiario.pk)
            ).count(),
        )
        mensagens = [str(m) for m in resposta.context["messages"]]
        self.assertTrue(any("Muitas exportações" in m for m in mensagens))

    def test_uso_normal_abaixo_do_limite_nao_e_afetado(self):
        url = reverse("app:beneficiarios:exportar", args=[self.beneficiario.pk])
        for _ in range(3):
            resposta = self.client.get(url)
            self.assertEqual(200, resposta.status_code)


class LimiteAnonimizacaoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Limite Anon", slug="pref-limite-anon")
        self.admin = Usuario.objects.create_user(
            username="admin_limite_anon",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.beneficiarios = [
            Beneficiario.objects.all_tenants().create(
                tenant=self.tenant, nome=f"Titular {i}", documento=f"111.111.111-0{i}"
            )
            for i in range(4)
        ]
        self.client.login(username="admin_limite_anon", password=SENHA)

    @patch("beneficiarios.views._LIMITE_ANONIMIZACOES", 2)
    @patch("beneficiarios.views._LIMITE_ANONIMIZACOES_JANELA_MINUTOS", 60)
    def test_bloqueia_apos_o_limite_e_nao_anonimiza(self):
        for beneficiario in self.beneficiarios[:2]:
            resposta = self.client.post(
                reverse("app:beneficiarios:anonimizar", args=[beneficiario.pk])
            )
            self.assertEqual(302, resposta.status_code)

        terceiro = self.beneficiarios[2]
        resposta = self.client.post(
            reverse("app:beneficiarios:anonimizar", args=[terceiro.pk]), follow=True
        )
        terceiro.refresh_from_db()
        self.assertIsNone(terceiro.anonimizado_em, "deveria ter sido recusado pelo limite, sem anonimizar")
        mensagens = [str(m) for m in resposta.context["messages"]]
        self.assertTrue(any("Muitas anonimizações" in m for m in mensagens))

        for beneficiario in self.beneficiarios[:2]:
            beneficiario.refresh_from_db()
            self.assertIsNotNone(beneficiario.anonimizado_em)

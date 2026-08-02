"""
`notificacoes:lista` era a única tela de listagem sem escopo de unidade —
todo usuário do tenant via o histórico completo, mesmo lotado numa única
unidade. `campo="beneficiario__unidade"` porque quem tem unidade é o
beneficiário, não a notificação em si.
"""

from django.test import TestCase
from django.urls import reverse

from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade
from notificacoes.models import NotificacaoEnviada, NotificacaoTemplate

SENHA = "senha-bem-longa-2026"


class NotificacoesEscopoPorUnidadeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Notif Unid", slug="pref-notif-unid")
        self.centro = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Centro")
        self.sul = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sul")

        self.func_centro = Usuario.objects.create_user(
            username="func_centro_notif",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.func_centro.unidades.add(self.centro)

        self.admin = Usuario.objects.create_user(
            username="admin_notif_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )

        self.template = NotificacaoTemplate.objects.all_tenants().create(
            tenant=self.tenant,
            tipo=NotificacaoTemplate.Tipo.CONFIRMACAO_EMPRESTIMO,
            titulo="Empréstimo realizado",
            corpo_texto="Olá {beneficiario}.",
        )
        self.beneficiario_centro = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Beneficiário do Centro", documento="111.111.111-11", unidade=self.centro
        )
        self.beneficiario_sul = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Beneficiário do Sul", documento="222.222.222-22", unidade=self.sul
        )
        self.beneficiario_sem_unidade = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Beneficiário Sem Unidade", documento="333.333.333-33"
        )

        for beneficiario in (self.beneficiario_centro, self.beneficiario_sul, self.beneficiario_sem_unidade):
            NotificacaoEnviada.objects.all_tenants().create(
                tenant=self.tenant,
                beneficiario=beneficiario,
                template=self.template,
                canal=NotificacaoEnviada.Canal.WHATSAPP,
                destinatario="5512999990000",
                corpo_renderizado="Olá.",
                status=NotificacaoEnviada.Status.ENVIADO,
            )

    def test_funcionario_ve_so_a_propria_unidade_e_sem_unidade(self):
        self.client.login(username="func_centro_notif", password=SENHA)
        resposta = self.client.get(reverse("app:notificacoes:lista"))
        conteudo = resposta.content.decode()
        self.assertIn("Beneficiário do Centro", conteudo)
        self.assertIn("Beneficiário Sem Unidade", conteudo)
        self.assertNotIn("Beneficiário do Sul", conteudo)

    def test_admin_ve_todas_as_unidades(self):
        self.client.login(username="admin_notif_unid", password=SENHA)
        resposta = self.client.get(reverse("app:notificacoes:lista"))
        conteudo = resposta.content.decode()
        self.assertIn("Beneficiário do Centro", conteudo)
        self.assertIn("Beneficiário do Sul", conteudo)
        self.assertIn("Beneficiário Sem Unidade", conteudo)

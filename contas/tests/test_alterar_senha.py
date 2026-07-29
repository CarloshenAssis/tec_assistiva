"""
Troca de senha por usuário já autenticado (rota /accounts/senha/alterar/).

Diferente da recuperação por e-mail, esta rota exige a senha atual — é o
caminho para quem quer trocar por rotina, não para quem esqueceu.
"""

from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.urls import reverse

from auditoria.models import AcaoAuditada, RegistroAuditoria
from contas.models import Papel, Usuario
from core.models import Tenant

SENHA_ATUAL = "senha-bem-longa-2026"
SENHA_NOVA = "outra-senha-bem-longa-2027"


class AlterarSenhaTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura W", slug="pref-troca-senha")
        self.usuario = Usuario.objects.create_user(
            username="func_troca",
            password=SENHA_ATUAL,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_exige_autenticacao(self):
        resposta = self.client.get(reverse("password_change"))
        self.assertEqual(302, resposta.status_code)  # redireciona para login

    def test_troca_com_sucesso(self):
        self.client.login(username="func_troca", password=SENHA_ATUAL)
        resposta = self.client.post(
            reverse("password_change"),
            {
                "old_password": SENHA_ATUAL,
                "new_password1": SENHA_NOVA,
                "new_password2": SENHA_NOVA,
            },
        )
        self.assertRedirects(resposta, reverse("password_change_done"))
        self.usuario.refresh_from_db()
        self.assertTrue(check_password(SENHA_NOVA, self.usuario.password))

    def test_exige_senha_atual_correta(self):
        """A diferença central em relação ao reset por e-mail."""
        self.client.login(username="func_troca", password=SENHA_ATUAL)
        resposta = self.client.post(
            reverse("password_change"),
            {
                "old_password": "senha-errada",
                "new_password1": SENHA_NOVA,
                "new_password2": SENHA_NOVA,
            },
        )
        self.assertEqual(200, resposta.status_code)  # reexibe com erro
        self.usuario.refresh_from_db()
        self.assertTrue(check_password(SENHA_ATUAL, self.usuario.password))

    def test_nao_permite_senha_curta(self):
        self.client.login(username="func_troca", password=SENHA_ATUAL)
        self.client.post(
            reverse("password_change"),
            {
                "old_password": SENHA_ATUAL,
                "new_password1": "curta",
                "new_password2": "curta",
            },
        )
        self.usuario.refresh_from_db()
        self.assertTrue(check_password(SENHA_ATUAL, self.usuario.password))

    def test_gera_registro_de_auditoria(self):
        self.client.login(username="func_troca", password=SENHA_ATUAL)
        self.client.post(
            reverse("password_change"),
            {
                "old_password": SENHA_ATUAL,
                "new_password1": SENHA_NOVA,
                "new_password2": SENHA_NOVA,
            },
        )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.SENHA_ALTERADA, usuario=self.usuario
            ).exists()
        )

    def test_nao_grava_senha_em_texto_claro_na_auditoria(self):
        self.client.login(username="func_troca", password=SENHA_ATUAL)
        self.client.post(
            reverse("password_change"),
            {
                "old_password": SENHA_ATUAL,
                "new_password1": SENHA_NOVA,
                "new_password2": SENHA_NOVA,
            },
        )
        for registro in RegistroAuditoria.objects.all():
            self.assertNotIn(SENHA_NOVA, f"{registro.descricao}")

    def test_sessao_continua_valida_apos_troca(self):
        """
        O Django atualiza o hash de sessão após troca de senha; sem isso o
        usuário seria deslogado no meio do próprio fluxo de troca.
        """
        self.client.login(username="func_troca", password=SENHA_ATUAL)
        self.client.post(
            reverse("password_change"),
            {
                "old_password": SENHA_ATUAL,
                "new_password1": SENHA_NOVA,
                "new_password2": SENHA_NOVA,
            },
        )
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertEqual(200, resposta.status_code)

    def test_link_visivel_para_usuario_autenticado(self):
        self.client.login(username="func_troca", password=SENHA_ATUAL)
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertContains(resposta, reverse("password_change"))

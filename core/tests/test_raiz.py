"""
Redirecionamento inicial (`/` e destino pós-login) por tipo de usuário.

Existe porque um redirect fixo para `app:dashboard` quebra para o Owner —
descoberto ao testar o login da primeira conta de plataforma em produção:
o Owner era redirecionado para uma área que só usuário de tenant acessa, e
recebia 403 no primeiro clique depois de logar.
"""

from django.test import TestCase
from django.urls import reverse

from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"


class RedirecionamentoPorTipoDeUsuarioTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Raiz", slug="pref-raiz")
        self.usuario_tenant = Usuario.objects.create_user(
            username="func_raiz",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.owner = Usuario.objects.create_user(
            username="owner_raiz", password=SENHA, is_platform_staff=True
        )

    def test_anonimo_vai_para_login(self):
        resposta = self.client.get(reverse("raiz"))
        self.assertRedirects(resposta, reverse("login"))

    def test_usuario_de_tenant_vai_para_dashboard_do_tenant(self):
        self.client.login(username="func_raiz", password=SENHA)
        resposta = self.client.get(reverse("raiz"))
        self.assertRedirects(resposta, reverse("app:dashboard"))

    def test_owner_vai_para_dashboard_do_owner(self):
        self.client.login(username="owner_raiz", password=SENHA)
        resposta = self.client.get(reverse("raiz"))
        self.assertRedirects(resposta, reverse("owner:dashboard"))

    def test_login_de_owner_nao_aterrissa_em_pagina_que_da_403(self):
        """
        O caso concreto que quebrou em produção: login bem-sucedido seguido
        da cadeia de redirects (login -> raiz -> dashboard do Owner) não
        pode terminar numa página que nega acesso.
        """
        resposta = self.client.post(
            reverse("login"), {"username": "owner_raiz", "password": SENHA}, follow=True
        )
        self.assertEqual(200, resposta.status_code)

    def test_login_de_usuario_de_tenant_nao_aterrissa_em_pagina_que_da_403(self):
        resposta = self.client.post(
            reverse("login"), {"username": "func_raiz", "password": SENHA}, follow=True
        )
        self.assertEqual(200, resposta.status_code)


class PaginasCompartilhadasRenderizamParaAmbosOsPerfisTest(TestCase):
    """
    `password_change`/`password_change_done` são a mesma view para tenant e
    Owner — precisam renderizar conteúdo em ambos os shells, não só um.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Senha", slug="pref-senha-raiz")
        self.usuario_tenant = Usuario.objects.create_user(
            username="func_senha_raiz",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.owner = Usuario.objects.create_user(
            username="owner_senha_raiz", password=SENHA, is_platform_staff=True
        )

    def test_owner_ve_conteudo_da_tela_de_alterar_senha(self):
        self.client.login(username="owner_senha_raiz", password=SENHA)
        resposta = self.client.get(reverse("password_change"))
        self.assertContains(resposta, "Senha atual")

    def test_owner_ve_conteudo_da_tela_de_senha_alterada(self):
        self.client.login(username="owner_senha_raiz", password=SENHA)
        self.client.post(
            reverse("password_change"),
            {
                "old_password": SENHA,
                "new_password1": "nova-senha-bem-longa-2027",
                "new_password2": "nova-senha-bem-longa-2027",
            },
        )
        resposta = self.client.get(reverse("password_change_done"))
        self.assertContains(resposta, "Senha alterada com sucesso")

    def test_tenant_continua_vendo_conteudo_da_tela_de_alterar_senha(self):
        self.client.login(username="func_senha_raiz", password=SENHA)
        resposta = self.client.get(reverse("password_change"))
        self.assertContains(resposta, "Senha atual")

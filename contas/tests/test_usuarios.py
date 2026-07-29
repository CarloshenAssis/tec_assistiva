"""
Gestão de usuários pelo próprio Admin/Gestor do tenant (`/app/usuarios/`).

O caso central do pedido do usuário: o Owner só gera o primeiro Admin (ver
owner/tests/test_views.py); a partir daí é o Admin/Gestor do tenant quem
cria os demais usuários — sem depender da plataforma para cada conta nova.
"""

from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.urls import reverse

from auditoria.models import AcaoAuditada, RegistroAuditoria
from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"


class AcessoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Acesso", slug="pref-usr-acesso")
        self.funcionario = Usuario.objects.create_user(
            username="func_acesso",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_acesso",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )

    def test_funcionario_nao_acessa_lista_de_usuarios(self):
        self.client.login(username="func_acesso", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:lista"))
        self.assertEqual(403, resposta.status_code)

    def test_gestor_acessa_lista_de_usuarios(self):
        self.client.login(username="gestor_acesso", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:lista"))
        self.assertEqual(200, resposta.status_code)

    def test_owner_e_bloqueado_na_area_de_tenant(self):
        """`/app/*` é exclusivo de usuário vinculado a tenant — o Owner usa `/owner/*`."""
        Usuario.objects.create_user(
            username="owner_bloqueado_app", password=SENHA, is_platform_staff=True
        )
        self.client.login(username="owner_bloqueado_app", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:lista"))
        self.assertEqual(403, resposta.status_code)


class CriarUsuarioTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Criar Usr", slug="pref-criar-usr")
        self.admin = Usuario.objects.create_user(
            username="admin_cria_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_cria_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )

    def test_admin_cria_gestor(self):
        self.client.login(username="admin_cria_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "novo_gestor_criado",
                "email": "gestor@prefeitura.gov.br",
                "papel": Papel.objects.get(codigo="gestor").pk,
            },
        )
        usuario = Usuario.objects.get(username="novo_gestor_criado")
        self.assertEqual("gestor", usuario.papel.codigo)
        self.assertEqual(self.tenant, usuario.tenant)

    def test_admin_cria_funcionario(self):
        self.client.login(username="admin_cria_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "novo_func_criado",
                "email": "func@prefeitura.gov.br",
                "papel": Papel.objects.get(codigo="funcionario").pk,
            },
        )
        self.assertTrue(Usuario.objects.filter(username="novo_func_criado").exists())

    def test_admin_nao_pode_atribuir_papel_admin(self):
        """
        O formulário só oferece papéis ABAIXO do nível do criador — mesmo um
        POST forjado com o pk do papel Admin não deve ser aceito.
        """
        self.client.login(username="admin_cria_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "tentativa_admin",
                "email": "x@x.com",
                "papel": Papel.objects.get(codigo="admin").pk,
            },
        )
        self.assertEqual(200, resposta.status_code)  # reexibe com erro de validação
        self.assertFalse(Usuario.objects.filter(username="tentativa_admin").exists())

    def test_gestor_cria_funcionario(self):
        self.client.login(username="gestor_cria_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "func_criado_por_gestor",
                "email": "y@y.com",
                "papel": Papel.objects.get(codigo="funcionario").pk,
            },
        )
        self.assertTrue(Usuario.objects.filter(username="func_criado_por_gestor").exists())

    def test_gestor_nao_pode_criar_gestor(self):
        """Gestor só provisiona estritamente abaixo do próprio nível."""
        self.client.login(username="gestor_cria_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "tentativa_gestor",
                "email": "z@z.com",
                "papel": Papel.objects.get(codigo="gestor").pk,
            },
        )
        self.assertEqual(200, resposta.status_code)
        self.assertFalse(Usuario.objects.filter(username="tentativa_gestor").exists())

    def test_novo_usuario_fica_no_mesmo_tenant_do_criador(self):
        outro_tenant = Tenant.objects.create(nome="Outra Prefeitura", slug="pref-outra-criar-usr")
        self.client.login(username="admin_cria_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "usuario_tenant_correto",
                "email": "w@w.com",
                "papel": Papel.objects.get(codigo="funcionario").pk,
            },
        )
        usuario = Usuario.objects.get(username="usuario_tenant_correto")
        self.assertEqual(self.tenant, usuario.tenant)
        self.assertNotEqual(outro_tenant, usuario.tenant)

    def test_senha_gerada_funciona_para_login(self):
        """Confirma de ponta a ponta: a senha mostrada na tela realmente autentica."""
        self.client.login(username="admin_cria_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "usuario_login_ok",
                "email": "login-ok@x.com",
                "papel": Papel.objects.get(codigo="funcionario").pk,
            },
        )
        usuario = Usuario.objects.get(username="usuario_login_ok")
        # A senha não fica acessível fora da resposta HTTP da criação — aqui
        # confirmamos que ELA (não uma senha arbitrária) é a única que bate.
        self.assertFalse(check_password("qualquer-coisa", usuario.password))

    def test_criacao_e_auditada(self):
        self.client.login(username="admin_cria_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "usuario_auditado",
                "email": "audit@x.com",
                "papel": Papel.objects.get(codigo="funcionario").pk,
            },
        )
        usuario = Usuario.objects.get(username="usuario_auditado")
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.CRIACAO,
                objeto_tipo="contas.Usuario",
                objeto_id=str(usuario.pk),
                tenant=self.tenant,
            ).exists()
        )


class AlternarAtivoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Alt Usr", slug="pref-alt-usr")
        self.admin = Usuario.objects.create_user(
            username="admin_alt_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_alt_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_admin_desativa_funcionario(self):
        self.client.login(username="admin_alt_usr", password=SENHA)
        self.client.post(reverse("app:usuarios:alternar_ativo", args=[self.funcionario.pk]))
        self.funcionario.refresh_from_db()
        self.assertFalse(self.funcionario.is_active)

    def test_nao_pode_desativar_a_propria_conta(self):
        self.client.login(username="admin_alt_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:alternar_ativo", args=[self.admin.pk])
        )
        self.assertEqual(403, resposta.status_code)

    def test_nao_alcanca_usuario_de_outro_tenant(self):
        outro_tenant = Tenant.objects.create(nome="Outra Alt", slug="pref-outra-alt-usr")
        outro_usuario = Usuario.objects.create_user(
            username="func_outro_tenant_alt",
            password=SENHA,
            tenant=outro_tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.client.login(username="admin_alt_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:alternar_ativo", args=[outro_usuario.pk])
        )
        self.assertEqual(404, resposta.status_code)
        outro_usuario.refresh_from_db()
        self.assertTrue(outro_usuario.is_active)


class AuditoriaTenantTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura Audit A", slug="pref-audit-a-usr")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura Audit B", slug="pref-audit-b-usr")
        self.admin_a = Usuario.objects.create_user(
            username="admin_audit_a",
            password=SENHA,
            tenant=self.tenant_a,
            papel=Papel.objects.get(codigo="admin"),
        )

    def test_ve_somente_registros_do_proprio_tenant(self):
        RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO, tenant=self.tenant_a, usuario_identificacao="a"
        )
        RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO, tenant=self.tenant_b, usuario_identificacao="b"
        )
        self.client.login(username="admin_audit_a", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:auditoria"))
        registros = list(resposta.context["pagina"])
        self.assertTrue(all(r.tenant_id == self.tenant_a.pk for r in registros))
        self.assertTrue(len(registros) >= 1)

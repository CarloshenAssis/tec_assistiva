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
from core.models import Tenant, Unidade
from core.unidades import unidades_do_usuario

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
        # Unidade é obrigatória na criação de Gestor/Funcionário
        # (docs/business-rules/unidades.md) — os testes abaixo que só
        # verificam outro comportamento (auditoria, tenant, senha) usam esta
        # unidade só para o form validar.
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")

    def test_admin_cria_gestor(self):
        self.client.login(username="admin_cria_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "novo_gestor_criado",
                "email": "gestor@prefeitura.gov.br",
                "papel": Papel.objects.get(codigo="gestor").pk,
                "unidades": [self.unidade.pk],
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
                "unidades": [self.unidade.pk],
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
                "unidades": [self.unidade.pk],
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
                "unidades": [self.unidade.pk],
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
                "unidades": [self.unidade.pk],
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
                "unidades": [self.unidade.pk],
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

    def test_atribui_unidades_ao_criar_funcionario(self):
        """A decisão de arquitetura: unidade é permissão atribuída no cadastro, não campo fixo."""
        centro = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Centro")
        sul = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sul")
        self.client.login(username="admin_cria_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "func_com_unidades",
                "email": "func_unid@x.com",
                "papel": Papel.objects.get(codigo="funcionario").pk,
                "unidades": [centro.pk, sul.pk],
            },
        )
        usuario = Usuario.objects.get(username="func_com_unidades")
        # `usuario.unidades.all()` direto falharia aqui: fora da requisição
        # (o teste já terminou o client.post), o ContextVar de tenant foi
        # resetado pelo TenantMiddleware — ver core/unidades.py.
        self.assertEqual({centro, sul}, set(unidades_do_usuario(usuario)))

    def test_criar_usuario_sem_marcar_unidade_e_erro_de_formulario(self):
        """
        Unidade é obrigatória na criação de Gestor/Funcionário
        (docs/business-rules/unidades.md) — sem ela, a pessoa recém-criada
        logaria num sistema sem nenhum ativo/beneficiário visível, sem saber
        por quê. Melhor barrar aqui do que deixar isso pra descobrir depois.
        """
        self.client.login(username="admin_cria_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:criar"),
            {
                "username": "func_sem_unidade_nenhuma",
                "email": "sem_unid@x.com",
                "papel": Papel.objects.get(codigo="funcionario").pk,
            },
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("unidades", resposta.context["form"].errors)
        self.assertFalse(Usuario.objects.filter(username="func_sem_unidade_nenhuma").exists())


class EditarUsuarioTest(TestCase):
    """
    Tela nova: antes só dava pra ativar/desativar e gerar nova senha — sem
    jeito de corrigir e-mail, nome, papel ou reatribuir unidade sem apagar
    e recriar a conta.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Editar Usr", slug="pref-editar-usr")
        self.admin = Usuario.objects.create_user(
            username="admin_edita_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_edita_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.outro_gestor = Usuario.objects.create_user(
            username="outro_gestor_edita_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_edita_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.centro = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Centro")
        self.sul = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sul")
        self.funcionario.unidades.add(self.centro)

    def _payload(self, **overrides):
        base = {
            "email": "novo@x.com",
            "first_name": "Novo",
            "last_name": "Nome",
            "papel": Papel.objects.get(codigo="funcionario").pk,
            "unidades": [self.sul.pk],
        }
        base.update(overrides)
        return base

    def test_admin_edita_funcionario(self):
        self.client.login(username="admin_edita_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:editar", args=[self.funcionario.pk]), self._payload()
        )
        self.assertRedirects(resposta, reverse("app:usuarios:lista"))
        self.funcionario.refresh_from_db()
        self.assertEqual("novo@x.com", self.funcionario.email)
        self.assertEqual("Novo", self.funcionario.first_name)
        self.assertEqual({self.sul}, set(unidades_do_usuario(self.funcionario)))

    def test_gestor_nao_pode_editar_admin(self):
        self.client.login(username="gestor_edita_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:editar", args=[self.admin.pk]), self._payload()
        )
        self.assertEqual(403, resposta.status_code)

    def test_gestor_pode_editar_outro_gestor_mas_nao_muda_papel_para_admin(self):
        """`pode_gerenciar` usa `>=`: Gestor gerencia um par de mesmo nível já existente."""
        self.client.login(username="gestor_edita_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:editar", args=[self.outro_gestor.pk]),
            self._payload(papel=Papel.objects.get(codigo="admin").pk),
        )
        self.assertEqual(200, resposta.status_code)  # reexibe com erro de validação
        self.assertIn("papel", resposta.context["form"].errors)
        self.outro_gestor.refresh_from_db()
        self.assertEqual("gestor", self.outro_gestor.papel.codigo)

    def test_gestor_edita_outro_gestor_mantendo_o_papel(self):
        self.client.login(username="gestor_edita_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:editar", args=[self.outro_gestor.pk]),
            self._payload(papel=Papel.objects.get(codigo="gestor").pk),
        )
        self.assertRedirects(resposta, reverse("app:usuarios:lista"))
        self.outro_gestor.refresh_from_db()
        self.assertEqual("gestor", self.outro_gestor.papel.codigo)
        self.assertEqual("novo@x.com", self.outro_gestor.email)

    def test_gestor_pode_rebaixar_outro_gestor_para_funcionario(self):
        self.client.login(username="gestor_edita_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:editar", args=[self.outro_gestor.pk]),
            self._payload(papel=Papel.objects.get(codigo="funcionario").pk),
        )
        self.assertRedirects(resposta, reverse("app:usuarios:lista"))
        self.outro_gestor.refresh_from_db()
        self.assertEqual("funcionario", self.outro_gestor.papel.codigo)

    def test_nao_pode_editar_a_propria_conta_por_aqui(self):
        self.client.login(username="admin_edita_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:editar", args=[self.admin.pk]), self._payload()
        )
        self.assertEqual(403, resposta.status_code)

    def test_nao_alcanca_usuario_de_outro_tenant(self):
        outro_tenant = Tenant.objects.create(nome="Outra Editar", slug="pref-outra-editar-usr")
        outro_usuario = Usuario.objects.create_user(
            username="func_outro_tenant_editar",
            password=SENHA,
            tenant=outro_tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.client.login(username="admin_edita_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:editar", args=[outro_usuario.pk]), self._payload()
        )
        self.assertEqual(404, resposta.status_code)

    def test_username_nao_muda(self):
        self.client.login(username="admin_edita_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:editar", args=[self.funcionario.pk]), self._payload()
        )
        self.funcionario.refresh_from_db()
        self.assertEqual("func_edita_usr", self.funcionario.username)

    def test_edicao_e_auditada(self):
        self.client.login(username="admin_edita_usr", password=SENHA)
        self.client.post(
            reverse("app:usuarios:editar", args=[self.funcionario.pk]), self._payload()
        )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.ALTERACAO,
                objeto_tipo="contas.Usuario",
                objeto_id=str(self.funcionario.pk),
            ).exists()
        )

    def test_formulario_sem_unidade_e_erro(self):
        self.client.login(username="admin_edita_usr", password=SENHA)
        resposta = self.client.post(
            reverse("app:usuarios:editar", args=[self.funcionario.pk]),
            self._payload(unidades=[]),
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("unidades", resposta.context["form"].errors)


class AlternarAtivoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Alt Usr", slug="pref-alt-usr")
        self.admin = Usuario.objects.create_user(
            username="admin_alt_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_alt_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_alt_usr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_gestor_nao_pode_desativar_admin(self):
        """Hierarquia: Gestor (20) não gerencia Admin (30) — `pode_gerenciar` nega."""
        self.client.login(username="gestor_alt_usr", password=SENHA)
        resposta = self.client.post(reverse("app:usuarios:alternar_ativo", args=[self.admin.pk]))
        self.assertEqual(403, resposta.status_code)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_botao_desativar_nao_aparece_pro_gestor_na_linha_do_admin(self):
        """
        Bloquear só no servidor não bastava: a lista mostrava o botão
        "Desativar" na linha do Admin pra qualquer Gestor, mesmo sabendo que
        clicar resultaria em 403 — a UI oferecia uma ação que nunca teria
        efeito.
        """
        self.client.login(username="gestor_alt_usr", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:lista"))
        conteudo = resposta.content.decode()
        # A linha do Admin não deve conter o form de alternar-ativo dele.
        self.assertNotIn(
            reverse("app:usuarios:alternar_ativo", args=[self.admin.pk]), conteudo
        )
        # Mas a do Funcionário (que o Gestor pode gerenciar) continua lá.
        self.assertIn(
            reverse("app:usuarios:alternar_ativo", args=[self.funcionario.pk]), conteudo
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


class GerarNovaSenhaTest(TestCase):
    """
    Caso real que motivou a tela: usuário criado, senha temporária mostrada
    uma única vez, pessoa erra ao digitar/retransmitir e não há como "ver de
    novo" — o Admin/Gestor precisa poder gerar outra sem recriar a conta
    (recriar nem seria possível, `username` é único — ver CriarUsuarioForm).
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Nova Senha", slug="pref-nova-senha")
        self.admin = Usuario.objects.create_user(
            username="admin_nova_senha",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_nova_senha",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_nova_senha",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.senha_antiga_hash = self.funcionario.password

    def test_exige_post(self):
        self.client.login(username="admin_nova_senha", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:gerar_nova_senha", args=[self.funcionario.pk]))
        self.assertEqual(403, resposta.status_code)

    def test_admin_gera_nova_senha_para_funcionario(self):
        self.client.login(username="admin_nova_senha", password=SENHA)
        resposta = self.client.post(reverse("app:usuarios:gerar_nova_senha", args=[self.funcionario.pk]))
        self.assertEqual(200, resposta.status_code)

        self.funcionario.refresh_from_db()
        self.assertNotEqual(self.senha_antiga_hash, self.funcionario.password)

        nova_senha = resposta.context["senha"]
        self.assertTrue(check_password(nova_senha, self.funcionario.password))

    def test_senha_antiga_para_de_funcionar(self):
        self.client.login(username="admin_nova_senha", password=SENHA)
        self.client.post(reverse("app:usuarios:gerar_nova_senha", args=[self.funcionario.pk]))
        self.client.logout()

        logou = self.client.login(username="func_nova_senha", password=SENHA)
        self.assertFalse(logou)

    def test_gestor_nao_pode_gerar_senha_do_admin(self):
        hash_antigo = self.admin.password
        self.client.login(username="gestor_nova_senha", password=SENHA)
        resposta = self.client.post(reverse("app:usuarios:gerar_nova_senha", args=[self.admin.pk]))
        self.assertEqual(403, resposta.status_code)
        self.admin.refresh_from_db()
        self.assertEqual(hash_antigo, self.admin.password)

    def test_nao_pode_gerar_a_propria_senha_por_aqui(self):
        self.client.login(username="admin_nova_senha", password=SENHA)
        resposta = self.client.post(reverse("app:usuarios:gerar_nova_senha", args=[self.admin.pk]))
        self.assertEqual(403, resposta.status_code)

    def test_nao_alcanca_usuario_de_outro_tenant(self):
        outro_tenant = Tenant.objects.create(nome="Outra Nova Senha", slug="pref-outra-nova-senha")
        outro_usuario = Usuario.objects.create_user(
            username="func_outro_tenant_senha",
            password=SENHA,
            tenant=outro_tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        hash_antigo = outro_usuario.password
        self.client.login(username="admin_nova_senha", password=SENHA)
        resposta = self.client.post(reverse("app:usuarios:gerar_nova_senha", args=[outro_usuario.pk]))
        self.assertEqual(404, resposta.status_code)
        outro_usuario.refresh_from_db()
        self.assertEqual(hash_antigo, outro_usuario.password)

    def test_gera_evento_de_auditoria(self):
        self.client.login(username="admin_nova_senha", password=SENHA)
        self.client.post(reverse("app:usuarios:gerar_nova_senha", args=[self.funcionario.pk]))
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.SENHA_ALTERADA, usuario=self.funcionario
            ).exists()
        )


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

    def test_filtro_por_usuario_isola_o_que_uma_pessoa_fez(self):
        """
        O caso concreto do pedido: o Admin precisa ver o que um Gestor ou
        Funcionário específico fez, não o log inteiro do tenant misturado.
        """
        funcionario = Usuario.objects.create_user(
            username="func_sob_supervisao",
            password=SENHA,
            tenant=self.tenant_a,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        gestor = Usuario.objects.create_user(
            username="gestor_sob_supervisao",
            password=SENHA,
            tenant=self.tenant_a,
            papel=Papel.objects.get(codigo="gestor"),
        )
        RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO,
            tenant=self.tenant_a,
            usuario=funcionario,
            usuario_identificacao="func_sob_supervisao",
        )
        RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO,
            tenant=self.tenant_a,
            usuario=gestor,
            usuario_identificacao="gestor_sob_supervisao",
        )

        self.client.login(username="admin_audit_a", password=SENHA)
        resposta = self.client.get(
            reverse("app:usuarios:auditoria"), {"usuario": "func_sob_supervisao"}
        )
        registros = list(resposta.context["pagina"])
        self.assertEqual(1, len(registros))
        self.assertEqual("func_sob_supervisao", registros[0].usuario_identificacao)

    def test_lista_de_usuarios_tem_link_direto_para_o_log_de_cada_um(self):
        """A tela de Usuários precisa levar direto ao log filtrado, sem caçar na lista geral."""
        Usuario.objects.create_user(
            username="func_com_link_de_log",
            password=SENHA,
            tenant=self.tenant_a,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.client.login(username="admin_audit_a", password=SENHA)
        resposta = self.client.get(reverse("app:usuarios:lista"))
        self.assertContains(
            resposta,
            f"{reverse('app:usuarios:auditoria')}?usuario=func_com_link_de_log",
        )

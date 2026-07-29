"""
Cadastro de Unidades (Admin) e o escopo de visibilidade por usuário
(docs/features/identificacao-patrimonial-e-unidades.md).

O ponto central da decisão de arquitetura: unidade é uma PERMISSÃO
(`Usuario.unidades`, M2M), não um atributo fixo — um Gestor pode ser
responsável por mais de uma unidade sem alterar o modelo.
"""

from django.test import TestCase
from django.urls import reverse

from contas.models import Papel, Usuario
from core.models import Tenant, Unidade
from core.unidades import unidades_visiveis

SENHA = "senha-bem-longa-2026"


class AcessoAoCadastroDeUnidadesTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Unidades", slug="pref-unid-acesso")
        self.admin = Usuario.objects.create_user(
            username="admin_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_admin_acessa_lista_de_unidades(self):
        self.client.login(username="admin_unid", password=SENHA)
        resposta = self.client.get(reverse("app:unidades:lista"))
        self.assertEqual(200, resposta.status_code)

    def test_gestor_nao_acessa_cadastro_de_unidades(self):
        """Diferente de gerenciar usuário: cadastrar unidade é exclusivo de Admin."""
        self.client.login(username="gestor_unid", password=SENHA)
        resposta = self.client.get(reverse("app:unidades:lista"))
        self.assertEqual(403, resposta.status_code)

    def test_funcionario_nao_acessa_cadastro_de_unidades(self):
        self.client.login(username="func_unid", password=SENHA)
        resposta = self.client.get(reverse("app:unidades:lista"))
        self.assertEqual(403, resposta.status_code)

    def test_link_de_unidades_so_aparece_para_admin(self):
        self.client.login(username="gestor_unid", password=SENHA)
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertNotContains(resposta, reverse("app:unidades:lista"))

        self.client.login(username="admin_unid", password=SENHA)
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertContains(resposta, reverse("app:unidades:lista"))


class CriarUnidadeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Criar Unid", slug="pref-criar-unid")
        self.admin = Usuario.objects.create_user(
            username="admin_criar_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )

    def test_cria_unidade_com_todos_os_campos(self):
        self.client.login(username="admin_criar_unid", password=SENHA)
        self.client.post(
            reverse("app:unidades:criar"),
            {
                "nome": "Fundo Social Centro",
                "tipo": "Fundo Social",
                "responsavel": "Maria Souza",
                "telefone": "(12) 3456-7890",
                "email": "centro@prefeitura.gov.br",
                "endereco": "Rua das Flores, 100",
                "cidade": "São José dos Campos",
                "uf": "SP",
                "observacoes": "Atende zona central",
                "ativo": "on",
            },
        )
        unidade = Unidade.objects.all_tenants().get(nome="Fundo Social Centro", tenant=self.tenant)
        self.assertEqual("Fundo Social", unidade.tipo)
        self.assertEqual("Maria Souza", unidade.responsavel)
        self.assertTrue(unidade.ativo)

    def test_nao_cria_unidade_duplicada_no_mesmo_tenant(self):
        """Nome duplicado é erro de formulário (200 + mensagem), nunca um 500 de banco."""
        Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Fundo Social Sul")
        self.client.login(username="admin_criar_unid", password=SENHA)
        resposta = self.client.post(
            reverse("app:unidades:criar"),
            {"nome": "Fundo Social Sul", "ativo": "on"},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertEqual(
            1, Unidade.objects.all_tenants().filter(tenant=self.tenant, nome="Fundo Social Sul").count()
        )


class AlternarAtivoUnidadeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Alt Unid", slug="pref-alt-unid")
        self.admin = Usuario.objects.create_user(
            username="admin_alt_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Posto X", ativo=True)

    def test_desativa_unidade_ativa(self):
        self.client.login(username="admin_alt_unid", password=SENHA)
        self.client.post(reverse("app:unidades:alternar_ativo", args=[self.unidade.pk]))
        self.unidade.refresh_from_db()
        self.assertFalse(self.unidade.ativo)

    def test_exige_post(self):
        self.client.login(username="admin_alt_unid", password=SENHA)
        resposta = self.client.get(reverse("app:unidades:alternar_ativo", args=[self.unidade.pk]))
        self.assertEqual(403, resposta.status_code)


class UnidadesVisiveisTest(TestCase):
    """
    A função que decide o escopo — testada isoladamente, sem HTTP, porque é
    o núcleo da regra que qualquer view de dado por unidade vai reusar.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Escopo", slug="pref-escopo-unid")
        self.centro = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Centro")
        self.sul = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sul")
        self.norte = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Norte")

    def test_admin_ve_todas_as_unidades_do_tenant(self):
        admin = Usuario.objects.create_user(
            username="admin_escopo",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        visiveis = set(unidades_visiveis(admin))
        self.assertEqual({self.centro, self.sul, self.norte}, visiveis)

    def test_gestor_ve_so_as_unidades_atribuidas(self):
        gestor = Usuario.objects.create_user(
            username="gestor_escopo",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        gestor.unidades.set([self.centro, self.sul])
        visiveis = set(unidades_visiveis(gestor))
        self.assertEqual({self.centro, self.sul}, visiveis)
        self.assertNotIn(self.norte, visiveis)

    def test_gestor_pode_ser_responsavel_por_mais_de_uma_unidade(self):
        """
        O ponto central da decisão de arquitetura: isso funciona sem
        precisar de nenhuma migração ou refatoração de modelo — é só
        atribuir mais uma unidade ao M2M.
        """
        gestor = Usuario.objects.create_user(
            username="gestor_multi_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        gestor.unidades.add(self.centro)
        self.assertEqual(1, unidades_visiveis(gestor).count())
        gestor.unidades.add(self.norte)
        self.assertEqual(2, unidades_visiveis(gestor).count())

    def test_funcionario_sem_unidade_atribuida_nao_ve_nenhuma(self):
        """Fail-closed: sem atribuição explícita, zero unidades — não 'todas por padrão'."""
        funcionario = Usuario.objects.create_user(
            username="func_sem_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.assertEqual(0, unidades_visiveis(funcionario).count())

    def test_nao_mistura_unidade_de_outro_tenant(self):
        outro_tenant = Tenant.objects.create(nome="Outra Prefeitura", slug="pref-outra-escopo")
        unidade_outro_tenant = Unidade.objects.all_tenants().create(
            tenant=outro_tenant, nome="Sede"
        )
        admin = Usuario.objects.create_user(
            username="admin_isolamento_unid",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )
        self.assertNotIn(unidade_outro_tenant, unidades_visiveis(admin))


class UnidadesDoUsuarioTest(TestCase):
    """
    Pegadinha real encontrada durante o desenvolvimento: `usuario.unidades.all()`
    (acessor M2M puro do Django) resolve pelo manager padrão de `Unidade`
    (`TenantManager`, fail-closed pelo ContextVar de tenant corrente) — fora
    de uma requisição HTTP ativa (teste, shell, management command), isso
    devolve vazio mesmo com a atribuição existindo na tabela de junção.
    `unidades_do_usuario()` existe para não repetir esse erro.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura M2M", slug="pref-m2m-unid")
        self.centro = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Centro M2M")
        self.gestor = Usuario.objects.create_user(
            username="gestor_m2m",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.gestor.unidades.add(self.centro)

    def test_acessor_m2m_puro_fica_vazio_fora_de_contexto_de_tenant(self):
        """Documenta a armadilha — não é o comportamento desejado, é o que o Django faz."""
        self.assertEqual(0, self.gestor.unidades.all().count())

    def test_unidades_do_usuario_funciona_fora_de_contexto_de_tenant(self):
        from core.unidades import unidades_do_usuario

        self.assertEqual([self.centro], list(unidades_do_usuario(self.gestor)))

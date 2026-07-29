"""
Trilha de auditoria: imutabilidade, cobertura dos eventos de autenticação e
extração confiável do IP de origem.
"""

from unittest import mock

from django.db import OperationalError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from auditoria.models import AcaoAuditada, RegistroAuditoria
from auditoria.services import ip_do_cliente, registrar
from contas.models import Papel, Usuario
from core.models import Tenant


class ImutabilidadeTest(TestCase):
    def setUp(self):
        self.registro = RegistroAuditoria.objects.create(
            acao=AcaoAuditada.LOGIN_SUCESSO, usuario_identificacao="alguem"
        )

    def test_registro_gravado_nao_pode_ser_alterado(self):
        self.registro.descricao = "reescrito"
        with self.assertRaises(RuntimeError):
            self.registro.save()

    def test_registro_nao_pode_ser_excluido(self):
        with self.assertRaises(RuntimeError):
            self.registro.delete()

    def test_expurgo_em_massa_continua_possivel(self):
        """
        O bloqueio é do `delete()` do model. O expurgo por prazo de retenção
        usa `QuerySet.delete()`, que opera direto no banco — é a exceção
        deliberada, exposta só pelo comando `expurgar_auditoria`.
        """
        RegistroAuditoria.objects.all().delete()
        self.assertEqual(0, RegistroAuditoria.objects.count())


class ExtracaoDeIpTest(TestCase):
    """
    Confiar no `X-Forwarded-For` que o cliente enviou é a falha clássica: quem
    ataca some do log e ainda consegue disparar o bloqueio no IP de outra
    pessoa. Com N proxies confiáveis, o IP autêntico é o N-ésimo da direita.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def test_sem_proxy_confiavel_usa_remote_addr(self):
        requisicao = self.factory.get("/", REMOTE_ADDR="203.0.113.10")
        requisicao.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4"
        with self.settings(SEGURANCA_PROXIES_CONFIAVEIS=0):
            self.assertEqual("203.0.113.10", ip_do_cliente(requisicao))

    def test_com_um_proxy_usa_o_ultimo_do_encaminhamento(self):
        requisicao = self.factory.get("/", REMOTE_ADDR="10.0.0.1")
        requisicao.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.7"
        with self.settings(SEGURANCA_PROXIES_CONFIAVEIS=1):
            self.assertEqual("198.51.100.7", ip_do_cliente(requisicao))

    def test_ignora_ip_forjado_pelo_cliente(self):
        # O cliente mandou "1.2.3.4"; o proxy confiável acrescentou o IP real
        # à direita. O valor da esquerda é texto escolhido por quem ataca.
        requisicao = self.factory.get("/", REMOTE_ADDR="10.0.0.1")
        requisicao.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4, 198.51.100.7"
        with self.settings(SEGURANCA_PROXIES_CONFIAVEIS=1):
            self.assertEqual("198.51.100.7", ip_do_cliente(requisicao))

    def test_valor_invalido_vira_none_em_vez_de_quebrar(self):
        requisicao = self.factory.get("/", REMOTE_ADDR="nao-e-um-ip")
        with self.settings(SEGURANCA_PROXIES_CONFIAVEIS=0):
            self.assertIsNone(ip_do_cliente(requisicao))


class ResilienciaTest(TestCase):
    def test_falha_na_gravacao_nao_derruba_a_requisicao(self):
        """
        Um problema momentâneo na tabela de auditoria não pode interromper um
        atendimento em andamento — o erro vai para o log, a requisição segue.

        A falha é simulada por mock em vez de provocada de verdade (com uma FK
        inválida, por exemplo): um erro real de banco marcaria a transação do
        TestCase como quebrada e derrubaria os testes seguintes da classe.
        """
        with mock.patch.object(
            RegistroAuditoria.objects, "create", side_effect=OperationalError("banco fora")
        ):
            with self.assertLogs("auditoria.services", level="ERROR"):
                registro = registrar(AcaoAuditada.ACESSO_DADO_PESSOAL)

        self.assertIsNone(registro)


class AuditoriaDeAutenticacaoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura X", slug="pref-audit")
        self.usuario = Usuario.objects.create_user(
            username="func_audit",
            password="senha-bem-longa-2026",
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_login_bem_sucedido_e_registrado(self):
        self.client.post(
            reverse("login"),
            {"username": "func_audit", "password": "senha-bem-longa-2026"},
        )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.LOGIN_SUCESSO, usuario=self.usuario
            ).exists()
        )

    def test_login_malsucedido_e_registrado_com_a_identificacao_tentada(self):
        self.client.post(
            reverse("login"), {"username": "func_audit", "password": "errada"}
        )
        registro = RegistroAuditoria.objects.filter(acao=AcaoAuditada.LOGIN_FALHA).first()
        self.assertIsNotNone(registro)
        self.assertEqual("func_audit", registro.usuario_identificacao)

    def test_senha_nunca_aparece_na_trilha(self):
        self.client.post(
            reverse("login"),
            {"username": "func_audit", "password": "senha-secreta-do-usuario"},
        )
        for registro in RegistroAuditoria.objects.all():
            texto = f"{registro.descricao} {registro.usuario_identificacao}"
            self.assertNotIn("senha-secreta-do-usuario", texto)

    def test_logout_e_registrado(self):
        self.client.login(username="func_audit", password="senha-bem-longa-2026")
        self.client.post(reverse("logout"))
        self.assertTrue(
            RegistroAuditoria.objects.filter(acao=AcaoAuditada.LOGOUT).exists()
        )

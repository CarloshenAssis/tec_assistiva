"""
Bloqueio de autenticação por excesso de tentativas.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from auditoria.models import AcaoAuditada, RegistroAuditoria
from contas.bloqueio import esta_bloqueado, tentativas_restantes
from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"


class BloqueioPorTentativasTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Y", slug="pref-bloq")
        self.usuario = Usuario.objects.create_user(
            username="func_bloq",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def _tentar(self, senha, usuario="func_bloq"):
        return self.client.post(reverse("login"), {"username": usuario, "password": senha})

    def test_conta_livre_no_inicio(self):
        self.assertFalse(esta_bloqueado(identificacao="func_bloq", ip=None).bloqueado)

    def test_bloqueia_apos_o_limite_de_tentativas(self):
        with self.settings(SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO=3):
            for _ in range(3):
                self._tentar("errada")
            self.assertTrue(esta_bloqueado(identificacao="func_bloq", ip=None).bloqueado)

    def test_senha_correta_e_recusada_enquanto_bloqueado(self):
        """O ponto central: bloqueado é bloqueado, mesmo acertando a senha."""
        with self.settings(SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO=3):
            for _ in range(3):
                self._tentar("errada")

            resposta = self._tentar(SENHA)

            self.assertEqual(200, resposta.status_code)  # reexibe o formulário
            self.assertFalse(resposta.wsgi_request.user.is_authenticated)

    def test_bloqueio_de_um_usuario_nao_afeta_outro(self):
        outro = Usuario.objects.create_user(
            username="func_bloq_2",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        with self.settings(
            SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO=3,
            # Limiar de IP alto para isolar o efeito por identificação — os
            # dois usuários compartilham o IP do cliente de teste.
            SEGURANCA_LOGIN_MAX_TENTATIVAS_IP=100,
        ):
            for _ in range(3):
                self._tentar("errada")

            self._tentar(SENHA, usuario="func_bloq_2")

        self.assertEqual(outro.pk, int(self.client.session["_auth_user_id"]))

    def test_bloqueio_por_ip_pega_tentativa_espalhada_entre_usuarios(self):
        """
        Password spraying: poucas tentativas em muitas contas passa despercebido
        pelo limiar por identificação, e é justamente o que o limiar por IP pega.
        """
        with self.settings(
            SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO=100,
            SEGURANCA_LOGIN_MAX_TENTATIVAS_IP=4,
        ):
            for indice in range(4):
                self._tentar("errada", usuario=f"alvo_{indice}")

            resultado = esta_bloqueado(identificacao="ainda_outro", ip="127.0.0.1")
            self.assertTrue(resultado.bloqueado)

    def test_tentativa_fora_da_janela_nao_conta(self):
        with self.settings(
            SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO=3,
            SEGURANCA_LOGIN_JANELA_MINUTOS=15,
        ):
            for _ in range(3):
                self._tentar("errada")
            self.assertTrue(esta_bloqueado(identificacao="func_bloq", ip=None).bloqueado)

            # Envelhece as falhas para além da janela.
            RegistroAuditoria.objects.filter(acao=AcaoAuditada.LOGIN_FALHA).update(
                criado_em=timezone.now() - timezone.timedelta(minutes=30)
            )
            self.assertFalse(esta_bloqueado(identificacao="func_bloq", ip=None).bloqueado)

    def test_bloqueio_gera_um_unico_registro_por_episodio(self):
        """
        Registrar a cada tentativa barrada deixaria quem ataca inflar a tabela
        de auditoria à vontade. Só a falha que cruza o limiar registra.
        """
        with self.settings(SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO=3):
            for _ in range(10):
                self._tentar("errada")

        self.assertEqual(
            1,
            RegistroAuditoria.objects.filter(acao=AcaoAuditada.BLOQUEIO_TENTATIVAS).count(),
        )

    def test_mensagem_nao_revela_se_a_conta_existe(self):
        with self.settings(SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO=2):
            for _ in range(2):
                self._tentar("errada", usuario="conta_que_nao_existe")
            resposta = self._tentar("errada", usuario="conta_que_nao_existe")

        corpo = resposta.content.decode()
        self.assertNotIn("não existe", corpo)
        self.assertNotIn("não cadastrado", corpo)
        self.assertIn("Muitas tentativas", corpo)

    def test_contador_de_tentativas_restantes(self):
        with self.settings(SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO=5):
            self.assertEqual(5, tentativas_restantes(identificacao="func_bloq"))
            self._tentar("errada")
            self.assertEqual(4, tentativas_restantes(identificacao="func_bloq"))

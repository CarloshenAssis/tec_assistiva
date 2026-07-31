"""
Limite de taxa (auditoria/limitador.py) — baseado na trilha de auditoria,
não em cache (ver docstring do módulo para a razão: Vercel é serverless).
"""

from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from ativos.models import Movimentacao
from auditoria import limitador
from auditoria.models import AcaoAuditada, RegistroAuditoria
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant

_MOVIMENTACAO = Movimentacao._meta.label
_BENEFICIARIO = Beneficiario._meta.label


class LimiteAtingidoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Limitador", slug="pref-limitador")
        papel = Papel.objects.get(codigo="admin")
        self.usuario = Usuario.objects.create_user(
            username="admin_limitador", password="senha-bem-longa-2026", tenant=self.tenant, papel=papel
        )

    def _gerar_eventos(self, quantidade, acao=AcaoAuditada.CRIACAO, objeto_tipo=_MOVIMENTACAO):
        for _ in range(quantidade):
            RegistroAuditoria.objects.create(
                usuario=self.usuario, acao=acao, objeto_tipo=objeto_tipo
            )

    def test_usuario_anonimo_nunca_e_limitado(self):
        self.assertFalse(
            limitador.limite_atingido(
                usuario=None, objeto_tipo=_MOVIMENTACAO, limite=1, janela_minutos=5
            )
        )

    def test_abaixo_do_limite_nao_bloqueia(self):
        self._gerar_eventos(59)
        self.assertFalse(
            limitador.limite_atingido(
                usuario=self.usuario, objeto_tipo=_MOVIMENTACAO, limite=60, janela_minutos=5
            )
        )

    def test_no_limite_bloqueia(self):
        self._gerar_eventos(60)
        self.assertTrue(
            limitador.limite_atingido(
                usuario=self.usuario, objeto_tipo=_MOVIMENTACAO, limite=60, janela_minutos=5
            )
        )

    def test_so_conta_o_tipo_de_objeto_pedido(self):
        self._gerar_eventos(60, objeto_tipo=_BENEFICIARIO)
        self.assertFalse(
            limitador.limite_atingido(
                usuario=self.usuario, objeto_tipo=_MOVIMENTACAO, limite=60, janela_minutos=5
            )
        )

    def test_so_conta_a_acao_pedida(self):
        self._gerar_eventos(60, acao=AcaoAuditada.ALTERACAO, objeto_tipo=_BENEFICIARIO)
        self.assertFalse(
            limitador.limite_atingido(
                usuario=self.usuario,
                objeto_tipo=_BENEFICIARIO,
                acao=AcaoAuditada.ANONIMIZACAO,
                limite=5,
                janela_minutos=60,
            )
        )

    def test_evento_fora_da_janela_nao_conta(self):
        self._gerar_eventos(60)
        RegistroAuditoria.objects.all().update(criado_em=timezone.now() - timedelta(minutes=10))
        self.assertFalse(
            limitador.limite_atingido(
                usuario=self.usuario, objeto_tipo=_MOVIMENTACAO, limite=60, janela_minutos=5
            )
        )


class RegistrarLimiteAtingidoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Limitador Log", slug="pref-limitador-log")
        papel = Papel.objects.get(codigo="admin")
        self.usuario = Usuario.objects.create_user(
            username="admin_log_limitador", password="senha-bem-longa-2026", tenant=self.tenant, papel=papel
        )
        self.request = RequestFactory().post("/qualquer/")
        self.request.user = self.usuario
        self.request.tenant = self.tenant

    def test_primeira_chamada_grava(self):
        limitador.registrar_limite_atingido(
            request=self.request,
            objeto_tipo=_MOVIMENTACAO,
            limite=60,
            janela_minutos=5,
            descricao="Limite de movimentações atingido (60/5min)",
        )
        self.assertEqual(
            1,
            RegistroAuditoria.objects.filter(
                usuario=self.usuario, acao=AcaoAuditada.ACESSO_NEGADO
            ).count(),
        )

    def test_chamadas_repetidas_na_mesma_janela_nao_duplicam(self):
        for _ in range(5):
            limitador.registrar_limite_atingido(
                request=self.request,
                objeto_tipo=_MOVIMENTACAO,
                limite=60,
                janela_minutos=5,
                descricao="Limite de movimentações atingido (60/5min)",
            )
        self.assertEqual(
            1,
            RegistroAuditoria.objects.filter(
                usuario=self.usuario, acao=AcaoAuditada.ACESSO_NEGADO
            ).count(),
        )

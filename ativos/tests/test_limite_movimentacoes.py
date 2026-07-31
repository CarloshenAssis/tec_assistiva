"""
Limite de taxa em executar_acao (auditoria/limitador.py) — trava conta
autenticada que gera movimentação em excesso, sem impedir uso humano normal.
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from ativos.domain.enums import StatusAtivo
from ativos.models import Ativo, CategoriaAtivo
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id

SENHA = "senha-bem-longa-2026"


class LimiteMovimentacoesTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Limite Mov", slug="pref-limite-mov")
        token = set_current_tenant_id(self.tenant.pk)
        self.addCleanup(reset_current_tenant_id, token)

        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-0001", categoria=self.categoria, unidade=self.unidade
        )

        gestor_papel = Papel.objects.get(codigo="gestor")
        self.gestor = Usuario.objects.create_user(
            username="gestor_limite_mov", password=SENHA, tenant=self.tenant, papel=gestor_papel
        )
        self.gestor.unidades.add(self.unidade)
        self.client.login(username="gestor_limite_mov", password=SENHA)

    def _reservar_e_cancelar(self):
        """Um ciclo reservar → cancelar gera duas Movimentacao no mesmo ativo."""
        self.client.post(reverse("app:ativos:executar_acao", args=[self.ativo.pk, "reservar"]))
        self.client.post(reverse("app:ativos:executar_acao", args=[self.ativo.pk, "cancelar_reserva"]))

    @patch("ativos.views._LIMITE_MOVIMENTACOES", 4)
    @patch("ativos.views._LIMITE_MOVIMENTACOES_JANELA_MINUTOS", 5)
    def test_bloqueia_apos_o_limite(self):
        # 2 ciclos = 4 movimentações, exatamente no limite — a 5ª (início do
        # 3º ciclo) deve ser recusada antes de mudar o estado do ativo.
        self._reservar_e_cancelar()
        self._reservar_e_cancelar()
        self.assertEqual(StatusAtivo.DISPONIVEL.value, self.ativo.status)

        self.client.post(reverse("app:ativos:executar_acao", args=[self.ativo.pk, "reservar"]))
        self.ativo.refresh_from_db()
        self.assertEqual(
            StatusAtivo.DISPONIVEL.value,
            self.ativo.status,
            "ação deveria ter sido recusada pelo limite, sem mudar o estado do ativo",
        )

    @patch("ativos.views._LIMITE_MOVIMENTACOES", 4)
    @patch("ativos.views._LIMITE_MOVIMENTACOES_JANELA_MINUTOS", 5)
    def test_mensagem_de_erro_amigavel_nao_500(self):
        self._reservar_e_cancelar()
        self._reservar_e_cancelar()

        resposta = self.client.post(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "reservar"]), follow=True
        )
        self.assertEqual(200, resposta.status_code)
        mensagens = [str(m) for m in resposta.context["messages"]]
        self.assertTrue(any("Muitas ações em pouco tempo" in m for m in mensagens))

    @patch("ativos.views._LIMITE_MOVIMENTACOES", 4)
    @patch("ativos.views._LIMITE_MOVIMENTACOES_JANELA_MINUTOS", 5)
    def test_bloqueio_grava_uma_unica_linha_de_auditoria(self):
        from auditoria.models import AcaoAuditada, RegistroAuditoria

        self._reservar_e_cancelar()
        self._reservar_e_cancelar()

        for _ in range(3):
            self.client.post(reverse("app:ativos:executar_acao", args=[self.ativo.pk, "reservar"]))

        self.assertEqual(
            1,
            RegistroAuditoria.objects.filter(
                usuario=self.gestor, acao=AcaoAuditada.ACESSO_NEGADO
            ).count(),
        )

    def test_uso_normal_abaixo_do_limite_nao_e_afetado(self):
        # Sem patch: limite real (60/5min) — um uso humano comum passa liso.
        for _ in range(5):
            self._reservar_e_cancelar()
        self.ativo.refresh_from_db()
        self.assertEqual(StatusAtivo.DISPONIVEL.value, self.ativo.status)

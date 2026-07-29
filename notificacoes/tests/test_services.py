from django.test import TestCase

from beneficiarios.models import Beneficiario
from core.models import Tenant
from core.tenancy import reset_current_tenant_id, set_current_tenant_id
from notificacoes.models import NotificacaoEnviada, NotificacaoTemplate
from notificacoes.services import criar_e_enviar, ja_notificado_hoje


class NotificacoesServicesTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura A", slug="pref-a-notif")
        token = set_current_tenant_id(self.tenant.pk)
        self.addCleanup(reset_current_tenant_id, token)

        self.template = NotificacaoTemplate.objects.all_tenants().create(
            tenant=self.tenant,
            tipo=NotificacaoTemplate.Tipo.CONFIRMACAO_EMPRESTIMO,
            titulo="Empréstimo realizado",
            corpo_texto="Olá {beneficiario}, seu {ativo} ({codigo}) vence em {data_prevista}.",
        )
        self.beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Maria Silva", cpf="123.456.789-09", whatsapp="(12) 99999-0000"
        )

    def test_criar_e_enviar_gera_notificacao_por_canal_disponivel(self):
        contexto = {"beneficiario": "Maria Silva", "ativo": "Cadeira", "codigo": "CAD-0001", "data_prevista": "10/08"}
        enviadas = criar_e_enviar(self.tenant, self.beneficiario, "confirmacao_emprestimo", contexto)

        self.assertEqual(len(enviadas), 1)  # só whatsapp, sem email cadastrado
        notificacao = enviadas[0]
        self.assertEqual(notificacao.status, NotificacaoEnviada.Status.ENVIADO)
        self.assertIn("Maria Silva", notificacao.corpo_renderizado)

    def test_sem_template_nao_gera_notificacao(self):
        enviadas = criar_e_enviar(self.tenant, self.beneficiario, "tipo_inexistente", {})
        self.assertEqual(enviadas, [])

    def test_ja_notificado_hoje_evita_duplicidade(self):
        contexto = {"beneficiario": "Maria Silva", "ativo": "Cadeira", "codigo": "CAD-0001", "data_prevista": "10/08"}
        criar_e_enviar(self.tenant, self.beneficiario, "confirmacao_emprestimo", contexto)

        self.assertTrue(ja_notificado_hoje(self.beneficiario, "confirmacao_emprestimo"))
        self.assertFalse(ja_notificado_hoje(self.beneficiario, "aviso_7_dias"))

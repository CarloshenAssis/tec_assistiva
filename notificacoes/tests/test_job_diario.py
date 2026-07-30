from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from ativos import services
from ativos.models import Ativo, CategoriaAtivo, DetalheEmprestimo
from beneficiarios.models import Beneficiario
from core.models import Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id
from notificacoes.models import NotificacaoEnviada, NotificacaoTemplate


class JobDiarioNotificacoesTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura A", slug="pref-a-job")
        token = set_current_tenant_id(self.tenant.pk)
        self.addCleanup(reset_current_tenant_id, token)

        for tipo, titulo in [
            (NotificacaoTemplate.Tipo.AVISO_7_DIAS, "7 dias"),
            (NotificacaoTemplate.Tipo.VENCIMENTO, "vencimento"),
            (NotificacaoTemplate.Tipo.ATRASO, "atraso"),
        ]:
            NotificacaoTemplate.objects.all_tenants().create(
                tenant=self.tenant, tipo=tipo, titulo=titulo, corpo_texto="{beneficiario} {codigo} {dias}"
            )

        self.categoria = CategoriaAtivo.objects.all_tenants().create(tenant=self.tenant, nome="Cadeira de Rodas")
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Maria Silva", cpf="123.456.789-09", whatsapp="(12) 99999-0000"
        )

    def _emprestar_com_prazo(self, patrimonio, dias_ate_vencer):
        ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant,
            patrimonio=patrimonio,
            categoria=self.categoria,
            unidade=self.unidade,
        )
        services.emprestar(ativo, self.beneficiario, usuario=None, prazo_dias=30)
        detalhe = DetalheEmprestimo.objects.get(movimentacao__ativo=ativo)
        detalhe.data_prevista_devolucao = timezone.now().date() + timedelta(days=dias_ate_vencer)
        detalhe.save(update_fields=["data_prevista_devolucao"])
        return ativo

    def test_dispara_aviso_de_7_dias_vencimento_e_atraso(self):
        self._emprestar_com_prazo("CAD-0001", 7)
        self._emprestar_com_prazo("CAD-0002", 0)
        self._emprestar_com_prazo("CAD-0003", -3)
        self._emprestar_com_prazo("CAD-0004", 15)  # não deve gerar nada ainda

        call_command("enviar_notificacoes_diarias")

        tipos_enviados = set(
            NotificacaoEnviada.objects.filter(beneficiario=self.beneficiario)
            .exclude(template__tipo=NotificacaoTemplate.Tipo.CONFIRMACAO_EMPRESTIMO)
            .values_list("template__tipo", flat=True)
        )
        self.assertEqual(tipos_enviados, {"aviso_7_dias", "vencimento", "atraso"})

    def test_nao_duplica_notificacao_no_mesmo_dia(self):
        self._emprestar_com_prazo("CAD-0005", -1)

        call_command("enviar_notificacoes_diarias")
        primeira_contagem = NotificacaoEnviada.objects.filter(template__tipo="atraso").count()

        call_command("enviar_notificacoes_diarias")
        segunda_contagem = NotificacaoEnviada.objects.filter(template__tipo="atraso").count()

        self.assertEqual(primeira_contagem, segunda_contagem)

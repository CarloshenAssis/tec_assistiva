"""
Dados financeiros de locação em DetalheEmprestimo (docs/business-rules/modulos.md).
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from ativos import services
from ativos.models import Ativo, CategoriaAtivo, DetalheEmprestimo
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core import features
from core.models import Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id

SENHA = "senha-bem-longa-2026"


class ValorMultaAtrasoTest(TestCase):
    """Cálculo puro — sem tocar em HTTP nem em módulo habilitado ou não."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Locadora Calculo", slug="locadora-calculo-fin", segmento=Tenant.Segmento.LOCADORA
        )
        token = set_current_tenant_id(self.tenant.pk)
        self.addCleanup(reset_current_tenant_id, token)

        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Andaime", prefixo="AND"
        )
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="AND-0001", categoria=self.categoria, unidade=self.unidade
        )
        self.cliente = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Construtora ABC", documento="123.456.789-09"
        )

    def _detalhe(self, **kwargs):
        movimentacao = services.emprestar(
            self.ativo, self.cliente, usuario=None, prazo_dias=10, **kwargs
        )
        return DetalheEmprestimo.objects.get(movimentacao=movimentacao)

    def test_sem_dados_financeiros_tudo_e_none(self):
        detalhe = self._detalhe()
        self.assertIsNone(detalhe.valor_total_periodo)
        self.assertIsNone(detalhe.valor_multa_atraso())

    def test_valor_total_periodo_multiplica_diaria_pelo_prazo(self):
        detalhe = self._detalhe(valor_diaria=Decimal("50.00"))
        self.assertEqual(Decimal("500.00"), detalhe.valor_total_periodo)

    def test_sem_atraso_multa_e_zero(self):
        import datetime

        detalhe = self._detalhe(valor_diaria=Decimal("50.00"), percentual_multa_atraso_dia=Decimal("2"))
        hoje = detalhe.data_prevista_devolucao - datetime.timedelta(days=1)
        self.assertEqual(Decimal("0"), detalhe.valor_multa_atraso(hoje=hoje))

    def test_multa_cresce_por_dia_de_atraso(self):
        import datetime

        detalhe = self._detalhe(valor_diaria=Decimal("50.00"), percentual_multa_atraso_dia=Decimal("2"))
        # valor_total_periodo = 500; 2% ao dia; 3 dias de atraso = 30.00
        hoje = detalhe.data_prevista_devolucao + datetime.timedelta(days=3)
        self.assertEqual(Decimal("30.000"), detalhe.valor_multa_atraso(hoje=hoje))

    def test_multa_precisa_de_diaria_e_percentual_juntos(self):
        """Só caução, sem diária/percentual, não permite calcular multa nenhuma."""
        detalhe = self._detalhe(caucao=Decimal("300.00"))
        self.assertIsNone(detalhe.valor_multa_atraso())


class WizardCapturaDadosFinanceirosTest(TestCase):
    def setUp(self):
        self.locadora = Tenant.objects.create(
            nome="Locadora Wizard", slug="locadora-wizard-fin", segmento=Tenant.Segmento.LOCADORA
        )
        self.prefeitura = Tenant.objects.create(
            nome="Prefeitura Wizard", slug="pref-wizard-fin", segmento=Tenant.Segmento.FUNDO_SOCIAL
        )
        self.unidade_loc = Unidade.objects.all_tenants().create(tenant=self.locadora, nome="Sede")
        self.unidade_pref = Unidade.objects.all_tenants().create(tenant=self.prefeitura, nome="Sede")

        self.func_locadora = Usuario.objects.create_user(
            username="func_locadora_fin", password=SENHA, tenant=self.locadora, papel=Papel.objects.get(codigo="funcionario")
        )
        self.func_locadora.unidades.add(self.unidade_loc)
        self.func_prefeitura = Usuario.objects.create_user(
            username="func_prefeitura_fin", password=SENHA, tenant=self.prefeitura, papel=Papel.objects.get(codigo="funcionario")
        )
        self.func_prefeitura.unidades.add(self.unidade_pref)

        categoria_loc = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.locadora, nome="Betoneira", prefixo="BET"
        )
        self.ativo_loc = Ativo.objects.all_tenants().create(
            tenant=self.locadora, patrimonio="BET-0001", categoria=categoria_loc, unidade=self.unidade_loc
        )
        self.cliente_loc = Beneficiario.objects.all_tenants().create(
            tenant=self.locadora, nome="Obra XPTO", documento="123.456.789-09"
        )

        categoria_pref = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.prefeitura, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.ativo_pref = Ativo.objects.all_tenants().create(
            tenant=self.prefeitura, patrimonio="CAD-0001", categoria=categoria_pref, unidade=self.unidade_pref
        )
        self.beneficiario_pref = Beneficiario.objects.all_tenants().create(
            tenant=self.prefeitura, nome="Maria Silva", documento="234.567.891-73"
        )

    def _avancar_ate_prazo(self, client, beneficiario_id, ativo_id):
        client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {"wizard_acao": "selecionar_beneficiario", "beneficiario_id": beneficiario_id},
        )
        client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {"wizard_acao": "selecionar_ativo", "ativo_id": ativo_id},
        )

    def test_passo_3_da_locadora_oferece_campos_financeiros(self):
        self.client.login(username="func_locadora_fin", password=SENHA)
        self._avancar_ate_prazo(self.client, self.cliente_loc.pk, self.ativo_loc.pk)
        resposta = self.client.get(reverse("app:ativos:wizard_emprestimo"))
        self.assertContains(resposta, "Valor da diária")
        self.assertContains(resposta, "Caução")

    def test_passo_3_da_prefeitura_nao_oferece_campos_financeiros(self):
        self.client.login(username="func_prefeitura_fin", password=SENHA)
        self._avancar_ate_prazo(self.client, self.beneficiario_pref.pk, self.ativo_pref.pk)
        resposta = self.client.get(reverse("app:ativos:wizard_emprestimo"))
        self.assertNotContains(resposta, "Valor da diária")

    def test_emprestimo_confirmado_grava_valores_financeiros(self):
        self.client.login(username="func_locadora_fin", password=SENHA)
        self._avancar_ate_prazo(self.client, self.cliente_loc.pk, self.ativo_loc.pk)
        self.client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {
                "wizard_acao": "definir_prazo",
                "prazo_dias": "15",
                "valor_diaria": "80,50",
                "caucao": "200",
                "percentual_multa_atraso_dia": "1.5",
            },
        )
        self.client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {"wizard_acao": "confirmar", "checklist_termo_impresso": "on"},
        )
        detalhe = DetalheEmprestimo.objects.all_tenants().get(movimentacao__ativo=self.ativo_loc)
        self.assertEqual(Decimal("80.50"), detalhe.valor_diaria)
        self.assertEqual(Decimal("200"), detalhe.caucao)
        self.assertEqual(Decimal("1.5"), detalhe.percentual_multa_atraso_dia)

    def test_valor_invalido_e_erro_amigavel_nao_500(self):
        self.client.login(username="func_locadora_fin", password=SENHA)
        self._avancar_ate_prazo(self.client, self.cliente_loc.pk, self.ativo_loc.pk)
        resposta = self.client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {"wizard_acao": "definir_prazo", "prazo_dias": "15", "valor_diaria": "abc"},
            follow=True,
        )
        self.assertContains(resposta, "Valor de locação inválido")

    def test_prefeitura_nao_grava_campos_financeiros_mesmo_forjando_o_post(self):
        """O passo 3 nem lê esses campos do POST quando o módulo está desligado."""
        self.client.login(username="func_prefeitura_fin", password=SENHA)
        self._avancar_ate_prazo(self.client, self.beneficiario_pref.pk, self.ativo_pref.pk)
        self.client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {"wizard_acao": "definir_prazo", "prazo_dias": "30", "valor_diaria": "80.50"},
        )
        self.client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {"wizard_acao": "confirmar", "checklist_termo_impresso": "on"},
        )
        detalhe = DetalheEmprestimo.objects.all_tenants().get(movimentacao__ativo=self.ativo_pref)
        self.assertIsNone(detalhe.valor_diaria)


class DevolucaoMostraMultaEstimadaTest(TestCase):
    def setUp(self):
        self.locadora = Tenant.objects.create(
            nome="Locadora Devolucao Fin", slug="locadora-devol-fin", segmento=Tenant.Segmento.LOCADORA
        )
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.locadora, nome="Sede")
        self.func = Usuario.objects.create_user(
            username="func_devol_fin", password=SENHA, tenant=self.locadora, papel=Papel.objects.get(codigo="funcionario")
        )
        self.func.unidades.add(self.unidade)
        categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.locadora, nome="Betoneira", prefixo="BET"
        )
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.locadora, patrimonio="BET-0002", categoria=categoria, unidade=self.unidade
        )
        self.cliente = Beneficiario.objects.all_tenants().create(
            tenant=self.locadora, nome="Obra Atrasada", documento="123.456.789-09"
        )

    def test_devolucao_atrasada_mostra_multa_estimada(self):
        import datetime

        token = set_current_tenant_id(self.locadora.pk)
        try:
            movimentacao = services.emprestar(
                self.ativo,
                self.cliente,
                usuario=None,
                prazo_dias=5,
                valor_diaria=Decimal("100.00"),
                percentual_multa_atraso_dia=Decimal("2"),
            )
            detalhe = DetalheEmprestimo.objects.get(movimentacao=movimentacao)
            detalhe.data_prevista_devolucao = datetime.date.today() - datetime.timedelta(days=4)
            detalhe.save(update_fields=["data_prevista_devolucao"])
        finally:
            reset_current_tenant_id(token)

        self.client.login(username="func_devol_fin", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:devolucao"), {"q": "BET-0002"})
        self.assertContains(resposta, "Multa por atraso estimada")

    def test_sem_atraso_nao_mostra_multa(self):
        token = set_current_tenant_id(self.locadora.pk)
        try:
            services.emprestar(
                self.ativo,
                self.cliente,
                usuario=None,
                prazo_dias=30,
                valor_diaria=Decimal("100.00"),
                percentual_multa_atraso_dia=Decimal("2"),
            )
        finally:
            reset_current_tenant_id(token)

        self.client.login(username="func_devol_fin", password=SENHA)
        resposta = self.client.get(reverse("app:ativos:devolucao"), {"q": "BET-0002"})
        self.assertNotContains(resposta, "Multa por atraso estimada")


class ModuloFinanceiroDesligadoNaoAparece(TestCase):
    def test_locadora_com_modulo_desligado_manualmente_nao_ve_campos(self):
        locadora = Tenant.objects.create(
            nome="Locadora Sem Financeiro", slug="locadora-sem-fin", segmento=Tenant.Segmento.LOCADORA
        )
        features.definir_modulo(locadora, features.LOCACAO_FINANCEIRO, False)
        unidade = Unidade.objects.all_tenants().create(tenant=locadora, nome="Sede")
        func = Usuario.objects.create_user(
            username="func_sem_fin", password=SENHA, tenant=locadora, papel=Papel.objects.get(codigo="funcionario")
        )
        func.unidades.add(unidade)
        categoria = CategoriaAtivo.objects.all_tenants().create(tenant=locadora, nome="Betoneira", prefixo="BET")
        ativo = Ativo.objects.all_tenants().create(
            tenant=locadora, patrimonio="BET-0003", categoria=categoria, unidade=unidade
        )
        beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=locadora, nome="Obra Y", documento="123.456.789-09"
        )

        self.client.login(username="func_sem_fin", password=SENHA)
        self.client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {"wizard_acao": "selecionar_beneficiario", "beneficiario_id": beneficiario.pk},
        )
        self.client.post(
            reverse("app:ativos:wizard_emprestimo"),
            {"wizard_acao": "selecionar_ativo", "ativo_id": ativo.pk},
        )
        resposta = self.client.get(reverse("app:ativos:wizard_emprestimo"))
        self.assertNotContains(resposta, "Valor da diária")

"""
Testes de integração dos services (Django ORM + banco de dados real),
cobrindo os fluxos completos de empréstimo/devolução/manutenção e o
isolamento multi-tenant sobre `Ativo`/`Movimentacao`.
"""

from django.test import TestCase

from ativos import services
from ativos.domain.enums import StatusAtivo
from ativos.domain.exceptions import TransicaoInvalidaError
from ativos.models import Ativo, CategoriaAtivo, Movimentacao
from beneficiarios.models import Beneficiario
from core.models import Tenant
from core.tenancy import reset_current_tenant_id, set_current_tenant_id


class BaseComTenant(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura A", slug="prefeitura-a-svc")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura B", slug="prefeitura-b-svc")

        token = set_current_tenant_id(self.tenant_a.pk)
        self.addCleanup(reset_current_tenant_id, token)

        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Cadeira de Rodas"
        )
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant_a, patrimonio="CAD-0001", categoria=self.categoria
        )
        self.beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Maria Silva", cpf="123.456.789-00"
        )


class FluxoEmprestimoDevolucaoTest(BaseComTenant):
    def test_emprestar_altera_status_e_cria_movimentacao(self):
        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)

        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.EMPRESTADO.value)

        movimentacao = Movimentacao.objects.get(ativo=self.ativo)
        self.assertEqual(movimentacao.tipo, "emprestimo")
        self.assertEqual(movimentacao.status_anterior, "disponivel")
        self.assertEqual(movimentacao.status_novo, "emprestado")
        self.assertEqual(movimentacao.detalhe_emprestimo.beneficiario, self.beneficiario)

    def test_nao_permite_emprestar_duas_vezes(self):
        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)
        self.ativo.refresh_from_db()

        with self.assertRaises(TransicaoInvalidaError):
            services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)

    def test_devolucao_para_disponivel(self):
        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)
        self.ativo.refresh_from_db()

        services.devolver(self.ativo, usuario=None, destino=StatusAtivo.DISPONIVEL)
        self.ativo.refresh_from_db()

        self.assertEqual(self.ativo.status, StatusAtivo.DISPONIVEL.value)
        self.assertEqual(Movimentacao.objects.filter(ativo=self.ativo).count(), 2)

    def test_devolucao_para_manutencao_bloqueia_novo_emprestimo(self):
        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)
        self.ativo.refresh_from_db()
        services.devolver(self.ativo, usuario=None, destino=StatusAtivo.MANUTENCAO)
        self.ativo.refresh_from_db()

        self.assertEqual(self.ativo.status, StatusAtivo.MANUTENCAO.value)
        with self.assertRaises(TransicaoInvalidaError):
            services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)

    def test_renovacao_nao_muda_status_mas_registra_movimentacao(self):
        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)
        self.ativo.refresh_from_db()

        services.renovar(self.ativo, usuario=None, novo_prazo_dias=15)
        self.ativo.refresh_from_db()

        self.assertEqual(self.ativo.status, StatusAtivo.EMPRESTADO.value)
        self.assertEqual(
            Movimentacao.objects.filter(ativo=self.ativo, tipo="renovacao").count(), 1
        )


class FluxoManutencaoTest(BaseComTenant):
    def test_enviar_e_retornar_manutencao(self):
        services.enviar_manutencao(self.ativo, usuario=None, motivo="Troca de roda")
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.MANUTENCAO.value)

        services.retornar_manutencao(self.ativo, usuario=None)
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.DISPONIVEL.value)

        manutencao = Movimentacao.objects.get(ativo=self.ativo, tipo="manutencao")
        self.assertIsNotNone(manutencao.detalhe_manutencao.data_conclusao)

    def test_manutencao_direta_para_baixa(self):
        services.enviar_manutencao(self.ativo, usuario=None, motivo="Sem reparo possível")
        self.ativo.refresh_from_db()

        services.dar_baixa(self.ativo, usuario=None, motivo="Estrutura irrecuperável")
        self.ativo.refresh_from_db()

        self.assertEqual(self.ativo.status, StatusAtivo.BAIXADO.value)

    def test_movimentacao_nunca_pode_ser_excluida(self):
        movimentacao = services.enviar_manutencao(self.ativo, usuario=None, motivo="Teste")
        with self.assertRaises(RuntimeError):
            movimentacao.delete()


class FluxoExtravioTest(BaseComTenant):
    def test_extravio_e_recuperacao(self):
        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)
        self.ativo.refresh_from_db()

        services.registrar_extravio(self.ativo, usuario=None)
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.EXTRAVIADO.value)

        services.registrar_recuperacao(self.ativo, usuario=None, observacoes="Encontrado no depósito")
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.DISPONIVEL.value)


class InativacaoTest(BaseComTenant):
    def test_inativar_e_reativar(self):
        services.inativar(self.ativo, usuario=None, motivo="Pausa administrativa")
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.INATIVO.value)

        services.reativar(self.ativo, usuario=None)
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.DISPONIVEL.value)

    def test_nao_pode_inativar_ativo_emprestado(self):
        from ativos.domain.exceptions import AcaoAdministrativaInvalidaError

        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)
        self.ativo.refresh_from_db()

        with self.assertRaises(AcaoAdministrativaInvalidaError):
            services.inativar(self.ativo, usuario=None)


class IsolamentoMultiTenantDeAtivosTest(BaseComTenant):
    def test_ativo_de_outro_tenant_nao_aparece_na_queryset_padrao(self):
        categoria_b = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant_b, nome="Cadeira de Rodas"
        )
        Ativo.objects.all_tenants().create(
            tenant=self.tenant_b, patrimonio="CAD-0001", categoria=categoria_b
        )

        # Mesmo patrimônio em tenants diferentes não colide (unique_together por tenant).
        self.assertEqual(Ativo.objects.all_tenants().filter(patrimonio="CAD-0001").count(), 2)

        # Mas, no contexto do tenant A, só o ativo do tenant A é visível.
        self.assertEqual(list(Ativo.objects.values_list("id", flat=True)), [self.ativo.id])

    def test_movimentacao_tambem_isolada_por_tenant(self):
        services.emprestar(self.ativo, self.beneficiario, usuario=None, prazo_dias=30)

        token = set_current_tenant_id(self.tenant_b.pk)
        self.addCleanup(reset_current_tenant_id, token)
        self.assertEqual(Movimentacao.objects.count(), 0)

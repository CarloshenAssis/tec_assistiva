"""
Testes de isolamento multi-tenant (RNF017/RNF018 — docs/ESPECIFICACAO_TECNICA.md,
docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3).

Critério de saída da Fase 0: nenhum destes testes pode falhar.
"""

from django.test import TestCase

from core.models import Fornecedor, Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id


class IsolamentoMultiTenantTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Prefeitura A", slug="prefeitura-a")
        self.tenant_b = Tenant.objects.create(nome="Prefeitura B", slug="prefeitura-b")

        self.unidade_a = Unidade.objects.all_tenants().create(
            tenant=self.tenant_a, nome="Centro"
        )
        self.unidade_b = Unidade.objects.all_tenants().create(
            tenant=self.tenant_b, nome="Centro"
        )

    def _com_tenant(self, tenant):
        token = set_current_tenant_id(tenant.pk if tenant else None)
        self.addCleanup(reset_current_tenant_id, token)

    def test_queryset_padrao_so_ve_o_proprio_tenant(self):
        self._com_tenant(self.tenant_a)
        nomes_visiveis = list(Unidade.objects.values_list("id", flat=True))
        self.assertEqual(nomes_visiveis, [self.unidade_a.id])

    def test_tenants_diferentes_podem_ter_mesmo_nome_de_unidade(self):
        # unique_together é (tenant, nome) — não deve haver conflito global.
        self.assertEqual(Unidade.objects.all_tenants().count(), 2)

    def test_sem_tenant_no_contexto_retorna_vazio_fail_closed(self):
        self._com_tenant(None)
        self.assertEqual(list(Unidade.objects.all()), [])

    def test_all_tenants_enxerga_tudo_intencionalmente(self):
        self._com_tenant(self.tenant_a)
        self.assertEqual(Unidade.objects.all_tenants().count(), 2)

    def test_isolamento_tambem_vale_para_fornecedor(self):
        Fornecedor.objects.all_tenants().create(tenant=self.tenant_a, nome="Ortopé Ltda")
        Fornecedor.objects.all_tenants().create(tenant=self.tenant_b, nome="Ortopé Ltda")

        self._com_tenant(self.tenant_b)
        fornecedores = Fornecedor.objects.all()
        self.assertEqual(fornecedores.count(), 1)
        self.assertEqual(fornecedores.first().tenant_id, self.tenant_b.pk)

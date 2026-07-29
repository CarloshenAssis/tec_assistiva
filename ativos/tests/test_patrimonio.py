"""
Geração de código patrimonial (docs/features/identificacao-patrimonial-e-unidades.md).

O usuário nunca é obrigado a gerar o QR Code nem o código manualmente — os
dois nascem junto com o ativo. Este arquivo cobre o código; o QR
(`qr_token`) já é gerado por `default=gerar_qr_token` no model, desde antes
desta spec.
"""

from django.test import TestCase
from django.urls import reverse

from ativos.models import Ativo, CategoriaAtivo
from ativos.patrimonio import gerar_codigo_patrimonial
from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"


class GerarCodigoPatrimonialTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Patrimonio", slug="pref-patrim")

    def test_usa_prefixo_cadastrado_na_categoria(self):
        categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.assertEqual("CAD-000001", gerar_codigo_patrimonial(categoria))

    def test_deriva_prefixo_do_nome_quando_nao_cadastrado(self):
        categoria = CategoriaAtivo.objects.all_tenants().create(tenant=self.tenant, nome="Muletas")
        self.assertEqual("MUL-000001", gerar_codigo_patrimonial(categoria))

    def test_incrementa_a_partir_do_maior_numero_existente(self):
        categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Andador", prefixo="AND"
        )
        Ativo.objects.all_tenants().create(tenant=self.tenant, categoria=categoria, patrimonio="AND-000001")
        Ativo.objects.all_tenants().create(tenant=self.tenant, categoria=categoria, patrimonio="AND-000005")
        self.assertEqual("AND-000006", gerar_codigo_patrimonial(categoria))

    def test_reaproveita_numero_apos_exclusao_do_ultimo_ativo(self):
        """
        Não há fluxo de exclusão de ativo na aplicação (só baixa/status) — a
        função olha o MAIOR número entre os ativos EXISTENTES, não um
        contador persistente. Se o último ativo da sequência for excluído
        manualmente (ex.: via Django Admin), o próximo cadastro pode gerar o
        mesmo número de novo. Isso é aceitável: o caso não ocorre no uso
        normal do produto, e um contador persistente seria complexidade
        desnecessária para uma exclusão que a UI nem oferece.
        """
        categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Muletas Excluir", prefixo="MUX"
        )
        Ativo.objects.all_tenants().create(tenant=self.tenant, categoria=categoria, patrimonio="MUX-000001")
        ativo_2 = Ativo.objects.all_tenants().create(
            tenant=self.tenant, categoria=categoria, patrimonio="MUX-000002"
        )
        ativo_2.delete()
        self.assertEqual("MUX-000002", gerar_codigo_patrimonial(categoria))

    def test_nao_mistura_sequencia_entre_categorias_diferentes(self):
        cadeira = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira Seq", prefixo="CAD"
        )
        muleta = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Muleta Seq", prefixo="MUL"
        )
        Ativo.objects.all_tenants().create(tenant=self.tenant, categoria=cadeira, patrimonio="CAD-000001")
        Ativo.objects.all_tenants().create(tenant=self.tenant, categoria=cadeira, patrimonio="CAD-000002")
        self.assertEqual("MUL-000001", gerar_codigo_patrimonial(muleta))

    def test_codigo_personalizado_de_outra_categoria_nao_atrapalha_a_sequencia(self):
        """Um código digitado manualmente com prefixo diferente não conta na sequência automática."""
        categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira Custom", prefixo="CAD"
        )
        Ativo.objects.all_tenants().create(tenant=self.tenant, categoria=categoria, patrimonio="PMSJC-2548")
        self.assertEqual("CAD-000001", gerar_codigo_patrimonial(categoria))


class CriarAtivoComCodigoAutomaticoTest(TestCase):
    """A view real: deixar o campo em branco gera o código; digitar um valida unicidade."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Ativo Patrim", slug="pref-ativo-patrim")
        self.gestor = Usuario.objects.create_user(
            username="gestor_patrim",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )

    def test_deixar_patrimonio_em_branco_gera_o_codigo(self):
        self.client.login(username="gestor_patrim", password=SENHA)
        self.client.post(
            reverse("app:ativos:criar"),
            {"patrimonio": "", "categoria": self.categoria.pk},
        )
        ativo = Ativo.objects.all_tenants().filter(tenant=self.tenant, categoria=self.categoria).first()
        self.assertIsNotNone(ativo)
        self.assertEqual("CAD-000001", ativo.patrimonio)

    def test_codigo_personalizado_e_aceito(self):
        self.client.login(username="gestor_patrim", password=SENHA)
        self.client.post(
            reverse("app:ativos:criar"),
            {"patrimonio": "PMSJC-2548", "categoria": self.categoria.pk},
        )
        self.assertTrue(
            Ativo.objects.all_tenants().filter(tenant=self.tenant, patrimonio="PMSJC-2548").exists()
        )

    def test_codigo_personalizado_duplicado_e_erro_de_formulario_nao_500(self):
        Ativo.objects.all_tenants().create(
            tenant=self.tenant, categoria=self.categoria, patrimonio="PMSJC-9999"
        )
        self.client.login(username="gestor_patrim", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:criar"),
            {"patrimonio": "PMSJC-9999", "categoria": self.categoria.pk},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertEqual(
            1,
            Ativo.objects.all_tenants().filter(tenant=self.tenant, patrimonio="PMSJC-9999").count(),
        )

    def test_cada_ativo_cadastrado_sem_codigo_recebe_o_proximo_numero(self):
        self.client.login(username="gestor_patrim", password=SENHA)
        self.client.post(
            reverse("app:ativos:criar"), {"patrimonio": "", "categoria": self.categoria.pk}
        )
        self.client.post(
            reverse("app:ativos:criar"), {"patrimonio": "", "categoria": self.categoria.pk}
        )
        codigos = set(
            Ativo.objects.all_tenants()
            .filter(tenant=self.tenant, categoria=self.categoria)
            .values_list("patrimonio", flat=True)
        )
        self.assertEqual({"CAD-000001", "CAD-000002"}, codigos)

"""
Checklist de check-in/devolução visível na ficha do ativo, com quem marcou.

O cenário que motivou isto: um funcionário confirma "boas condições" no
check-in ou devolução, mas na prática o ativo não estava — e depois é
preciso ver, para aquele ativo específico, quem marcou o quê e quando.
`Movimentacao.usuario`/`data_hora` já existiam; o que faltava era decodificar
o checklist salvo em `dados_especificos` para algo legível na tela.
"""

from django.test import TestCase
from django.urls import reverse

from ativos import services
from ativos.domain.enums import StatusAtivo
from ativos.models import Ativo, CategoriaAtivo
from ativos.selectors import checklist_detalhado
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade

SENHA = "senha-bem-longa-2026"


class ChecklistDetalhadoTest(TestCase):
    """Seletor puro — traduz o JSON bruto para rótulo + marcado."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Checklist", slug="pref-checklist")
        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas"
        )
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant,
            patrimonio="CAD-CHK-01",
            categoria=self.categoria,
            unidade=self.unidade,
        )
        self.beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Maria Silva", cpf="123.456.789-09"
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_checklist",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_item_marcado_aparece_como_marcado(self):
        movimentacao = services.emprestar(
            self.ativo,
            self.beneficiario,
            usuario=self.funcionario,
            prazo_dias=30,
            checklist={"rodas": True, "freios": False},
        )
        itens = checklist_detalhado(movimentacao)
        rodas = next(i for i in itens if i["rotulo"] == "Rodas boas")
        freios = next(i for i in itens if i["rotulo"] == "Freios funcionando")
        self.assertTrue(rodas["marcado"])
        self.assertFalse(freios["marcado"])

    def test_item_ausente_do_checklist_conta_como_nao_marcado(self):
        """Um item que o funcionário simplesmente não marcou não pode virar 'confirmado'."""
        movimentacao = services.emprestar(
            self.ativo, self.beneficiario, usuario=self.funcionario, prazo_dias=30, checklist={}
        )
        itens = checklist_detalhado(movimentacao)
        self.assertTrue(all(not item["marcado"] for item in itens))

    def test_movimentacao_sem_checklist_devolve_lista_vazia(self):
        movimentacao = services.enviar_manutencao(self.ativo, self.funcionario, motivo="Roda quebrada")
        self.assertEqual([], checklist_detalhado(movimentacao))

    def test_usa_o_catalogo_certo_por_tipo_de_movimentacao(self):
        """Empréstimo e devolução têm checklists diferentes — não pode misturar rótulos."""
        emprestimo = services.emprestar(
            self.ativo,
            self.beneficiario,
            usuario=self.funcionario,
            prazo_dias=30,
            checklist={"higienizado": True},
        )
        devolucao = services.devolver(
            self.ativo,
            usuario=self.funcionario,
            destino=StatusAtivo.DISPONIVEL,
            checklist={"limpa": True},
        )
        rotulos_emprestimo = {i["rotulo"] for i in checklist_detalhado(emprestimo)}
        rotulos_devolucao = {i["rotulo"] for i in checklist_detalhado(devolucao)}
        self.assertIn("Higienizado", rotulos_emprestimo)
        self.assertNotIn("Limpa", rotulos_emprestimo)
        self.assertIn("Limpa", rotulos_devolucao)
        self.assertNotIn("Higienizado", rotulos_devolucao)


class TimelineDaFichaMostraQuemFezOCheckinTest(TestCase):
    """A tela real que o Admin/Gestor usa para investigar um check-in questionável."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Timeline", slug="pref-timeline-chk")
        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas"
        )
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant,
            patrimonio="CAD-CHK-02",
            categoria=self.categoria,
            unidade=self.unidade,
        )
        self.beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="João Pedro", cpf="234.567.891-73"
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_timeline_chk",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.funcionario = Usuario.objects.create_user(
            username="func_timeline_chk",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        # Gestor só enxerga ativo de unidade atribuída a ele
        # (docs/business-rules/unidades.md) — sem isto, a ficha responde 404.
        self.gestor.unidades.add(self.unidade)
        services.emprestar(
            self.ativo,
            self.beneficiario,
            usuario=self.funcionario,
            prazo_dias=30,
            checklist={"rodas": True, "freios": False},
        )

    def test_timeline_mostra_o_nome_de_quem_fez_o_checkin(self):
        self.client.login(username="gestor_timeline_chk", password=SENHA)
        resposta = self.client.get(
            reverse("app:ativos:ficha", args=[self.ativo.pk]), {"aba": "movimentacoes"}
        )
        self.assertContains(resposta, "func_timeline_chk")

    def test_timeline_mostra_o_item_marcado_como_bom(self):
        self.client.login(username="gestor_timeline_chk", password=SENHA)
        resposta = self.client.get(
            reverse("app:ativos:ficha", args=[self.ativo.pk]), {"aba": "movimentacoes"}
        )
        self.assertContains(resposta, "Rodas boas")

    def test_timeline_distingue_visualmente_marcado_de_nao_marcado(self):
        """
        O ponto central do pedido: dá pra ver, olhando a tela, o que foi
        confirmado como OK e o que não foi — não é uma lista plana sem
        diferenciação.
        """
        self.client.login(username="gestor_timeline_chk", password=SENHA)
        resposta = self.client.get(
            reverse("app:ativos:ficha", args=[self.ativo.pk]), {"aba": "movimentacoes"}
        )
        corpo = resposta.content.decode()
        self.assertIn("✓", corpo)
        self.assertIn("✗", corpo)

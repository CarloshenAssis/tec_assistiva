"""
Escopo por unidade aplicado de fato nas telas (docs/business-rules/unidades.md).

Antes disto, `unidades_visiveis()` existia e era testado, mas nenhuma view o
usava: um Gestor de uma unidade via os ativos de todas. Estes testes fecham
esse buraco pela porta que o usuário realmente usa (HTTP), não só pela função.
"""

from django.test import TestCase
from django.urls import reverse

from ativos.models import Ativo, CategoriaAtivo
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade

SENHA = "senha-bem-longa-2026"


class BaseDuasUnidades(TestCase):
    """Um tenant, duas unidades, um ativo em cada."""

    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Escopo", slug="pref-escopo")
        self.norte = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Posto Norte")
        self.sul = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Posto Sul")

        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.ativo_norte = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-NORTE", categoria=self.categoria, unidade=self.norte
        )
        self.ativo_sul = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-SUL", categoria=self.categoria, unidade=self.sul
        )

        self.gestor_norte = Usuario.objects.create_user(
            username="gestor_norte",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.gestor_norte.unidades.add(self.norte)

        self.admin = Usuario.objects.create_user(
            username="admin_escopo",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="admin"),
        )

    def logar(self, username):
        self.assertTrue(self.client.login(username=username, password=SENHA))


class ListagemDeAtivosPorUnidadeTest(BaseDuasUnidades):
    def test_gestor_ve_apenas_ativo_da_unidade_atribuida(self):
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:ativos:lista"))
        self.assertContains(resposta, "CAD-NORTE")
        self.assertNotContains(resposta, "CAD-SUL")

    def test_admin_ve_ativos_de_todas_as_unidades(self):
        """Admin nunca é restrito por unidade, mesmo sem nenhuma atribuída a ele."""
        self.logar("admin_escopo")
        resposta = self.client.get(reverse("app:ativos:lista"))
        self.assertContains(resposta, "CAD-NORTE")
        self.assertContains(resposta, "CAD-SUL")

    def test_resumo_por_categoria_tambem_respeita_o_escopo(self):
        """
        Os cartões de contagem no topo da lista não podem revelar o acervo das
        outras unidades — seria um vazamento pela agregação, com a lista
        detalhada corretamente filtrada logo abaixo.
        """
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:ativos:lista"))
        resumo = resposta.context["resumo_categorias"]
        self.assertEqual(1, resumo[0]["total"])


class FichaEQrCodePorUnidadeTest(BaseDuasUnidades):
    def test_ficha_de_ativo_de_outra_unidade_devolve_404(self):
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:ativos:ficha", args=[self.ativo_sul.pk]))
        self.assertEqual(404, resposta.status_code)

    def test_ficha_da_propria_unidade_abre(self):
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:ativos:ficha", args=[self.ativo_norte.pk]))
        self.assertEqual(200, resposta.status_code)

    def test_qr_code_de_ativo_de_outra_unidade_nao_e_resolvido(self):
        """
        A etiqueta física de outra unidade pode chegar às mãos de qualquer um —
        a resposta é a mesma de "não existe", sem confirmar que o ativo é real.
        """
        self.logar("gestor_norte")
        resposta = self.client.get(
            reverse("app:ativos:resolver_qr", args=[self.ativo_sul.qr_token])
        )
        self.assertEqual(404, resposta.status_code)

    def test_busca_manual_por_patrimonio_de_outra_unidade_nao_encontra(self):
        """Sem isto, o campo de digitação do scan seria uma porta lateral ao escopo."""
        self.logar("gestor_norte")
        resposta = self.client.post(
            reverse("app:ativos:scan"), {"codigo": "CAD-SUL"}, follow=True
        )
        self.assertContains(resposta, "Nenhum ativo encontrado")

    def test_admin_resolve_qr_de_qualquer_unidade(self):
        self.logar("admin_escopo")
        resposta = self.client.get(
            reverse("app:ativos:resolver_qr", args=[self.ativo_sul.qr_token])
        )
        self.assertEqual(200, resposta.status_code)


class AcoesRespeitamOEscopoTest(BaseDuasUnidades):
    def test_nao_executa_acao_em_ativo_de_outra_unidade(self):
        self.logar("gestor_norte")
        resposta = self.client.post(
            reverse("app:ativos:executar_acao", args=[self.ativo_sul.pk, "reservar"])
        )
        self.assertEqual(404, resposta.status_code)
        self.ativo_sul.refresh_from_db()
        self.assertEqual("disponivel", self.ativo_sul.status)

    def test_edicao_de_ativo_de_outra_unidade_devolve_404(self):
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:ativos:editar", args=[self.ativo_sul.pk]))
        self.assertEqual(404, resposta.status_code)


class WizardEDevolucaoRespeitamOEscopoTest(BaseDuasUnidades):
    def test_wizard_nao_oferece_ativo_de_outra_unidade(self):
        beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Maria Silva", cpf="123.456.789-09", unidade=self.norte
        )
        self.logar("gestor_norte")
        sessao = self.client.session
        sessao["wizard_emprestimo"] = {"beneficiario_id": beneficiario.pk}
        sessao.save()

        resposta = self.client.get(reverse("app:ativos:wizard_emprestimo"), {"q": "CAD"})
        self.assertContains(resposta, "CAD-NORTE")
        self.assertNotContains(resposta, "CAD-SUL")


class CadastroExigeUnidadeTest(BaseDuasUnidades):
    def test_gestor_so_pode_escolher_unidade_que_opera(self):
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:ativos:criar"))
        opcoes = list(resposta.context["form"].fields["unidade"].queryset)
        self.assertEqual([self.norte], opcoes)

    def test_cadastro_sem_unidade_e_erro_de_formulario(self):
        """Unidade é obrigatória: o POST sem ela não pode gravar um ativo órfão."""
        self.logar("gestor_norte")
        resposta = self.client.post(
            reverse("app:ativos:criar"), {"patrimonio": "", "categoria": self.categoria.pk}
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("unidade", resposta.context["form"].errors)
        self.assertEqual(2, Ativo.objects.all_tenants().filter(tenant=self.tenant).count())

    def test_nao_aceita_unidade_de_fora_do_escopo_do_usuario(self):
        """Mesmo forjando o POST, o Gestor não cadastra ativo na unidade alheia."""
        self.logar("gestor_norte")
        resposta = self.client.post(
            reverse("app:ativos:criar"),
            {"patrimonio": "CAD-FORJADO", "categoria": self.categoria.pk, "unidade": self.sul.pk},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertFalse(
            Ativo.objects.all_tenants().filter(patrimonio="CAD-FORJADO").exists()
        )


class SemUnidadeAtribuidaTest(BaseDuasUnidades):
    """
    Gestor sem unidade nenhuma: fail-closed é o comportamento certo, mas a tela
    tem de dizer que é falta de permissão, não falta de cadastro.
    """

    def setUp(self):
        super().setUp()
        self.orfao = Usuario.objects.create_user(
            username="gestor_orfao",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )

    def test_lista_vazia_explica_o_motivo(self):
        self.logar("gestor_orfao")
        resposta = self.client.get(reverse("app:ativos:lista"))
        self.assertNotContains(resposta, "CAD-NORTE")
        self.assertContains(resposta, "Nenhuma unidade atribuída")

    def test_cadastro_orienta_em_vez_de_mostrar_formulario_inutil(self):
        self.logar("gestor_orfao")
        resposta = self.client.get(reverse("app:ativos:criar"))
        self.assertContains(resposta, "É preciso ter uma unidade")
        self.assertNotIn("form", resposta.context)


class BeneficiarioPorUnidadeTest(BaseDuasUnidades):
    def setUp(self):
        super().setUp()
        self.do_norte = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Ana do Norte", cpf="123.456.789-09", unidade=self.norte
        )
        self.do_sul = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Bruno do Sul", cpf="234.567.891-73", unidade=self.sul
        )
        self.sem_unidade = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Carla Sem Unidade", cpf="345.678.912-38"
        )

    def test_gestor_ve_titular_da_sua_unidade_e_os_sem_unidade(self):
        """
        Titular sem unidade é da organização toda (ver o comentário no campo
        `Beneficiario.unidade`) — some da lista seria perder acesso a cadastro
        legítimo, não proteger dado.
        """
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:beneficiarios:lista"))
        self.assertContains(resposta, "Ana do Norte")
        self.assertContains(resposta, "Carla Sem Unidade")
        self.assertNotContains(resposta, "Bruno do Sul")

    def test_ficha_de_titular_de_outra_unidade_devolve_404(self):
        self.logar("gestor_norte")
        resposta = self.client.get(
            reverse("app:beneficiarios:ficha", args=[self.do_sul.pk])
        )
        self.assertEqual(404, resposta.status_code)


class DashboardPorUnidadeTest(BaseDuasUnidades):
    def test_admin_ve_quebra_por_unidade(self):
        self.logar("admin_escopo")
        resposta = self.client.get(reverse("app:dashboard"))
        nomes = [linha["nome"] for linha in resposta.context["por_unidade"]]
        self.assertIn("Posto Norte", nomes)
        self.assertIn("Posto Sul", nomes)

    def test_contagens_do_dashboard_respeitam_o_escopo_do_gestor(self):
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertEqual(1, resposta.context["total_ativos"])

    def test_gestor_de_unidade_unica_nao_ve_a_tabela_por_unidade(self):
        """Seria uma tabela de uma linha repetindo os cartões acima."""
        self.logar("gestor_norte")
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertEqual([], resposta.context["por_unidade"])

"""
Centro de Etiquetas (docs/business-rules/etiquetas.md).
"""

from django.test import TestCase
from django.urls import reverse

from ativos import services
from ativos.etiquetas import montar_etiquetas
from ativos.models import Ativo, CategoriaAtivo, ImpressaoEtiqueta, LayoutEtiqueta
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id

SENHA = "senha-bem-longa-2026"


class BaseEtiquetas(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Etiqueta", slug="pref-etiq")
        token = set_current_tenant_id(self.tenant.pk)
        self.addCleanup(reset_current_tenant_id, token)

        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.cadeiras = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.muletas = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Muletas", prefixo="MUL"
        )
        self.cadeira = self._criar("CAD-0001", self.cadeiras)
        self.muleta = self._criar("MUL-0001", self.muletas)

        self.funcionario = Usuario.objects.create_user(
            username="func_etiq",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.funcionario.unidades.add(self.unidade)

    def _criar(self, patrimonio, categoria=None):
        return Ativo.objects.all_tenants().create(
            tenant=self.tenant,
            patrimonio=patrimonio,
            categoria=categoria or self.cadeiras,
            unidade=self.unidade,
        )

    def logar(self):
        self.assertTrue(self.client.login(username="func_etiq", password=SENHA))


class MontarEtiquetasTest(BaseEtiquetas):
    """
    Conteúdo da etiqueta — testável sem cliente HTTP.

    Todo tamanho mostra o mesmo conteúdo (QR, patrimônio, categoria, nome e
    logotipo da instituição): só a escala física muda entre Pequeno/Médio/
    Grande, não o que a etiqueta carrega (docs/business-rules/etiquetas.md).
    """

    def test_qr_vai_embutido_como_data_uri(self):
        """
        Folha autocontida: 60 etiquetas não podem gerar 60 requisições no
        momento da impressão, sob risco de sair etiqueta sem QR.
        """
        etiquetas = montar_etiquetas(
            [self.cadeira],
            url_de=lambda ativo: f"https://exemplo.test/qr/{ativo.qr_token}/",
            tenant=self.tenant,
            layout=LayoutEtiqueta.MEDIO,
        )
        self.assertTrue(etiquetas[0]["qr"].startswith("data:image/png;base64,"))

    def test_todo_tamanho_mostra_categoria_e_instituicao(self):
        for layout in LayoutEtiqueta.values:
            with self.subTest(layout=layout):
                etiqueta = montar_etiquetas(
                    [self.cadeira],
                    url_de=lambda ativo: "https://exemplo.test/",
                    tenant=self.tenant,
                    layout=layout,
                )[0]
                self.assertEqual("CAD-0001", etiqueta["patrimonio"])
                self.assertEqual("Cadeira de Rodas", etiqueta["categoria"])
                self.assertEqual("Prefeitura Etiqueta", etiqueta["instituicao"])

    def test_sem_logotipo_configurado_etiqueta_fica_sem_logo(self):
        etiqueta = montar_etiquetas(
            [self.cadeira],
            url_de=lambda ativo: "https://exemplo.test/",
            tenant=self.tenant,
            layout=LayoutEtiqueta.MEDIO,
        )[0]
        self.assertEqual("", etiqueta["logo"])


class FilaDeImpressaoTest(BaseEtiquetas):
    def test_ativo_novo_entra_na_fila_de_impressao(self):
        self.logar()
        resposta = self.client.get(reverse("app:ativos:etiquetas_centro"))
        self.assertEqual(2, resposta.context["total_na_fila"])

    def test_filtro_de_fila_mostra_so_quem_nunca_foi_impresso(self):
        services.registrar_impressao_etiquetas(
            [self.cadeira], usuario=self.funcionario, layout=LayoutEtiqueta.MEDIO
        )
        self.logar()
        resposta = self.client.get(
            reverse("app:ativos:etiquetas_centro"), {"somente_sem_etiqueta": "on"}
        )
        patrimonios = [a.patrimonio for a in resposta.context["ativos"]]
        self.assertEqual(["MUL-0001"], patrimonios)

    def test_ativo_baixado_fica_fora_da_fila(self):
        """Etiqueta nova para item fora do patrimônio só confundiria o inventário."""
        services.dar_baixa(self.muleta, usuario=None, motivo="Sem reparo")
        self.logar()
        resposta = self.client.get(reverse("app:ativos:etiquetas_centro"))
        self.assertEqual(1, resposta.context["total_na_fila"])
        self.assertNotContains(resposta, "MUL-0001")


class FiltrosDoCentroTest(BaseEtiquetas):
    def test_filtra_por_categoria(self):
        self.logar()
        resposta = self.client.get(
            reverse("app:ativos:etiquetas_centro"), {"categoria": self.cadeiras.pk}
        )
        patrimonios = [a.patrimonio for a in resposta.context["ativos"]]
        self.assertEqual(["CAD-0001"], patrimonios)

    def test_filtra_por_status(self):
        services.enviar_manutencao(self.muleta, usuario=None, motivo="Ponteira gasta")
        self.logar()
        resposta = self.client.get(
            reverse("app:ativos:etiquetas_centro"), {"status": "manutencao"}
        )
        patrimonios = [a.patrimonio for a in resposta.context["ativos"]]
        self.assertEqual(["MUL-0001"], patrimonios)

    def test_ativo_vindo_da_ficha_chega_pre_selecionado(self):
        self.logar()
        resposta = self.client.get(
            reverse("app:ativos:etiquetas_centro"), {"ativo": self.cadeira.pk}
        )
        self.assertEqual(self.cadeira.pk, resposta.context["ativo_pre_selecionado"])


class GerarFolhaTest(BaseEtiquetas):
    def test_gera_folha_em_lote_e_registra_o_historico(self):
        self.logar()
        resposta = self.client.post(
            reverse("app:ativos:etiquetas_folha"),
            {"ativos": [self.cadeira.pk, self.muleta.pk], "layout": LayoutEtiqueta.MEDIO},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertContains(resposta, "CAD-0001")
        self.assertContains(resposta, "MUL-0001")
        self.assertEqual(2, ImpressaoEtiqueta.objects.count())

    def test_etiquetas_do_mesmo_lote_compartilham_o_identificador(self):
        """Permite mostrar "40 etiquetas em 12/03" em vez de 40 linhas soltas."""
        self.logar()
        self.client.post(
            reverse("app:ativos:etiquetas_folha"),
            {"ativos": [self.cadeira.pk, self.muleta.pk], "layout": LayoutEtiqueta.GRANDE},
        )
        lotes = set(ImpressaoEtiqueta.objects.values_list("lote", flat=True))
        self.assertEqual(1, len(lotes))

    def test_reimpressao_soma_no_contador_e_nao_substitui(self):
        self.logar()
        for _ in range(3):
            self.client.post(
                reverse("app:ativos:etiquetas_folha"),
                {"ativos": [self.cadeira.pk], "layout": LayoutEtiqueta.MEDIO},
            )
        self.cadeira.refresh_from_db()
        self.assertEqual(3, self.cadeira.total_impressoes)
        self.assertIsNotNone(self.cadeira.ultima_impressao)

    def test_get_nao_gera_folha_nem_registra_impressao(self):
        """
        Um GET tornaria o registro acionável por pré-visualização de link,
        inflando o histórico com impressões que nunca aconteceram.
        """
        self.logar()
        resposta = self.client.get(reverse("app:ativos:etiquetas_folha"))
        self.assertEqual(403, resposta.status_code)
        self.assertEqual(0, ImpressaoEtiqueta.objects.count())

    def test_sem_selecionar_nada_avisa_em_vez_de_gerar_folha_vazia(self):
        self.logar()
        resposta = self.client.post(
            reverse("app:ativos:etiquetas_folha"), {"layout": LayoutEtiqueta.MEDIO}, follow=True
        )
        self.assertContains(resposta, "Selecione ao menos um ativo")
        self.assertEqual(0, ImpressaoEtiqueta.objects.count())

    def test_layout_forjado_e_recusado(self):
        self.logar()
        resposta = self.client.post(
            reverse("app:ativos:etiquetas_folha"),
            {"ativos": [self.cadeira.pk], "layout": "gigante"},
            follow=True,
        )
        self.assertContains(resposta, "Tamanho de etiqueta inválido")
        self.assertEqual(0, ImpressaoEtiqueta.objects.count())

    def test_nao_imprime_etiqueta_de_ativo_baixado(self):
        services.dar_baixa(self.muleta, usuario=None, motivo="Sem reparo")
        self.logar()
        resposta = self.client.post(
            reverse("app:ativos:etiquetas_folha"),
            {"ativos": [self.muleta.pk], "layout": LayoutEtiqueta.MEDIO},
            follow=True,
        )
        self.assertContains(resposta, "Selecione ao menos um ativo")
        self.assertEqual(0, ImpressaoEtiqueta.objects.count())


class EscopoDeUnidadeNasEtiquetasTest(BaseEtiquetas):
    """O Centro de Etiquetas não pode ser porta lateral ao escopo de unidade."""

    def setUp(self):
        super().setUp()
        self.outra = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Filial")
        self.alheio = Ativo.objects.all_tenants().create(
            tenant=self.tenant,
            patrimonio="CAD-ALHEIO",
            categoria=self.cadeiras,
            unidade=self.outra,
        )

    def test_ativo_de_outra_unidade_nao_aparece_no_centro(self):
        self.logar()
        resposta = self.client.get(reverse("app:ativos:etiquetas_centro"))
        self.assertNotContains(resposta, "CAD-ALHEIO")

    def test_nao_gera_etiqueta_de_ativo_de_outra_unidade_nem_forjando_o_post(self):
        self.logar()
        resposta = self.client.post(
            reverse("app:ativos:etiquetas_folha"),
            {"ativos": [self.alheio.pk], "layout": LayoutEtiqueta.MEDIO},
            follow=True,
        )
        self.assertContains(resposta, "Selecione ao menos um ativo")
        self.assertEqual(0, ImpressaoEtiqueta.objects.count())


class HistoricoDeImpressaoTest(BaseEtiquetas):
    def test_historico_agrupa_por_lote_e_mostra_quem_imprimiu(self):
        self.logar()
        self.client.post(
            reverse("app:ativos:etiquetas_folha"),
            {"ativos": [self.cadeira.pk, self.muleta.pk], "layout": LayoutEtiqueta.MEDIO},
        )
        resposta = self.client.get(reverse("app:ativos:etiquetas_historico"))
        lotes = resposta.context["lotes"]
        self.assertEqual(1, len(lotes))
        self.assertEqual(2, len(lotes[0]["ativos"]))
        self.assertContains(resposta, "func_etiq")

    def test_registro_de_impressao_nao_pode_ser_excluido(self):
        """Histórico é imutável, como Movimentacao (docs/business-rules/etiquetas.md)."""
        services.registrar_impressao_etiquetas(
            [self.cadeira], usuario=self.funcionario, layout=LayoutEtiqueta.MEDIO
        )
        registro = ImpressaoEtiqueta.objects.first()
        with self.assertRaises(RuntimeError):
            registro.delete()


class FichaMostraDadosDaEtiquetaTest(BaseEtiquetas):
    def test_aba_qrcode_mostra_ultima_impressao_e_contador(self):
        services.registrar_impressao_etiquetas(
            [self.cadeira], usuario=self.funcionario, layout=LayoutEtiqueta.GRANDE
        )
        self.logar()
        resposta = self.client.get(
            reverse("app:ativos:ficha", args=[self.cadeira.pk]), {"aba": "qrcode"}
        )
        self.assertEqual(1, resposta.context["total_impressoes"])
        self.assertIsNotNone(resposta.context["ultima_impressao"])
        self.assertContains(resposta, "Reimprimir etiqueta")

    def test_ativo_nunca_impresso_mostra_que_esta_na_fila(self):
        self.logar()
        resposta = self.client.get(
            reverse("app:ativos:ficha", args=[self.cadeira.pk]), {"aba": "qrcode"}
        )
        self.assertContains(resposta, "Nunca impressa")
        self.assertContains(resposta, "Imprimir etiqueta")

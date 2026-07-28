from django.test import SimpleTestCase

from ativos.domain.acoes import NIVEL_ADMIN, NIVEL_FUNCIONARIO, NIVEL_GESTOR, acoes_disponiveis
from ativos.domain.enums import StatusAtivo

S = StatusAtivo


class AcoesDisponiveisTest(SimpleTestCase):
    def test_disponivel_sem_filtro_de_papel_inclui_emprestar(self):
        codigos = [a.codigo for a in acoes_disponiveis(S.DISPONIVEL)]
        self.assertIn("emprestar", codigos)
        self.assertNotIn("receber_devolucao", codigos)

    def test_emprestado_nunca_oferece_emprestar_de_novo(self):
        codigos = [a.codigo for a in acoes_disponiveis(S.EMPRESTADO)]
        self.assertNotIn("emprestar", codigos)
        self.assertIn("receber_devolucao", codigos)
        self.assertIn("renovar", codigos)

    def test_manutencao_nunca_oferece_emprestar_nem_devolver(self):
        codigos = [a.codigo for a in acoes_disponiveis(S.MANUTENCAO)]
        self.assertNotIn("emprestar", codigos)
        self.assertNotIn("receber_devolucao", codigos)
        self.assertIn("finalizar_manutencao", codigos)

    def test_baixado_e_somente_consulta(self):
        codigos = {a.codigo for a in acoes_disponiveis(S.BAIXADO)}
        self.assertEqual(codigos, {"ver_historico", "ver_fotos", "ver_timeline"})

    def test_funcionario_nao_ve_dar_baixa(self):
        codigos = [a.codigo for a in acoes_disponiveis(S.DISPONIVEL, nivel_hierarquico=NIVEL_FUNCIONARIO)]
        self.assertNotIn("dar_baixa", codigos)
        self.assertIn("emprestar", codigos)

    def test_gestor_ve_dar_baixa(self):
        codigos = [a.codigo for a in acoes_disponiveis(S.DISPONIVEL, nivel_hierarquico=NIVEL_GESTOR)]
        self.assertIn("dar_baixa", codigos)

    def test_apenas_admin_reativa(self):
        codigos_funcionario = [
            a.codigo for a in acoes_disponiveis(S.INATIVO, nivel_hierarquico=NIVEL_FUNCIONARIO)
        ]
        codigos_admin = [a.codigo for a in acoes_disponiveis(S.INATIVO, nivel_hierarquico=NIVEL_ADMIN)]
        self.assertNotIn("reativar", codigos_funcionario)
        self.assertIn("reativar", codigos_admin)

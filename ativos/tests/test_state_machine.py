"""
Testes da máquina de estados pura (sem banco de dados) — a peça de maior
risco de negócio do produto. Critério de saída da Fase 0
(docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §12): nenhum destes testes pode falhar.
"""

from django.test import SimpleTestCase

from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.domain.exceptions import DestinoObrigatorioError, TransicaoInvalidaError
from ativos.domain.state_machine import pode_inativar, pode_transicionar, transicionar

S = StatusAtivo
T = TipoMovimentacao


class TransicoesValidasTest(SimpleTestCase):
    def test_disponivel_para_emprestado(self):
        self.assertEqual(transicionar(S.DISPONIVEL, T.EMPRESTIMO), S.EMPRESTADO)

    def test_disponivel_para_reservado(self):
        self.assertEqual(transicionar(S.DISPONIVEL, T.RESERVA), S.RESERVADO)

    def test_reservado_para_emprestado(self):
        self.assertEqual(transicionar(S.RESERVADO, T.EMPRESTIMO), S.EMPRESTADO)

    def test_reservado_cancelamento_volta_disponivel(self):
        self.assertEqual(transicionar(S.RESERVADO, T.RESERVA), S.DISPONIVEL)

    def test_disponivel_para_manutencao(self):
        self.assertEqual(transicionar(S.DISPONIVEL, T.MANUTENCAO), S.MANUTENCAO)

    def test_renovacao_mantem_emprestado(self):
        self.assertEqual(transicionar(S.EMPRESTADO, T.RENOVACAO), S.EMPRESTADO)

    def test_devolucao_para_disponivel(self):
        self.assertEqual(transicionar(S.EMPRESTADO, T.DEVOLUCAO, destino=S.DISPONIVEL), S.DISPONIVEL)

    def test_devolucao_para_higienizacao(self):
        self.assertEqual(
            transicionar(S.EMPRESTADO, T.DEVOLUCAO, destino=S.HIGIENIZACAO), S.HIGIENIZACAO
        )

    def test_devolucao_para_manutencao(self):
        self.assertEqual(transicionar(S.EMPRESTADO, T.DEVOLUCAO, destino=S.MANUTENCAO), S.MANUTENCAO)

    def test_higienizacao_conclusao_para_disponivel(self):
        self.assertEqual(transicionar(S.HIGIENIZACAO, T.HIGIENIZACAO), S.DISPONIVEL)

    def test_manutencao_retorno_para_disponivel(self):
        self.assertEqual(transicionar(S.MANUTENCAO, T.RETORNO_MANUTENCAO), S.DISPONIVEL)

    def test_manutencao_para_baixado(self):
        self.assertEqual(transicionar(S.MANUTENCAO, T.BAIXA), S.BAIXADO)

    def test_disponivel_para_baixado(self):
        self.assertEqual(transicionar(S.DISPONIVEL, T.BAIXA), S.BAIXADO)

    def test_emprestado_para_extraviado(self):
        self.assertEqual(transicionar(S.EMPRESTADO, T.EXTRAVIO), S.EXTRAVIADO)

    def test_extraviado_recuperado_volta_disponivel(self):
        self.assertEqual(transicionar(S.EXTRAVIADO, T.TRANSFERENCIA), S.DISPONIVEL)


class TransicoesInvalidasTest(SimpleTestCase):
    def test_nao_permite_emprestar_ativo_ja_emprestado(self):
        with self.assertRaises(TransicaoInvalidaError):
            transicionar(S.EMPRESTADO, T.EMPRESTIMO)

    def test_nao_permite_emprestar_ativo_em_manutencao(self):
        with self.assertRaises(TransicaoInvalidaError):
            transicionar(S.MANUTENCAO, T.EMPRESTIMO)

    def test_nao_permite_devolver_ativo_disponivel(self):
        with self.assertRaises(TransicaoInvalidaError):
            transicionar(S.DISPONIVEL, T.DEVOLUCAO, destino=S.DISPONIVEL)

    def test_nao_permite_nenhuma_transicao_a_partir_de_baixado(self):
        for tipo in T:
            with self.assertRaises(TransicaoInvalidaError):
                transicionar(S.BAIXADO, tipo)

    def test_devolucao_sem_destino_exige_destino_explicito(self):
        with self.assertRaises(DestinoObrigatorioError):
            transicionar(S.EMPRESTADO, T.DEVOLUCAO)

    def test_devolucao_com_destino_invalido_falha(self):
        with self.assertRaises(TransicaoInvalidaError):
            transicionar(S.EMPRESTADO, T.DEVOLUCAO, destino=S.EXTRAVIADO)

    def test_pode_transicionar_nao_levanta_excecao(self):
        self.assertTrue(pode_transicionar(S.DISPONIVEL, T.EMPRESTIMO))
        self.assertFalse(pode_transicionar(S.EMPRESTADO, T.EMPRESTIMO))
        self.assertFalse(pode_transicionar(S.EMPRESTADO, T.DEVOLUCAO))  # sem destino


class InativacaoTest(SimpleTestCase):
    def test_pode_inativar_a_partir_de_disponivel_manutencao_reservado(self):
        self.assertTrue(pode_inativar(S.DISPONIVEL))
        self.assertTrue(pode_inativar(S.MANUTENCAO))
        self.assertTrue(pode_inativar(S.RESERVADO))

    def test_nao_pode_inativar_a_partir_de_emprestado_ou_baixado(self):
        self.assertFalse(pode_inativar(S.EMPRESTADO))
        self.assertFalse(pode_inativar(S.BAIXADO))

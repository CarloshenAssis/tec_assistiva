from datetime import date, timedelta

from django.test import SimpleTestCase

from ativos.domain.cores import CorOperacional, cor_operacional
from ativos.domain.enums import StatusAtivo

HOJE = date(2026, 7, 28)


class CorOperacionalTest(SimpleTestCase):
    def test_disponivel_e_azul(self):
        self.assertEqual(cor_operacional(StatusAtivo.DISPONIVEL, hoje=HOJE), CorOperacional.AZUL)

    def test_manutencao_e_amarelo(self):
        self.assertEqual(cor_operacional(StatusAtivo.MANUTENCAO, hoje=HOJE), CorOperacional.AMARELO)

    def test_baixado_extraviado_inativo_sao_cinza(self):
        for status in (StatusAtivo.BAIXADO, StatusAtivo.EXTRAVIADO, StatusAtivo.INATIVO):
            self.assertEqual(cor_operacional(status, hoje=HOJE), CorOperacional.CINZA)

    def test_emprestado_dentro_do_prazo_e_verde(self):
        data_prevista = HOJE + timedelta(days=20)
        self.assertEqual(
            cor_operacional(StatusAtivo.EMPRESTADO, data_prevista, hoje=HOJE), CorOperacional.VERDE
        )

    def test_emprestado_vencendo_em_7_dias_e_verde_claro(self):
        data_prevista = HOJE + timedelta(days=7)
        self.assertEqual(
            cor_operacional(StatusAtivo.EMPRESTADO, data_prevista, hoje=HOJE), CorOperacional.VERDE_CLARO
        )

    def test_emprestado_atrasado_1_dia_e_vermelho_claro(self):
        data_prevista = HOJE - timedelta(days=1)
        self.assertEqual(
            cor_operacional(StatusAtivo.EMPRESTADO, data_prevista, hoje=HOJE), CorOperacional.VERMELHO_CLARO
        )

    def test_emprestado_atrasado_15_dias_e_vermelho_medio(self):
        data_prevista = HOJE - timedelta(days=15)
        self.assertEqual(
            cor_operacional(StatusAtivo.EMPRESTADO, data_prevista, hoje=HOJE), CorOperacional.VERMELHO_MEDIO
        )

    def test_emprestado_atrasado_60_dias_e_vermelho_escuro(self):
        data_prevista = HOJE - timedelta(days=60)
        self.assertEqual(
            cor_operacional(StatusAtivo.EMPRESTADO, data_prevista, hoje=HOJE), CorOperacional.VERMELHO_ESCURO
        )

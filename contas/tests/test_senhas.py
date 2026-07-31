"""
Geração de senha temporária (contas/senhas.py).
"""

from django.test import SimpleTestCase

from contas.senhas import _AMBIGUOS, gerar_senha_temporaria


class GerarSenhaTemporariaTest(SimpleTestCase):
    def test_tamanho_e_16(self):
        self.assertEqual(16, len(gerar_senha_temporaria()))

    def test_nunca_contem_caracteres_ambiguos(self):
        # Caso real que motivou isto: conta criada, 3 tentativas de login
        # com a senha errada — o par mais provável de confundir ao copiar
        # à mão é exatamente um destes (0/O, 1/l/I).
        for _ in range(200):
            senha = gerar_senha_temporaria()
            for caractere in _AMBIGUOS:
                self.assertNotIn(caractere, senha)

    def test_senhas_sucessivas_sao_diferentes(self):
        senhas = {gerar_senha_temporaria() for _ in range(20)}
        self.assertEqual(20, len(senhas))

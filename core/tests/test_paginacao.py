"""
Paginação padrão das telas de lista (core/paginacao.py).
"""

from django.http import HttpRequest
from django.test import TestCase

from core.paginacao import TAMANHO_PADRAO, TAMANHOS_DISPONIVEIS, paginar


def _requisicao(**parametros_get):
    request = HttpRequest()
    request.GET = request.GET.copy()
    for chave, valor in parametros_get.items():
        request.GET[chave] = valor
    return request


class PaginarTest(TestCase):
    def setUp(self):
        self.itens = list(range(1, 231))  # 230 "registros"

    def test_sem_por_pagina_usa_o_padrao(self):
        pagina = paginar(_requisicao(), self.itens)
        self.assertEqual(TAMANHO_PADRAO, pagina.paginator.per_page)

    def test_por_pagina_valido_e_respeitado(self):
        for tamanho in TAMANHOS_DISPONIVEIS:
            pagina = paginar(_requisicao(por_pagina=str(tamanho)), self.itens)
            self.assertEqual(tamanho, pagina.paginator.per_page)

    def test_por_pagina_fora_da_lista_cai_no_padrao(self):
        # Sem isto, "?por_pagina=999999" viraria "traga o acervo inteiro".
        pagina = paginar(_requisicao(por_pagina="999999"), self.itens)
        self.assertEqual(TAMANHO_PADRAO, pagina.paginator.per_page)

    def test_por_pagina_nao_numerico_cai_no_padrao(self):
        pagina = paginar(_requisicao(por_pagina="abc"), self.itens)
        self.assertEqual(TAMANHO_PADRAO, pagina.paginator.per_page)

    def test_pagina_alem_do_fim_devolve_a_ultima(self):
        # Comportamento padrão do Paginator.get_page — confirmando que não
        # quebra com página inexistente (usuário editou a URL na mão).
        pagina = paginar(_requisicao(por_pagina="100", pagina="999"), self.itens)
        self.assertEqual(pagina.paginator.num_pages, pagina.number)

    def test_corta_de_verdade_no_tamanho_escolhido(self):
        pagina = paginar(_requisicao(por_pagina="10"), self.itens)
        self.assertEqual(10, len(pagina.object_list))
        self.assertEqual(list(range(1, 11)), list(pagina.object_list))

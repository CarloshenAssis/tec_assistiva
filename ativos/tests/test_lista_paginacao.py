"""
Paginação da lista de ativos (antes cortava em `[:200]` sem paginação
nenhuma — ver core/paginacao.py).
"""

from django.test import TestCase
from django.urls import reverse

from ativos.models import Ativo, CategoriaAtivo
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade

SENHA = "senha-bem-longa-2026"


class ListaAtivosPaginacaoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Pag Ativos", slug="pref-pag-ativos")
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Sede")
        self.categoria = CategoriaAtivo.objects.all_tenants().create(tenant=self.tenant, nome="Andador")
        for i in range(30):
            Ativo.objects.all_tenants().create(
                tenant=self.tenant, patrimonio=f"AND-{i:04d}", categoria=self.categoria, unidade=self.unidade
            )
        self.admin = Usuario.objects.create_user(
            username="admin_pag_ativos", password=SENHA, tenant=self.tenant, papel=Papel.objects.get(codigo="admin")
        )
        self.client.login(username="admin_pag_ativos", password=SENHA)

    def test_pagina_padrao_mostra_25(self):
        resposta = self.client.get(reverse("app:ativos:lista"))
        self.assertEqual(25, len(resposta.context["pagina"].object_list))
        self.assertEqual(2, resposta.context["pagina"].paginator.num_pages)

    def test_segunda_pagina_mostra_o_resto(self):
        resposta = self.client.get(reverse("app:ativos:lista"), {"pagina": 2})
        self.assertEqual(5, len(resposta.context["pagina"].object_list))

    def test_por_pagina_e_respeitado(self):
        resposta = self.client.get(reverse("app:ativos:lista"), {"por_pagina": 10})
        self.assertEqual(10, len(resposta.context["pagina"].object_list))
        self.assertEqual(3, resposta.context["pagina"].paginator.num_pages)

    def test_por_pagina_invalido_cai_no_padrao(self):
        resposta = self.client.get(reverse("app:ativos:lista"), {"por_pagina": 99999})
        self.assertEqual(25, len(resposta.context["pagina"].object_list))

"""
Captura automática de criação/alteração/exclusão via sinais do ORM.

O ponto central destes testes: a trilha não pode depender de nenhuma view
lembrar de chamar `registrar()` — criar/alterar/apagar qualquer model de
domínio precisa aparecer na auditoria só por ter passado pelo ORM.
"""

from django.test import TestCase

from auditoria.models import AcaoAuditada, RegistroAuditoria
from contas.models import Papel, Usuario
from core.models import Fornecedor, Tenant, Unidade


class CriacaoAutomaticaTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Rastreio", slug="pref-rastreio")

    def test_criar_registro_gera_evento_de_criacao(self):
        unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Posto Central")
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.CRIACAO,
                objeto_tipo="core.Unidade",
                objeto_id=str(unidade.pk),
            ).exists()
        )

    def test_evento_de_criacao_carrega_o_tenant(self):
        unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Posto Norte")
        registro = RegistroAuditoria.objects.get(
            acao=AcaoAuditada.CRIACAO, objeto_tipo="core.Unidade", objeto_id=str(unidade.pk)
        )
        self.assertEqual(self.tenant, registro.tenant)


class AlteracaoAutomaticaTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Alt", slug="pref-alt")
        self.unidade = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Original")

    def test_alterar_campo_gera_evento_de_alteracao(self):
        self.unidade.nome = "Renomeada"
        self.unidade.save()
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.ALTERACAO,
                objeto_tipo="core.Unidade",
                objeto_id=str(self.unidade.pk),
            ).exists()
        )

    def test_descricao_lista_os_campos_alterados_por_nome(self):
        self.unidade.nome = "Renomeada de Novo"
        self.unidade.save()
        registro = RegistroAuditoria.objects.get(
            acao=AcaoAuditada.ALTERACAO, objeto_tipo="core.Unidade", objeto_id=str(self.unidade.pk)
        )
        self.assertIn("nome", registro.descricao)

    def test_save_sem_mudanca_nao_gera_evento(self):
        """Um re-save idempotente não é uma "alteração" para fins de auditoria."""
        total_antes = RegistroAuditoria.objects.filter(acao=AcaoAuditada.ALTERACAO).count()
        self.unidade.save()
        total_depois = RegistroAuditoria.objects.filter(acao=AcaoAuditada.ALTERACAO).count()
        self.assertEqual(total_antes, total_depois)

    def test_nome_do_campo_aparece_mas_nao_o_valor_novo(self):
        """
        A diferença de auditoria não pode virar uma segunda cópia do dado —
        só o *nome* do campo que mudou entra na descrição, nunca o valor.
        """
        self.unidade.nome = "Segredo Que Nao Deve Vazar Para A Descricao"
        self.unidade.save()
        registro = RegistroAuditoria.objects.get(
            acao=AcaoAuditada.ALTERACAO, objeto_tipo="core.Unidade", objeto_id=str(self.unidade.pk)
        )
        self.assertNotIn("Segredo Que Nao Deve Vazar", registro.descricao)


class ExclusaoAutomaticaTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Excl", slug="pref-excl")

    def test_apagar_registro_gera_evento_de_exclusao(self):
        fornecedor = Fornecedor.objects.all_tenants().create(tenant=self.tenant, nome="Oficina X")
        pk = fornecedor.pk
        fornecedor.delete()
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.EXCLUSAO, objeto_tipo="core.Fornecedor", objeto_id=str(pk)
            ).exists()
        )


class EscopoDaAuditoriaAutomaticaTest(TestCase):
    def test_nao_audita_a_propria_tabela_de_auditoria(self):
        """Auditar a auditoria seria recursivo e sem propósito."""
        total_antes = RegistroAuditoria.objects.count()
        RegistroAuditoria.objects.create(acao=AcaoAuditada.LOGIN_SUCESSO)
        # A criação acima não deve, por si, gerar um SEGUNDO registro
        # "criacao" apontando pra ela mesma.
        total_depois = RegistroAuditoria.objects.filter(
            acao=AcaoAuditada.CRIACAO, objeto_tipo="auditoria.RegistroAuditoria"
        ).count()
        self.assertEqual(0, total_depois)
        self.assertEqual(total_antes + 1, RegistroAuditoria.objects.count())


class CriacaoDeUsuarioTest(TestCase):
    """
    O caso que a plataforma mais precisa rastrear: criação de conta.
    """

    def test_criar_usuario_e_auditado(self):
        tenant = Tenant.objects.create(nome="Prefeitura User", slug="pref-user")
        usuario = Usuario.objects.create_user(
            username="novo_gestor",
            password="senha-bem-longa-2026",
            tenant=tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=AcaoAuditada.CRIACAO,
                objeto_tipo="contas.Usuario",
                objeto_id=str(usuario.pk),
            ).exists()
        )

    def test_hash_de_senha_nunca_aparece_na_descricao_da_alteracao(self):
        tenant = Tenant.objects.create(nome="Prefeitura User2", slug="pref-user-2")
        usuario = Usuario.objects.create_user(
            username="outro_gestor",
            password="senha-bem-longa-2026",
            tenant=tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        usuario.set_password("nova-senha-bem-longa-2027")
        usuario.save()
        registro = RegistroAuditoria.objects.filter(
            acao=AcaoAuditada.ALTERACAO, objeto_tipo="contas.Usuario", objeto_id=str(usuario.pk)
        ).first()
        self.assertIsNotNone(registro)
        self.assertNotIn("nova-senha-bem-longa-2027", registro.descricao)
        self.assertNotIn("pbkdf2", registro.descricao)
        self.assertNotIn("argon2", registro.descricao)
        # O NOME do campo pode aparecer — é só o valor que não pode.
        self.assertIn("password", registro.descricao)

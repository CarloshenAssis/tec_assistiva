"""
Transferência entre unidades, extravio e correção de manutenção
(docs/business-rules/unidades.md e manutencao.md).
"""

from django.test import TestCase
from django.urls import reverse

from ativos import services
from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.domain.exceptions import (
    AcaoAdministrativaInvalidaError,
    TransferenciaInvalidaError,
    TransicaoInvalidaError,
)
from ativos.models import Ativo, CategoriaAtivo, DetalheManutencao, Movimentacao
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Fornecedor, Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id

SENHA = "senha-bem-longa-2026"


class BaseTransferencia(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Transf", slug="pref-transf")
        token = set_current_tenant_id(self.tenant.pk)
        self.addCleanup(reset_current_tenant_id, token)

        self.origem = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Matriz")
        self.destino = Unidade.objects.all_tenants().create(tenant=self.tenant, nome="Filial")
        self.categoria = CategoriaAtivo.objects.all_tenants().create(
            tenant=self.tenant, nome="Cadeira de Rodas", prefixo="CAD"
        )
        self.ativo = Ativo.objects.all_tenants().create(
            tenant=self.tenant, patrimonio="CAD-0001", categoria=self.categoria, unidade=self.origem
        )


class TransferirServiceTest(BaseTransferencia):
    def test_transferencia_muda_a_unidade_sem_mudar_o_status(self):
        movimentacao = services.transferir(
            self.ativo, usuario=None, unidade_destino=self.destino, observacoes="Remanejamento"
        )
        self.ativo.refresh_from_db()

        self.assertEqual(self.destino, self.ativo.unidade)
        self.assertEqual(StatusAtivo.DISPONIVEL.value, self.ativo.status)
        self.assertEqual(TipoMovimentacao.TRANSFERENCIA.value, movimentacao.tipo)
        self.assertEqual("disponivel", movimentacao.status_anterior)
        self.assertEqual("disponivel", movimentacao.status_novo)

    def test_registra_origem_e_destino_pelo_nome_na_timeline(self):
        """
        A FK da movimentação aponta só para o destino e é SET_NULL — sem a cópia
        textual, renomear a unidade de origem apagaria do histórico de onde o
        ativo saiu, que é exatamente o que a transferência existe para contar.
        """
        movimentacao = services.transferir(
            self.ativo, usuario=None, unidade_destino=self.destino, observacoes="Remanejamento"
        )
        dados = movimentacao.dados_especificos
        self.assertEqual("Matriz", dados["unidade_origem_nome"])
        self.assertEqual("Filial", dados["unidade_destino_nome"])

        self.origem.nome = "Matriz (desativada)"
        self.origem.save()
        movimentacao.refresh_from_db()
        self.assertEqual("Matriz", movimentacao.dados_especificos["unidade_origem_nome"])

    def test_transferir_para_a_mesma_unidade_e_recusado(self):
        with self.assertRaises(TransferenciaInvalidaError):
            services.transferir(self.ativo, usuario=None, unidade_destino=self.origem)
        self.assertEqual(0, Movimentacao.objects.filter(ativo=self.ativo).count())

    def test_nao_transfere_ativo_emprestado(self):
        beneficiario = Beneficiario.objects.all_tenants().create(
            tenant=self.tenant, nome="Maria Silva", documento="123.456.789-09"
        )
        services.emprestar(self.ativo, beneficiario, usuario=None, prazo_dias=30)
        self.ativo.refresh_from_db()

        with self.assertRaises(TransicaoInvalidaError):
            services.transferir(self.ativo, usuario=None, unidade_destino=self.destino)

        self.ativo.refresh_from_db()
        self.assertEqual(self.origem, self.ativo.unidade)

    def test_transfere_ativo_em_manutencao(self):
        """O ativo está na oficina, mas a responsabilidade patrimonial pode mudar."""
        services.enviar_manutencao(self.ativo, usuario=None, motivo="Roda solta")
        self.ativo.refresh_from_db()

        services.transferir(self.ativo, usuario=None, unidade_destino=self.destino)
        self.ativo.refresh_from_db()
        self.assertEqual(self.destino, self.ativo.unidade)
        self.assertEqual(StatusAtivo.MANUTENCAO.value, self.ativo.status)


class TransferirPelaViewTest(BaseTransferencia):
    def setUp(self):
        super().setUp()
        self.gestor = Usuario.objects.create_user(
            username="gestor_transf",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.gestor.unidades.add(self.origem)
        self.funcionario = Usuario.objects.create_user(
            username="func_transf",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.funcionario.unidades.add(self.origem)

    def test_gestor_transfere_e_o_ativo_sai_da_sua_visao(self):
        """
        Consequência esperada do escopo por unidade: quem transfere para uma
        unidade que não opera perde o ativo de vista. É por isso que o
        formulário exige justificativa.
        """
        self.client.login(username="gestor_transf", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "transferir"]),
            {"unidade_destino": self.destino.pk, "observacoes": "Remanejado para a filial"},
        )
        self.assertEqual(302, resposta.status_code)

        self.ativo.refresh_from_db()
        self.assertEqual(self.destino, self.ativo.unidade)

        self.assertEqual(404, self.client.get(
            reverse("app:ativos:ficha", args=[self.ativo.pk])
        ).status_code)

    def test_transferencia_exige_justificativa(self):
        self.client.login(username="gestor_transf", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "transferir"]),
            {"unidade_destino": self.destino.pk, "observacoes": ""},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("observacoes", resposta.context["form"].errors)
        self.ativo.refresh_from_db()
        self.assertEqual(self.origem, self.ativo.unidade)

    def test_funcionario_nao_transfere(self):
        self.client.login(username="func_transf", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "transferir"]),
            {"unidade_destino": self.destino.pk, "observacoes": "Tentativa"},
        )
        self.assertEqual(403, resposta.status_code)

    def test_unidade_atual_nao_aparece_como_destino(self):
        self.client.login(username="gestor_transf", password=SENHA)
        resposta = self.client.get(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "transferir"])
        )
        destinos = list(resposta.context["form"].fields["unidade_destino"].queryset)
        self.assertEqual([self.destino], destinos)


class ExtravioPelaViewTest(BaseTransferencia):
    def setUp(self):
        super().setUp()
        self.gestor = Usuario.objects.create_user(
            username="gestor_extravio",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="gestor"),
        )
        self.gestor.unidades.add(self.origem)

    def test_gestor_registra_extravio_de_ativo_em_estoque(self):
        """Inventário que não encontra o item — antes disto não havia tela para isso."""
        self.client.login(username="gestor_extravio", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "registrar_extravio"]),
            {"observacoes": "Não localizado no inventário de julho"},
        )
        self.assertEqual(302, resposta.status_code)

        self.ativo.refresh_from_db()
        self.assertEqual(StatusAtivo.EXTRAVIADO.value, self.ativo.status)
        movimentacao = Movimentacao.objects.filter(ativo=self.ativo).first()
        self.assertEqual(TipoMovimentacao.EXTRAVIO.value, movimentacao.tipo)
        self.assertIn("inventário", movimentacao.observacoes)

    def test_extravio_exige_justificativa(self):
        """Sem o "por quê", o registro de extravio não tem nada a contar depois."""
        self.client.login(username="gestor_extravio", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "registrar_extravio"]),
            {"observacoes": ""},
        )
        self.assertEqual(200, resposta.status_code)
        self.ativo.refresh_from_db()
        self.assertEqual(StatusAtivo.DISPONIVEL.value, self.ativo.status)

    def test_recuperacao_usa_o_tipo_proprio_e_nao_transferencia(self):
        services.registrar_extravio(self.ativo, usuario=None, observacoes="Perdido")
        self.ativo.refresh_from_db()

        movimentacao = services.registrar_recuperacao(
            self.ativo, usuario=None, observacoes="Encontrado no depósito"
        )
        self.ativo.refresh_from_db()

        self.assertEqual(StatusAtivo.DISPONIVEL.value, self.ativo.status)
        self.assertEqual(TipoMovimentacao.RECUPERACAO.value, movimentacao.tipo)


class EditarManutencaoTest(BaseTransferencia):
    def setUp(self):
        super().setUp()
        self.funcionario = Usuario.objects.create_user(
            username="func_manut",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )
        self.funcionario.unidades.add(self.origem)
        self.fornecedor = Fornecedor.objects.all_tenants().create(
            tenant=self.tenant, nome="Oficina Central"
        )
        services.enviar_manutencao(self.ativo, usuario=None, motivo="Roda solta")
        self.ativo.refresh_from_db()

    def test_funcionario_corrige_os_dados_da_manutencao(self):
        """
        Quem está com o ativo na oficina é quem sabe corrigir motivo/valor —
        exigir Gestor para isso só geraria dado errado esperando aprovação.
        """
        self.client.login(username="func_manut", password=SENHA)
        resposta = self.client.post(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "editar_manutencao"]),
            {
                "motivo": "Roda solta e freio travando",
                "fornecedor": self.fornecedor.pk,
                "valor": "180.50",
            },
        )
        self.assertEqual(302, resposta.status_code)

        detalhe = DetalheManutencao.objects.get(movimentacao__ativo=self.ativo)
        self.assertEqual("Roda solta e freio travando", detalhe.motivo)
        self.assertEqual(self.fornecedor, detalhe.fornecedor)

    def test_formulario_vem_preenchido_com_os_dados_atuais(self):
        """É uma correção, não um registro novo — abrir vazio convidaria a apagar dado."""
        self.client.login(username="func_manut", password=SENHA)
        resposta = self.client.get(
            reverse("app:ativos:executar_acao", args=[self.ativo.pk, "editar_manutencao"])
        )
        self.assertEqual("Roda solta", resposta.context["form"].initial["motivo"])

    def test_editar_manutencao_nao_cria_movimentacao(self):
        """
        Correção de metadado não é evento de estado: a timeline registra
        transições, e a alteração fica na trilha de auditoria
        (docs/business-rules/manutencao.md).
        """
        antes = Movimentacao.objects.filter(ativo=self.ativo).count()
        services.editar_manutencao(self.ativo, usuario=None, motivo="Outro motivo")
        self.assertEqual(antes, Movimentacao.objects.filter(ativo=self.ativo).count())

    def test_nao_edita_manutencao_de_ativo_que_nao_esta_em_manutencao(self):
        services.retornar_manutencao(self.ativo, usuario=None)
        self.ativo.refresh_from_db()
        with self.assertRaises(AcaoAdministrativaInvalidaError):
            services.editar_manutencao(self.ativo, usuario=None, motivo="Tarde demais")

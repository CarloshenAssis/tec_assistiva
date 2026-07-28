"""
Casos de uso do domínio de Ativos — a camada que orquestra
`ativos.domain.state_machine` com a persistência (Django ORM), seguindo o
padrão de camadas já definido em docs/ESPECIFICACAO_TECNICA.md §3.2
(`services.py` mantém as views "magras").

Toda função aqui é a ÚNICA forma correta de mudar o status de um Ativo —
nunca se deve atribuir `ativo.status = ...` diretamente fora deste módulo,
porque isso pularia a validação da máquina de estados e deixaria de criar
o registro de `Movimentacao` correspondente (violando o invariante
"nenhuma mudança de status sem rastro" — docs/PLANO_DOMINIO_ATIVOS.md §2.2).
"""

from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.domain.exceptions import AcaoAdministrativaInvalidaError
from ativos.domain.state_machine import pode_inativar, transicionar
from ativos.models import Ativo, DetalheEmprestimo, DetalheManutencao, FotoMovimentacao, Movimentacao


def _registrar(
    ativo: Ativo,
    tipo: TipoMovimentacao,
    usuario,
    destino: Optional[StatusAtivo] = None,
    unidade=None,
    observacoes: str = "",
    dados_especificos: Optional[dict] = None,
) -> Movimentacao:
    status_atual = ativo.status_enum
    status_novo = transicionar(status_atual, tipo, destino)

    with transaction.atomic():
        movimentacao = Movimentacao.objects.create(
            tenant=ativo.tenant,
            ativo=ativo,
            tipo=tipo.value,
            usuario=usuario,
            unidade=unidade if unidade is not None else ativo.unidade,
            observacoes=observacoes,
            status_anterior=status_atual.value,
            status_novo=status_novo.value,
            dados_especificos=dados_especificos or {},
        )
        update_fields = ["status", "atualizado_em"]
        ativo.status = status_novo.value
        if unidade is not None:
            ativo.unidade = unidade
            update_fields.append("unidade")
        ativo.save(update_fields=update_fields)

    return movimentacao


def emprestar(
    ativo: Ativo,
    beneficiario,
    usuario,
    prazo_dias: int,
    unidade=None,
    observacoes: str = "",
    checklist: Optional[dict] = None,
    assinatura_arquivo=None,
) -> Movimentacao:
    """
    Assinatura física é o padrão do sistema (docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md
    §1): o checklist inclui os itens "termo impresso"/"termo assinado", e
    `assinatura_arquivo` é a foto/scan do termo assinado — não uma
    assinatura em tela. O módulo de assinatura digital (opcional, por
    tenant) fica fora do escopo desta fase.
    """
    data_prevista = timezone.now().date() + timedelta(days=prazo_dias)
    movimentacao = _registrar(
        ativo,
        TipoMovimentacao.EMPRESTIMO,
        usuario,
        unidade=unidade,
        observacoes=observacoes,
        dados_especificos={"checklist": checklist or {}},
    )
    DetalheEmprestimo.objects.create(
        tenant=ativo.tenant,
        movimentacao=movimentacao,
        beneficiario=beneficiario,
        prazo_dias=prazo_dias,
        data_prevista_devolucao=data_prevista,
        assinatura_tipo=DetalheEmprestimo.AssinaturaTipo.FISICA,
        assinatura_arquivo=assinatura_arquivo,
    )
    return movimentacao


def renovar(ativo: Ativo, usuario, novo_prazo_dias: int, observacoes: str = "") -> Movimentacao:
    """
    Registra a renovação sem criar um novo `DetalheEmprestimo` (que
    permanece como o registro histórico das condições da retirada
    original). A nova data prevista fica em `dados_especificos` — uma
    consulta de "prazo vigente" (Fase 1) deve olhar a renovação mais
    recente antes de cair para o `DetalheEmprestimo` original.
    """
    nova_data = timezone.now().date() + timedelta(days=novo_prazo_dias)
    return _registrar(
        ativo,
        TipoMovimentacao.RENOVACAO,
        usuario,
        observacoes=observacoes,
        dados_especificos={
            "novo_prazo_dias": novo_prazo_dias,
            "nova_data_devolucao": nova_data.isoformat(),
        },
    )


def devolver(
    ativo: Ativo,
    usuario,
    destino: StatusAtivo,
    unidade=None,
    observacoes: str = "",
    checklist: Optional[dict] = None,
) -> Movimentacao:
    return _registrar(
        ativo,
        TipoMovimentacao.DEVOLUCAO,
        usuario,
        destino=destino,
        unidade=unidade,
        observacoes=observacoes,
        dados_especificos={"checklist": checklist or {}},
    )


def anexar_foto(movimentacao: Movimentacao, arquivo, tipo: str = "frontal") -> FotoMovimentacao:
    """
    Fotos da entrega/devolução/manutenção, usadas na comparação
    antes/depois (docs/PLANO_DOMINIO_ATIVOS.md §9).
    """
    return FotoMovimentacao.objects.create(
        tenant=movimentacao.tenant, movimentacao=movimentacao, tipo=tipo, arquivo=arquivo
    )


def reservar(ativo: Ativo, usuario, observacoes: str = "") -> Movimentacao:
    return _registrar(ativo, TipoMovimentacao.RESERVA, usuario, observacoes=observacoes)


def cancelar_reserva(ativo: Ativo, usuario, observacoes: str = "") -> Movimentacao:
    return _registrar(ativo, TipoMovimentacao.RESERVA, usuario, observacoes=observacoes)


def enviar_manutencao(
    ativo: Ativo,
    usuario,
    motivo: str,
    fornecedor=None,
    valor=None,
    observacoes: str = "",
) -> Movimentacao:
    movimentacao = _registrar(ativo, TipoMovimentacao.MANUTENCAO, usuario, observacoes=observacoes)
    DetalheManutencao.objects.create(
        tenant=ativo.tenant,
        movimentacao=movimentacao,
        fornecedor=fornecedor,
        motivo=motivo,
        valor=valor,
    )
    return movimentacao


def retornar_manutencao(ativo: Ativo, usuario, observacoes: str = "") -> Movimentacao:
    movimentacao = _registrar(
        ativo, TipoMovimentacao.RETORNO_MANUTENCAO, usuario, observacoes=observacoes
    )
    ultima_manutencao = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.MANUTENCAO)
    detalhe = getattr(ultima_manutencao, "detalhe_manutencao", None)
    if detalhe is not None:
        detalhe.data_conclusao = timezone.now().date()
        detalhe.save(update_fields=["data_conclusao"])
    return movimentacao


def concluir_higienizacao(ativo: Ativo, usuario, observacoes: str = "") -> Movimentacao:
    return _registrar(ativo, TipoMovimentacao.HIGIENIZACAO, usuario, observacoes=observacoes)


def registrar_extravio(ativo: Ativo, usuario, observacoes: str = "") -> Movimentacao:
    return _registrar(ativo, TipoMovimentacao.EXTRAVIO, usuario, observacoes=observacoes)


def registrar_recuperacao(ativo: Ativo, usuario, observacoes: str = "") -> Movimentacao:
    """Ativo extraviado que foi encontrado — recuperação, exige justificativa."""
    return _registrar(ativo, TipoMovimentacao.TRANSFERENCIA, usuario, observacoes=observacoes)


def dar_baixa(ativo: Ativo, usuario, motivo: str, observacoes: str = "") -> Movimentacao:
    return _registrar(
        ativo,
        TipoMovimentacao.BAIXA,
        usuario,
        observacoes=observacoes,
        dados_especificos={"motivo": motivo},
    )


def inativar(ativo: Ativo, usuario, motivo: str = "") -> None:
    """
    Ação administrativa (não operacional) — não passa pela tabela de
    transições por `Movimentacao` (docs/PLANO_DOMINIO_ATIVOS.md §5.2).
    Só o Admin do tenant pode chamar isto (RBAC verificado na view).
    """
    if not pode_inativar(ativo.status_enum):
        raise AcaoAdministrativaInvalidaError(ativo.status_enum, "inativar")
    ativo.status = StatusAtivo.INATIVO.value
    ativo.save(update_fields=["status", "atualizado_em"])


def reativar(ativo: Ativo, usuario) -> None:
    if ativo.status_enum != StatusAtivo.INATIVO:
        raise AcaoAdministrativaInvalidaError(ativo.status_enum, "reativar")
    ativo.status = StatusAtivo.DISPONIVEL.value
    ativo.save(update_fields=["status", "atualizado_em"])

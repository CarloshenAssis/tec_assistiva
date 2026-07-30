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

import logging
import uuid
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.domain.exceptions import (
    AcaoAdministrativaInvalidaError,
    TransferenciaInvalidaError,
)
from ativos.domain.state_machine import pode_inativar, transicionar
from ativos.models import (
    Ativo,
    DetalheEmprestimo,
    DetalheManutencao,
    FotoMovimentacao,
    ImpressaoEtiqueta,
    Movimentacao,
)


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
    _notificar_confirmacao_emprestimo(ativo, beneficiario, data_prevista, movimentacao)
    return movimentacao


def _notificar_confirmacao_emprestimo(ativo, beneficiario, data_prevista, movimentacao):
    """
    Disparo automático da confirmação de empréstimo (RF016). Uma falha na
    notificação nunca deve derrubar o empréstimo em si (RNF016) — daí o
    `try/except` amplo aqui, isolado do restante da transação (a
    `Movimentacao`/`DetalheEmprestimo` já foram gravadas com sucesso).
    """
    try:
        from notificacoes.services import criar_e_enviar

        criar_e_enviar(
            tenant=ativo.tenant,
            beneficiario=beneficiario,
            tipo="confirmacao_emprestimo",
            contexto={
                "beneficiario": beneficiario.nome,
                "ativo": ativo.categoria.nome,
                "codigo": ativo.patrimonio,
                "data_prevista": data_prevista.strftime("%d/%m/%Y"),
                "dias": (data_prevista - timezone.now().date()).days,
            },
            movimentacao=movimentacao,
        )
    except Exception:  # noqa: BLE001 — notificação nunca pode derrubar o empréstimo
        logging.getLogger("notificacoes").exception(
            "Falha ao notificar confirmação de empréstimo do ativo %s", ativo.pk
        )


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
    return _registrar(ativo, TipoMovimentacao.RECUPERACAO, usuario, observacoes=observacoes)


def transferir(ativo: Ativo, usuario, unidade_destino, observacoes: str = "") -> Movimentacao:
    """
    Move a unidade responsável pelo ativo, sem alterar o estado operacional
    dele (docs/business-rules/unidades.md).

    Guarda nome e id da unidade de origem e de destino em
    `dados_especificos`, e não apenas a FK `Movimentacao.unidade`: a FK é
    `SET_NULL` e aponta só para o destino, então sem essa cópia textual o
    histórico perderia de onde o ativo saiu no dia em que a unidade de
    origem fosse renomeada ou removida — justamente a informação que a
    transferência existe para registrar.
    """
    origem = ativo.unidade
    if origem is not None and unidade_destino.pk == origem.pk:
        raise TransferenciaInvalidaError(
            f"O ativo {ativo.patrimonio} já está na unidade {unidade_destino.nome}."
        )
    return _registrar(
        ativo,
        TipoMovimentacao.TRANSFERENCIA,
        usuario,
        unidade=unidade_destino,
        observacoes=observacoes,
        dados_especificos={
            "unidade_origem_id": origem.pk if origem else None,
            "unidade_origem_nome": origem.nome if origem else "",
            "unidade_destino_id": unidade_destino.pk,
            "unidade_destino_nome": unidade_destino.nome,
        },
    )


def editar_manutencao(
    ativo: Ativo, usuario, motivo: str, fornecedor=None, valor=None
) -> DetalheManutencao:
    """
    Corrige os dados da manutenção em curso (motivo/fornecedor/valor).

    Não gera `Movimentacao`: o estado do ativo não muda, e a timeline
    registra eventos de estado, não correções de metadado. A alteração é
    capturada automaticamente pela trilha de auditoria (sinal `post_save`
    em `auditoria/rastreamento.py`), que registra quem alterou quais campos
    e quando — ver docs/business-rules/manutencao.md.
    """
    if ativo.status_enum != StatusAtivo.MANUTENCAO:
        raise AcaoAdministrativaInvalidaError(ativo.status_enum, "editar_manutencao")

    movimentacao = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.MANUTENCAO)
    detalhe = getattr(movimentacao, "detalhe_manutencao", None) if movimentacao else None
    if detalhe is None:
        # Ativo em manutenção sem DetalheManutencao é dado inconsistente
        # (importação antiga, ou manutenção criada fora dos serviços). Criar
        # o detalhe é melhor que estourar erro na cara do operador, que não
        # tem como resolver isso.
        detalhe = DetalheManutencao.objects.create(
            tenant=ativo.tenant, movimentacao=movimentacao, motivo=motivo, valor=valor,
            fornecedor=fornecedor,
        )
        return detalhe

    detalhe.motivo = motivo
    detalhe.fornecedor = fornecedor
    detalhe.valor = valor
    detalhe.save(update_fields=["motivo", "fornecedor", "valor"])
    return detalhe


def dar_baixa(ativo: Ativo, usuario, motivo: str, observacoes: str = "") -> Movimentacao:
    return _registrar(
        ativo,
        TipoMovimentacao.BAIXA,
        usuario,
        observacoes=observacoes,
        dados_especificos={"motivo": motivo},
    )


def registrar_impressao_etiquetas(ativos, usuario, layout: str) -> list:
    """
    Grava o histórico de impressão de um lote de etiquetas
    (docs/business-rules/etiquetas.md).

    Todas as etiquetas geradas na mesma folha compartilham um `lote`, o que
    permite mostrar o histórico agrupado e reimprimir exatamente o mesmo
    conjunto depois. Chamado no momento em que a folha é gerada — não há
    como o sistema saber se o papel realmente saiu da impressora, então o
    registro significa "folha emitida", e é por isso que "Reimprimir"
    existe como ação normal e não como correção de erro.
    """
    lote = uuid.uuid4()
    registros = [
        ImpressaoEtiqueta(
            tenant=ativo.tenant, ativo=ativo, layout=layout, usuario=usuario, lote=lote
        )
        for ativo in ativos
    ]
    # bulk_create não dispara os sinais de auditoria (limitação conhecida,
    # ver docs/business-rules/auditoria.md) — aceitável aqui: o próprio
    # ImpressaoEtiqueta JÁ É a trilha do evento, com usuário e horário.
    return ImpressaoEtiqueta.objects.bulk_create(registros)


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

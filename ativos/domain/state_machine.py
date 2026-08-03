"""
Máquina de estados do Ativo — implementação literal da tabela de
transições de docs/PLANO_DOMINIO_ATIVOS.md §5.2.

Este módulo não importa Django: é testado em isolamento total (ver
ativos/tests/test_state_machine.py) porque é a peça de maior risco de
negócio do produto (garantir, por construção, que "o ativo nunca poderá
estar em mais de um estado" e que ações inválidas — como emprestar um
ativo em manutenção — sejam impossíveis, não apenas escondidas na UI).
"""

from typing import Optional

from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.domain.exceptions import DestinoObrigatorioError, TransicaoInvalidaError

S = StatusAtivo
T = TipoMovimentacao

#: Estados a partir dos quais transferir o ativo de unidade é permitido.
#:
#: São os estados em que o ativo está sob controle direto da organização.
#: `EMPRESTADO` fica de fora de propósito: o ativo está fisicamente com o
#: beneficiário, e trocar a unidade responsável no meio do empréstimo
#: tornaria ambíguo quem responde pela devolução. `BAIXADO`, `INATIVO` e
#: `EXTRAVIADO` também ficam de fora — não há o que transferir.
_ESTADOS_TRANSFERIVEIS = {S.DISPONIVEL, S.RESERVADO, S.MANUTENCAO, S.HIGIENIZACAO}

# Transições "simples": (status_atual, tipo) -> status_novo, sem ambiguidade de destino.
_TRANSICOES_SIMPLES = {
    (S.DISPONIVEL, T.EMPRESTIMO): S.EMPRESTADO,
    (S.DISPONIVEL, T.RESERVA): S.RESERVADO,
    (S.DISPONIVEL, T.MANUTENCAO): S.MANUTENCAO,
    (S.DISPONIVEL, T.BAIXA): S.BAIXADO,
    # Um ativo pode ser dado por extraviado sem estar emprestado — é o caso
    # do inventário que não encontra o item na prateleira.
    (S.DISPONIVEL, T.EXTRAVIO): S.EXTRAVIADO,
    (S.RESERVADO, T.EMPRESTIMO): S.EMPRESTADO,
    (S.RESERVADO, T.RESERVA): S.DISPONIVEL,  # cancelamento da reserva
    (S.EMPRESTADO, T.RENOVACAO): S.EMPRESTADO,  # não muda o status, mas é registrado
    (S.EMPRESTADO, T.EXTRAVIO): S.EXTRAVIADO,
    (S.HIGIENIZACAO, T.HIGIENIZACAO): S.DISPONIVEL,  # conclusão da higienização
    (S.MANUTENCAO, T.RETORNO_MANUTENCAO): S.DISPONIVEL,
    (S.MANUTENCAO, T.BAIXA): S.BAIXADO,
    (S.EXTRAVIADO, T.RECUPERACAO): S.DISPONIVEL,  # extraviado que foi encontrado
    # Transferência entre unidades NÃO muda o estado operacional do ativo —
    # muda a unidade responsável (registrada na própria Movimentacao). Por
    # isso cada estado transferível mapeia para si mesmo.
    **{(estado, T.TRANSFERENCIA): estado for estado in _ESTADOS_TRANSFERIVEIS},
}

# Transições em que o destino varia por decisão do operador no momento do evento.
_DESTINOS_VALIDOS_DEVOLUCAO = {S.DISPONIVEL, S.HIGIENIZACAO, S.MANUTENCAO}
_TRANSICOES_COM_DESTINO = {
    (S.EMPRESTADO, T.DEVOLUCAO): _DESTINOS_VALIDOS_DEVOLUCAO,
}

# Estados a partir dos quais uma inativação administrativa é permitida.
# Não é disparada por uma Movimentacao operacional (não há tipo fechado
# para isso no enum TipoMovimentacao — ver docs/PLANO_DOMINIO_ATIVOS.md §5.2,
# nota sobre o estado `inativo`), por isso tem funções dedicadas abaixo em
# vez de entrar nas tabelas de transição por tipo de movimentação.
_ESTADOS_INATIVAVEIS = {S.DISPONIVEL, S.MANUTENCAO, S.RESERVADO}

ESTADOS_TERMINAIS = {S.BAIXADO}


def transicionar(
    status_atual: StatusAtivo, tipo: TipoMovimentacao, destino: Optional[StatusAtivo] = None
) -> StatusAtivo:
    """Calcula o novo status do Ativo dada uma movimentação.

    Função central da máquina de estados — todo registro de
    `Movimentacao` passa por aqui antes de gravar, direta ou
    indiretamente (via `ativos.services`).

    Args:
        status_atual: O `StatusAtivo` corrente do ativo.
        tipo: O `TipoMovimentacao` sendo registrado.
        destino: Obrigatório apenas para transições ambíguas (hoje, só
            `DEVOLUCAO` a partir de `EMPRESTADO`), onde o operador
            escolhe entre múltiplos status novos possíveis. Ignorado nas
            demais transições.

    Returns:
        O novo `StatusAtivo` resultante da transição.

    Raises:
        DestinoObrigatorioError: Se a transição exigir `destino` e ele
            não tiver sido informado.
        TransicaoInvalidaError: Se a combinação de `status_atual` e
            `tipo` (e, quando aplicável, `destino`) não estiver na
            tabela de transições permitidas.
    """
    chave_com_destino = (status_atual, tipo)
    if chave_com_destino in _TRANSICOES_COM_DESTINO:
        destinos_validos = _TRANSICOES_COM_DESTINO[chave_com_destino]
        if destino is None:
            raise DestinoObrigatorioError(
                f"A movimentação '{tipo.rotulo}' a partir do estado "
                f"'{status_atual.rotulo}' exige um destino explícito "
                f"(um de: {sorted(d.value for d in destinos_validos)})."
            )
        if destino not in destinos_validos:
            raise TransicaoInvalidaError(status_atual, tipo, destino)
        return destino

    chave_simples = (status_atual, tipo)
    if chave_simples in _TRANSICOES_SIMPLES:
        return _TRANSICOES_SIMPLES[chave_simples]

    raise TransicaoInvalidaError(status_atual, tipo, destino)


def pode_transicionar(
    status_atual: StatusAtivo, tipo: TipoMovimentacao, destino: Optional[StatusAtivo] = None
) -> bool:
    """Verifica, sem levantar exceção, se uma transição é permitida.

    Args:
        status_atual: O `StatusAtivo` corrente do ativo.
        tipo: O `TipoMovimentacao` a verificar.
        destino: Ver `transicionar`.

    Returns:
        `True` se `transicionar` com os mesmos argumentos não levantaria
        exceção; `False` caso contrário.
    """
    try:
        transicionar(status_atual, tipo, destino)
        return True
    except (TransicaoInvalidaError, DestinoObrigatorioError):
        return False


def pode_inativar(status_atual: StatusAtivo) -> bool:
    """Verifica se a inativação administrativa é permitida a partir do estado.

    Args:
        status_atual: O `StatusAtivo` corrente do ativo.

    Returns:
        `True` se `status_atual` estiver em `_ESTADOS_INATIVAVEIS`
        (`DISPONIVEL`, `MANUTENCAO` ou `RESERVADO`).
    """
    return status_atual in _ESTADOS_INATIVAVEIS


def pode_transferir(status_atual: StatusAtivo) -> bool:
    """Verifica se a transferência entre unidades é permitida a partir do estado.

    Args:
        status_atual: O `StatusAtivo` corrente do ativo.

    Returns:
        `True` se `status_atual` estiver em `_ESTADOS_TRANSFERIVEIS`.
    """
    return status_atual in _ESTADOS_TRANSFERIVEIS


def eh_estado_terminal(status_atual: StatusAtivo) -> bool:
    """Verifica se o estado é terminal (sem transição de saída).

    Args:
        status_atual: O `StatusAtivo` a verificar.

    Returns:
        `True` se `status_atual` estiver em `ESTADOS_TERMINAIS`
        (hoje, só `BAIXADO`).
    """
    return status_atual in ESTADOS_TERMINAIS

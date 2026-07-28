from ativos.domain.enums import StatusAtivo, TipoMovimentacao


class DominioAtivoError(Exception):
    """Base para erros de domínio do Ativo."""


class TransicaoInvalidaError(DominioAtivoError):
    """
    Levantada quando uma `Movimentacao` tentaria colocar o Ativo numa
    transição de estado fora da tabela definida em
    docs/PLANO_DOMINIO_ATIVOS.md §5.2.

    É levantada pelo domínio (ativos/domain/state_machine.py), não pela
    view — ou seja, mesmo uma chamada direta à API ou um bug de UI não
    conseguem colocar o ativo num estado inconsistente.
    """

    def __init__(self, status_atual: StatusAtivo, tipo: TipoMovimentacao, destino=None):
        self.status_atual = status_atual
        self.tipo = tipo
        self.destino = destino
        detalhe = f" com destino '{destino}'" if destino else ""
        super().__init__(
            f"Não é possível registrar uma movimentação do tipo "
            f"'{tipo.rotulo}'{detalhe} para um ativo no estado "
            f"'{status_atual.rotulo}'."
        )


class DestinoObrigatorioError(DominioAtivoError):
    """Levantada quando uma movimentação exige `destino` e ele não foi informado."""


class AcaoAdministrativaInvalidaError(DominioAtivoError):
    """
    Levantada por `inativar`/`reativar` — ações administrativas que não
    passam pela tabela de transições por `Movimentacao` (não há um
    `TipoMovimentacao` operacional para elas, ver
    docs/PLANO_DOMINIO_ATIVOS.md §5.2, nota sobre o estado `inativo`).
    """

    def __init__(self, status_atual: StatusAtivo, acao: str):
        self.status_atual = status_atual
        self.acao = acao
        super().__init__(
            f"Não é possível executar a ação '{acao}' com o ativo no estado "
            f"'{status_atual.rotulo}'."
        )

"""
`acoes_disponiveis` — a única fonte de verdade sobre "o que pode ser feito
agora" com um Ativo (docs/PLANO_DOMINIO_ATIVOS.md §5.3).

Consumida por: resolução do QR Code, ficha do ativo, painel rápido (drawer)
e, futuramente, endpoints de API — nunca reimplementada por tela. Isso é o
que garante que essas superfícies nunca fiquem dessincronizadas entre si.

Cruza duas dimensões numa única chamada: o estado do ativo E o nível
hierárquico do usuário (RBAC). Quando `nivel_hierarquico` não é informado,
devolve a lista completa por estado, sem filtro de permissão — útil para
listar "todas as ações teoricamente possíveis neste estado" (ex.: em
telas administrativas/relatórios), mas as views de operação devem sempre
passar o nível do usuário logado.
"""

from dataclasses import dataclass
from typing import List, Optional

from ativos.domain.enums import StatusAtivo

S = StatusAtivo


@dataclass(frozen=True)
class Acao:
    codigo: str
    rotulo: str
    nivel_hierarquico_minimo: int = 0


# Níveis hierárquicos espelham contas.models.Papel.nivel_hierarquico
# (Funcionário=10, Gestor=20, Admin=30) — ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3.2.
NIVEL_FUNCIONARIO = 10
NIVEL_GESTOR = 20
NIVEL_ADMIN = 30

_ACOES_POR_STATUS = {
    S.DISPONIVEL: [
        Acao("emprestar", "Emprestar", NIVEL_FUNCIONARIO),
        Acao("enviar_manutencao", "Enviar para Manutenção", NIVEL_FUNCIONARIO),
        Acao("reservar", "Reservar", NIVEL_FUNCIONARIO),
        Acao("transferir", "Transferir de Unidade", NIVEL_GESTOR),
        Acao("editar", "Editar", NIVEL_GESTOR),
        Acao("imprimir_etiqueta", "Imprimir Etiqueta", NIVEL_FUNCIONARIO),
        Acao("ver_historico", "Ver Histórico", NIVEL_FUNCIONARIO),
        Acao("ver_fotos", "Ver Fotos", NIVEL_FUNCIONARIO),
        Acao("ver_timeline", "Ver Timeline", NIVEL_FUNCIONARIO),
        Acao("registrar_extravio", "Registrar Extravio", NIVEL_GESTOR),
        Acao("dar_baixa", "Dar Baixa", NIVEL_GESTOR),
    ],
    S.RESERVADO: [
        Acao("confirmar_emprestimo", "Confirmar Empréstimo", NIVEL_FUNCIONARIO),
        Acao("cancelar_reserva", "Cancelar Reserva", NIVEL_FUNCIONARIO),
        Acao("transferir", "Transferir de Unidade", NIVEL_GESTOR),
        Acao("imprimir_etiqueta", "Imprimir Etiqueta", NIVEL_FUNCIONARIO),
        Acao("ver_historico", "Ver Histórico", NIVEL_FUNCIONARIO),
    ],
    S.EMPRESTADO: [
        Acao("receber_devolucao", "Receber Devolução", NIVEL_FUNCIONARIO),
        Acao("renovar", "Renovar Empréstimo", NIVEL_FUNCIONARIO),
        Acao("imprimir_etiqueta", "Imprimir Etiqueta", NIVEL_FUNCIONARIO),
        Acao("ver_historico", "Ver Histórico", NIVEL_FUNCIONARIO),
        Acao("ver_fotos", "Ver Fotos", NIVEL_FUNCIONARIO),
        Acao("registrar_extravio", "Registrar Extravio", NIVEL_GESTOR),
    ],
    S.MANUTENCAO: [
        Acao("finalizar_manutencao", "Finalizar Manutenção", NIVEL_FUNCIONARIO),
        # Quem está com o ativo em mãos na oficina é quem sabe corrigir
        # motivo/fornecedor/valor — exigir Gestor para isso só geraria dado
        # errado esperando aprovação. A alteração fica registrada na trilha
        # de auditoria (auditoria/rastreamento.py), então continua rastreável.
        Acao("editar_manutencao", "Editar Manutenção", NIVEL_FUNCIONARIO),
        Acao("transferir", "Transferir de Unidade", NIVEL_GESTOR),
        Acao("imprimir_etiqueta", "Imprimir Etiqueta", NIVEL_FUNCIONARIO),
        Acao("dar_baixa", "Dar Baixa", NIVEL_GESTOR),
        Acao("ver_historico", "Ver Histórico", NIVEL_FUNCIONARIO),
    ],
    S.HIGIENIZACAO: [
        Acao("concluir_higienizacao", "Concluir Higienização", NIVEL_FUNCIONARIO),
        Acao("transferir", "Transferir de Unidade", NIVEL_GESTOR),
        Acao("imprimir_etiqueta", "Imprimir Etiqueta", NIVEL_FUNCIONARIO),
        Acao("ver_historico", "Ver Histórico", NIVEL_FUNCIONARIO),
    ],
    S.EXTRAVIADO: [
        Acao("registrar_recuperacao", "Registrar Recuperação", NIVEL_GESTOR),
        Acao("ver_historico", "Ver Histórico", NIVEL_FUNCIONARIO),
    ],
    S.BAIXADO: [
        # Estado terminal: somente consulta, nenhuma ação de movimentação.
        # Imprimir etiqueta também não faz sentido — o ativo saiu do
        # patrimônio, uma etiqueta nova só geraria confusão no inventário.
        Acao("ver_historico", "Ver Histórico", NIVEL_FUNCIONARIO),
        Acao("ver_fotos", "Ver Fotos", NIVEL_FUNCIONARIO),
        Acao("ver_timeline", "Ver Timeline", NIVEL_FUNCIONARIO),
    ],
    S.INATIVO: [
        Acao("reativar", "Reativar", NIVEL_ADMIN),
        Acao("ver_historico", "Ver Histórico", NIVEL_FUNCIONARIO),
    ],
}


def acoes_disponiveis(
    status: StatusAtivo, nivel_hierarquico: Optional[int] = None
) -> List[Acao]:
    acoes = _ACOES_POR_STATUS.get(status, [])
    if nivel_hierarquico is None:
        return list(acoes)
    return [acao for acao in acoes if nivel_hierarquico >= acao.nivel_hierarquico_minimo]

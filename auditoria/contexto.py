"""
Requisição HTTP corrente, exposta via ContextVar para os sinais de auditoria.

Sinais do Django (`pre_save`/`post_save`/`post_delete`) não recebem a
requisição — e é dela que vem "quem fez essa alteração". Mesmo padrão já
usado em `core.tenancy` para o tenant corrente: middleware seta uma vez por
requisição, o código que precisa lê daqui, sem precisar passar `request`
por toda a cadeia de chamadas (views → services → sinais do ORM).
"""

from __future__ import annotations

import contextvars
from typing import Optional

_requisicao_atual: contextvars.ContextVar[Optional[object]] = contextvars.ContextVar(
    "requisicao_atual", default=None
)


def definir_requisicao_atual(request):
    """Registra a requisição corrente na ContextVar, para o restante do ciclo.

    Chamado uma vez por requisição pelo `CapturaRequisicaoMiddleware`, no
    início da cadeia de middlewares.

    Args:
        request: A requisição Django corrente.

    Returns:
        O token devolvido por `ContextVar.set`, a ser repassado a
        `limpar_requisicao_atual` ao final da requisição.
    """
    return _requisicao_atual.set(request)


def obter_requisicao_atual():
    """Devolve a requisição registrada para o contexto de execução corrente.

    Returns:
        A `request` definida por `definir_requisicao_atual`, ou `None` se
        nenhuma foi definida (ex.: código rodando fora de uma requisição
        HTTP, como um management command).
    """
    return _requisicao_atual.get()


def limpar_requisicao_atual(token) -> None:
    """Desfaz o registro da requisição ao final do ciclo.

    Sempre chamado em `finally` pelo middleware, para não vazar a
    requisição de uma execução para a próxima que reaproveitar a mesma
    thread/worker.

    Args:
        token: O token devolvido por `definir_requisicao_atual`.
    """
    _requisicao_atual.reset(token)

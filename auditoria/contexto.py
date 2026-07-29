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
    return _requisicao_atual.set(request)


def obter_requisicao_atual():
    return _requisicao_atual.get()


def limpar_requisicao_atual(token) -> None:
    _requisicao_atual.reset(token)

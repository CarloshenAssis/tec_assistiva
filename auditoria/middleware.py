"""
Expõe a requisição corrente via ContextVar para os sinais de auditoria.

Precisa vir depois de `AuthenticationMiddleware` (para `request.user` existir)
e de `TenantMiddleware` (para `request.tenant` existir) — ver
ciclartech/settings.py e auditoria/rastreamento.py.
"""

from __future__ import annotations

from auditoria.contexto import definir_requisicao_atual, limpar_requisicao_atual


class CapturaRequisicaoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = definir_requisicao_atual(request)
        try:
            return self.get_response(request)
        finally:
            limpar_requisicao_atual(token)

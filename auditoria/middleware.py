"""
Expõe a requisição corrente via ContextVar para os sinais de auditoria.

Precisa vir depois de `AuthenticationMiddleware` (para `request.user` existir)
e de `TenantMiddleware` (para `request.tenant` existir) — ver
ciclartech/settings.py e auditoria/rastreamento.py.
"""

from __future__ import annotations

from auditoria.contexto import definir_requisicao_atual, limpar_requisicao_atual


class CapturaRequisicaoMiddleware:
    """Middleware Django que publica a requisição corrente para os sinais de auditoria.

    É o único ponto de escrita da ContextVar de `auditoria.contexto` — todo
    o resto do sistema só lê. Precisa ser instalado depois de
    `AuthenticationMiddleware` e `TenantMiddleware`, para que
    `request.user`/`request.tenant` já estejam resolvidos quando o
    rastreamento de auditoria (`auditoria/rastreamento.py`) os ler.
    """

    def __init__(self, get_response):
        """Guarda o próximo elo da cadeia de middlewares.

        Args:
            get_response: Callable padrão do Django que processa o restante
                da cadeia de middlewares/view.
        """
        self.get_response = get_response

    def __call__(self, request):
        """Publica `request` na ContextVar durante o processamento da view.

        Args:
            request: A requisição Django corrente.

        Returns:
            A resposta produzida pelo restante da cadeia (`get_response`).
        """
        token = definir_requisicao_atual(request)
        try:
            return self.get_response(request)
        finally:
            limpar_requisicao_atual(token)

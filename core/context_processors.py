"""
Vocabulário de tela que varia por segmento do tenant (ex.: "Beneficiário"
numa prefeitura, "Cliente" numa locadora) — ver `core.models.Tenant`.
"""

from __future__ import annotations

from core import features


def vocabulario(request):
    """Context processor com o vocabulário de tela específico do segmento.

    `rotulo_beneficiario_singular`/`_plural`: usados na sidebar e nos
    títulos das telas de Beneficiários, para que o mesmo cadastro apareça
    com o nome que faz sentido para o segmento do cliente, sem duplicar
    template nem model por segmento.

    Owner e usuário anônimo não têm `tenant` (ver
    `contas.middleware.TenantMiddleware`) — nesse caso cai no rótulo padrão
    ("Beneficiário"), que é inofensivo nas telas onde aparece (login,
    painel do Owner não usa este rótulo).

    Args:
        request: A requisição corrente, com `request.tenant` já resolvido
            pelo `TenantMiddleware` (pode ser `None`).

    Returns:
        Dicionário de contexto injetado em todo template, com as chaves
        `rotulo_beneficiario_singular`, `rotulo_beneficiario_plural`,
        `locacao_financeiro_habilitado` e
        `documento_pessoa_juridica_habilitado`.
    """
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return {
            "rotulo_beneficiario_singular": "Beneficiário",
            "rotulo_beneficiario_plural": "Beneficiários",
            "locacao_financeiro_habilitado": False,
            "documento_pessoa_juridica_habilitado": False,
        }
    return {
        "rotulo_beneficiario_singular": tenant.rotulo_beneficiario_singular,
        "rotulo_beneficiario_plural": tenant.rotulo_beneficiario_plural,
        "locacao_financeiro_habilitado": features.modulo_habilitado(tenant, features.LOCACAO_FINANCEIRO),
        "documento_pessoa_juridica_habilitado": features.modulo_habilitado(
            tenant, features.DOCUMENTO_PESSOA_JURIDICA
        ),
    }

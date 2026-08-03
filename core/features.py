"""
Módulos/feature flags por tenant (docs/business-rules/modulos.md).

Um módulo tem um padrão de ativação por segmento (ex.: "locação
financeira" já nasce ligada para uma Locadora) e pode ser sobreposto
individualmente por tenant pela tela do Owner (`TenantModulo`) — o mesmo
princípio de "padrão + exceção explícita" que `core.unidades` já usa para
escopo de unidade.
"""

from __future__ import annotations

from core.models import Modulo, Tenant, TenantModulo

#: Código de cada módulo do catálogo — usado tanto para consultar quanto
#: para popular a migration de seed (`core/migrations/0003_*`). Manter os
#: dois em sincronia é responsabilidade de quem adicionar um módulo novo.
LOCACAO_FINANCEIRO = "locacao_financeiro"
DOCUMENTO_PESSOA_JURIDICA = "documento_pessoa_juridica"

#: Módulos ativos por padrão em cada segmento, na ausência de um
#: `TenantModulo` explícito para aquele tenant. Só a Locadora tem módulo
#: ligado por padrão hoje — os demais segmentos nascem com tudo desligado
#: e o Owner liga manualmente se um cliente específico precisar.
_MODULOS_PADRAO_POR_SEGMENTO: dict[str, set[str]] = {
    Tenant.Segmento.LOCADORA: {LOCACAO_FINANCEIRO, DOCUMENTO_PESSOA_JURIDICA},
}


def modulo_habilitado(tenant: Tenant, codigo: str) -> bool:
    """Verifica se um módulo está habilitado para um tenant.

    Nota de implementação: usa `all_tenants()` + filtro explícito por
    `tenant.pk` (mesmo padrão de `core.unidades.unidades_visiveis`) porque
    esta função recebe o tenant como argumento explícito e precisa
    funcionar tanto dentro de uma requisição (contexto do próprio tenant)
    quanto a partir do painel do Owner (consultando o módulo de QUALQUER
    tenant, não o corrente).

    Args:
        tenant: O `Tenant` a consultar, ou `None` quando não há tenant no
            contexto (Owner, usuário anônimo).
        codigo: Código do módulo (ver constantes deste módulo, ex.:
            `LOCACAO_FINANCEIRO`).

    Returns:
        `False` se `tenant` for `None` — não há tenant para se referir.
        Caso contrário, o valor explícito de `TenantModulo.ativo` se
        existir uma exceção configurada para este tenant, ou o padrão do
        segmento em `_MODULOS_PADRAO_POR_SEGMENTO`.
    """
    if tenant is None:
        return False

    registro = (
        TenantModulo.objects.all_tenants()
        .filter(tenant_id=tenant.pk, modulo__codigo=codigo)
        .first()
    )
    if registro is not None:
        return registro.ativo
    return codigo in _MODULOS_PADRAO_POR_SEGMENTO.get(tenant.segmento, set())


def modulos_do_tenant(tenant: Tenant) -> list[dict]:
    """Monta o catálogo completo de módulos com o status de cada um para um tenant.

    Usado na tela do Owner para montar os toggles
    (`templates/owner/tenant_detalhe.html`).

    Args:
        tenant: O `Tenant` cujo status de módulos será calculado.

    Returns:
        Lista de dicionários, um por módulo do catálogo, cada um com as
        chaves:

        - ``modulo``: a instância de `Modulo`.
        - ``ativo``: `bool` indicando se está ligado para este tenant.
        - ``e_o_padrao_do_segmento``: `bool` indicando se o valor de
          ``ativo`` vem do padrão do segmento (sem `TenantModulo`
          explícito) ou de uma exceção configurada manualmente.
    """
    padrao = _MODULOS_PADRAO_POR_SEGMENTO.get(tenant.segmento, set())
    overrides = {
        registro.modulo_id: registro.ativo
        for registro in TenantModulo.objects.all_tenants().filter(tenant_id=tenant.pk)
    }
    resultado = []
    for modulo in Modulo.objects.all():
        ativo_padrao = modulo.codigo in padrao
        resultado.append(
            {
                "modulo": modulo,
                "ativo": overrides.get(modulo.pk, ativo_padrao),
                "e_o_padrao_do_segmento": modulo.pk not in overrides,
            }
        )
    return resultado


def definir_modulo(tenant: Tenant, codigo: str, ativo: bool) -> None:
    """Liga ou desliga um módulo para um tenant específico.

    Grava (ou atualiza) a exceção explícita — chamado só pela tela do Owner.

    Nota de implementação: usa `all_tenants()` pelo mesmo motivo do resto
    do módulo — o `update_or_create` precisa localizar um `TenantModulo`
    já existente para QUALQUER tenant, e o manager padrão (`TenantManager`,
    escopado pelo ContextVar do tenant corrente) devolveria "não
    encontrado" sempre que chamado fora do contexto de requisição daquele
    tenant, já que a tela do Owner nunca está no contexto do tenant que
    está editando. Sem isto, cada chamada criaria uma linha nova e a
    segunda bateria na `UniqueConstraint`.

    Args:
        tenant: O `Tenant` a configurar.
        codigo: Código do módulo (ver constantes deste módulo).
        ativo: Novo estado do módulo para este tenant.

    Raises:
        Modulo.DoesNotExist: Se `codigo` não corresponder a nenhum módulo
            do catálogo.
    """
    modulo = Modulo.objects.get(codigo=codigo)
    TenantModulo.objects.all_tenants().update_or_create(
        tenant=tenant, modulo=modulo, defaults={"ativo": ativo}
    )

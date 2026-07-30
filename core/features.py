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
    """
    `tenant=None` (Owner, usuário anônimo) nunca tem módulo de tenant
    habilitado — não há tenant para se referir.

    Usa `all_tenants()` + filtro explícito por `tenant.pk` (mesmo padrão de
    `core.unidades.unidades_visiveis`): esta função recebe o tenant como
    argumento explícito e precisa funcionar tanto dentro de uma requisição
    (contexto do próprio tenant) quanto a partir do painel do Owner
    (consultando o módulo de QUALQUER tenant, não o corrente).
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
    """
    Todo o catálogo de módulos e se cada um está ativo para `tenant` —
    usado na tela do Owner para montar os toggles
    (`templates/owner/tenant_detalhe.html`).
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
    """
    Grava (ou atualiza) a exceção explícita — chamado só pela tela do Owner.

    `all_tenants()` aqui pelo mesmo motivo do resto do módulo: o `update_or_
    create` precisa localizar um `TenantModulo` já existente para QUALQUER
    tenant, e o manager padrão (`TenantManager`, escopado pelo ContextVar do
    tenant corrente) devolveria "não encontrado" sempre que chamado fora do
    contexto de requisição daquele tenant — a tela do Owner nunca está no
    contexto do tenant que está editando. Sem isto, cada chamada criaria uma
    linha nova e a segunda batia na `UniqueConstraint`.
    """
    modulo = Modulo.objects.get(codigo=codigo)
    TenantModulo.objects.all_tenants().update_or_create(
        tenant=tenant, modulo=modulo, defaults={"ativo": ativo}
    )

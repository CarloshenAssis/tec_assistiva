"""
Escopo de unidade por usuário — camada de decisão sobre "o que este usuário
pode ver", separada do modelo (contas/models.py::Usuario.unidades).

Decisão de arquitetura (docs/features/identificacao-patrimonial-e-unidades.md):
a unidade NÃO é um atributo fixo do usuário (não existe `Usuario.unidade`),
é uma permissão — `Usuario.unidades` é M2M. Isso é o que permite um Gestor
responsável por duas unidades, ou um Funcionário cobrindo férias em outra,
sem precisar de nenhuma alteração de modelo depois. Só o Admin (e o Owner)
enxergam todas as unidades do tenant, sempre — nunca dependem do M2M.
"""

from __future__ import annotations

from typing import Optional

from ativos.domain.acoes import NIVEL_ADMIN
from core.models import Unidade


def nivel_do_usuario(usuario) -> int:
    papel = getattr(usuario, "papel", None)
    return papel.nivel_hierarquico if papel else 0


def unidades_visiveis(usuario) -> "models.QuerySet[Unidade]":  # noqa: F821 — anotação só documental
    """
    Unidades que `usuario` pode operar/visualizar.

    Admin (e superusuário) enxergam todas as unidades do próprio tenant —
    "visão completa da organização", conforme a especificação. Gestor e
    Funcionário enxergam só as unidades atribuídas a eles via
    `Usuario.unidades`.

    Usa `all_tenants()` + filtro explícito por `usuario.tenant_id` (em vez
    do `Unidade.objects` normal, que depende do ContextVar do tenant
    corrente) de propósito: esta função recebe o usuário como argumento
    explícito e precisa devolver o resultado certo independente de haver ou
    não uma requisição HTTP em andamento — é chamada tanto de dentro de
    views (`tenant_required`) quanto de testes/scripts que não passam pelo
    `TenantMiddleware`. Por isso está na lista de exceções auditadas de
    `core/tests/test_architecture.py`, junto com `core/admin.py`.
    """
    base = Unidade.objects.all_tenants().filter(tenant_id=usuario.tenant_id)

    if usuario.is_platform_staff or usuario.is_superuser or nivel_do_usuario(usuario) >= NIVEL_ADMIN:
        return base

    return base.filter(usuarios_permitidos=usuario)


def unidades_do_usuario(usuario) -> "models.QuerySet[Unidade]":  # noqa: F821
    """
    Unidades atribuídas a `usuario` (o M2M em si, sem a regra "Admin vê
    tudo") — para exibir/editar a atribuição, diferente de
    `unidades_visiveis()`, que é para decidir o que o usuário PODE VER.

    Não use `usuario.unidades.all()` diretamente fora de uma view protegida
    por `tenant_required`: o acessor M2M do Django resolve através do
    manager padrão de `Unidade` (`TenantManager`, fail-closed pelo
    ContextVar de tenant corrente), então em teste/shell/management command
    — onde não há requisição ativa — `usuario.unidades.all()` devolve vazio
    mesmo com a linha existindo na tabela de junção. Esta função contorna
    isso com `all_tenants()` + filtro explícito por `usuario`.
    """
    return Unidade.objects.all_tenants().filter(usuarios_permitidos=usuario)


def usuario_pode_operar_unidade(usuario, unidade: Optional[Unidade]) -> bool:
    """
    `unidade=None` (ativo sem unidade definida) é sempre visível — não dá
    para restringir acesso a um dado que não tem unidade nenhuma associada,
    isso bloquearia até o Admin de ver o próprio cadastro incompleto.
    """
    if unidade is None:
        return True
    return unidades_visiveis(usuario).filter(pk=unidade.pk).exists()

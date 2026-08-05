"""
Captura automática de criação/alteração/exclusão para os models de domínio.

Por que sinal em vez de chamada explícita em cada view: "toda alteração
feita no sistema" não pode depender de um desenvolvedor lembrar de chamar
`registrar()` numa view nova — um esquecimento aqui seria um buraco
silencioso na trilha, e silencioso é exatamente o tipo de falha que uma
auditoria não pode ter. Conectar em `pre_save`/`post_save`/`post_delete`
garante que a captura acontece no próprio ORM, não importa por qual
view/service/management command o dado passou.

Limitação conhecida e aceita: `bulk_create`/`bulk_update`/`QuerySet.update()`
não disparam sinais por instância no Django — não há uso desses métodos nos
services de domínio hoje (todos usam `.create()`/`.save()` por instância);
se isso mudar, o ponto de escrita em massa precisa registrar explicitamente.
"""

from __future__ import annotations

from django.apps import apps as registro_global_de_apps
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from auditoria.contexto import obter_requisicao_atual
from auditoria.models import AcaoAuditada
from auditoria.services import registrar

#: Apps de domínio cujos models entram na trilha automaticamente. Só os
#: nossos — apps do próprio Django (sessions, admin, contenttypes) não são
#: dado de negócio e inflariam a trilha sem trazer valor de auditoria.
_APPS_AUDITADAS = {"core", "contas", "ativos", "beneficiarios", "notificacoes"}

#: Auto-exclusão: auditar a própria tabela de auditoria seria recursivo e
#: sem propósito — ela já é append-only e tem sua própria proteção
#: (RegistroAuditoria.save()/delete() bloqueados, ver auditoria/models.py).
_MODELOS_EXCLUIDOS = {"auditoria.registroauditoria"}


def _rotulo(sender) -> str:
    """Rótulo `"app_label.model_name"` (minúsculo) de um model, para `_MODELOS_EXCLUIDOS`.

    Args:
        sender: A classe do model, tal como recebida pelo sinal Django.

    Returns:
        String `"app_label.model_name"` em minúsculas.
    """
    return f"{sender._meta.app_label}.{sender._meta.model_name}"


def _eh_modelo_historico(sender) -> bool:
    """
    `True` para os models reconstruídos pelo executor de migrations
    (`apps.get_model()` dentro de uma `RunPython`).

    Auditar esses é ao mesmo tempo inútil e perigoso: inútil porque uma
    migration não tem requisição nem usuário — o registro sairia anônimo e sem
    contexto; perigoso porque a tabela de auditoria pode ainda não existir no
    ponto do grafo em que a migration roda, e aí o INSERT derruba o `migrate`
    inteiro. Isso torna a ordem do grafo de migrations uma dependência oculta
    de qualquer data migration que crie registro — foi exatamente o que
    aconteceu ao introduzir o backfill de unidade obrigatória em
    `ativos/migrations/0005_*`.

    A detecção compara o registro de apps do model com o registro global: o
    executor de migrations monta os models históricos num `Apps` próprio,
    isolado. É mais estável que checar `sender.__module__ == "__fake__"`, que
    depende do nome que o Django dá ao módulo sintético.

    Args:
        sender: A classe do model, tal como recebida pelo sinal Django.

    Returns:
        `True` se `sender` foi reconstruído por uma migration em vez de
        vir do registro normal de apps.
    """
    return sender._meta.apps is not registro_global_de_apps


def _deve_auditar(sender) -> bool:
    """Decide se um `save`/`delete` de `sender` deve gerar registro de auditoria.

    Combina as três exclusões: model histórico de migration, app fora da
    lista de apps de domínio e o próprio model de auditoria (evitaria
    recursão sem propósito).

    Args:
        sender: A classe do model, tal como recebida pelo sinal Django.

    Returns:
        `True` se o model deve ser auditado.
    """
    if _eh_modelo_historico(sender):
        return False
    return sender._meta.app_label in _APPS_AUDITADAS and _rotulo(sender) not in _MODELOS_EXCLUIDOS


def _campos_diferentes(anterior, atual) -> list[str]:
    """
    Nomes dos campos que mudaram — nunca os valores.

    O log de alteração automática não pode virar uma segunda cópia do dado
    pessoal (mesmo princípio já aplicado ao remover nome/telefone do log de
    notificações): saber que "cpf, telefone" mudaram é suficiente para uma
    investigação, e não duplica CPF/telefone em mais um lugar.
    """
    diferentes = []
    for campo in atual._meta.concrete_fields:
        nome = campo.name
        if nome == "id":
            continue
        if getattr(anterior, nome, None) != getattr(atual, nome, None):
            diferentes.append(nome)
    return diferentes


@receiver(pre_save)
def _capturar_estado_anterior(sender, instance, **kwargs):
    """Busca o estado do registro antes do `save()`, para comparar depois no `post_save`.

    Roda em todo `pre_save` de model auditado; para uma criação (`pk` ainda
    vazio) não há estado anterior a buscar.

    Args:
        sender: A classe do model que está sendo salvo.
        instance: A instância prestes a ser salva, ainda com os valores
            que serão persistidos.
        **kwargs: Demais argumentos do sinal `pre_save` (não usados).
    """
    if not _deve_auditar(sender):
        return
    # Guardado na própria instância (não num dict global por sender+pk): é o
    # mesmo objeto Python entre o pre_save e o post_save de um único
    # `.save()`, então não há risco de uma requisição concorrente
    # sobrescrever o estado capturado por outra.
    instance._auditoria_estado_anterior = (
        sender._base_manager.filter(pk=instance.pk).first() if instance.pk else None
    )


@receiver(post_save)
def _auditar_criacao_ou_alteracao(sender, instance, created, **kwargs):
    """Grava `CRIACAO` ou `ALTERACAO` na trilha, após um `save()` bem-sucedido.

    Para alteração, só grava se algum campo de fato mudou de valor (ver
    `_campos_diferentes`) — um `.save()` sem mudança não é evento de
    auditoria, mesmo que o ORM tenha rodado o UPDATE.

    Args:
        sender: A classe do model salvo.
        instance: A instância já salva, com os novos valores.
        created: `True` se foi um INSERT (criação), `False` se foi UPDATE.
        **kwargs: Demais argumentos do sinal `post_save` (não usados).
    """
    if not _deve_auditar(sender):
        return

    request = obter_requisicao_atual()
    tenant = getattr(instance, "tenant", None)

    if created:
        registrar(AcaoAuditada.CRIACAO, request=request, tenant=tenant, objeto=instance)
        return

    anterior = getattr(instance, "_auditoria_estado_anterior", None)
    if anterior is None:
        return
    campos = _campos_diferentes(anterior, instance)
    if not campos:
        # `.save()` sem mudança de valor não é "alteração" para efeito de
        # auditoria — evita ruído de re-save idempotente.
        return

    registrar(
        AcaoAuditada.ALTERACAO,
        request=request,
        tenant=tenant,
        objeto=instance,
        descricao=f"Campos alterados: {', '.join(campos)}",
    )


@receiver(post_delete)
def _auditar_exclusao(sender, instance, **kwargs):
    """Grava `EXCLUSAO` na trilha, após um `delete()` de model de domínio.

    Args:
        sender: A classe do model excluído.
        instance: A instância que acabou de ser excluída (ainda em memória,
            já sem linha correspondente no banco).
        **kwargs: Demais argumentos do sinal `post_delete` (não usados).
    """
    if not _deve_auditar(sender):
        return
    registrar(
        AcaoAuditada.EXCLUSAO,
        request=obter_requisicao_atual(),
        tenant=getattr(instance, "tenant", None),
        objeto=instance,
    )

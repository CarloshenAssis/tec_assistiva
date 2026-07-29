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
    return f"{sender._meta.app_label}.{sender._meta.model_name}"


def _deve_auditar(sender) -> bool:
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
    if not _deve_auditar(sender):
        return
    registrar(
        AcaoAuditada.EXCLUSAO,
        request=obter_requisicao_atual(),
        tenant=getattr(instance, "tenant", None),
        objeto=instance,
    )

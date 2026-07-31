"""
Limite de taxa para ações autenticadas sensíveis (transferir, dar baixa,
exportar dados de um titular, anonimizar).

Mesmo raciocínio de `contas/bloqueio.py` (bloqueio de login), reaproveitado
aqui: o estado é *derivado da trilha de auditoria* (Postgres), nunca de
`django.core.cache`. Um `LocMemCache` seria inofensivo na prática em
produção — a Vercel é serverless, cada invocação é um processo novo sem
memória compartilhada, então o contador nasceria zerado a cada requisição e
o limite nunca travaria nada.

O que isto resolve: login já tem bloqueio por tentativa (contas/bloqueio.py),
mas uma conta legítima (ou comprometida) não tinha *nenhuma* barreira depois
de autenticada — um script podia chamar `executar_acao` (emprestar, devolver,
transferir, dar baixa) milhares de vezes por minuto, e a única forma de
descobrir seria alguém ler a trilha de auditoria depois do estrago feito.
Isto não impede um usuário autorizado de operar normalmente (os limiares são
generosos para uso humano de balcão) — impede que a mesma conta vire uma
metralhadora de requisições.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from auditoria.models import AcaoAuditada, RegistroAuditoria


def _config(nome: str, padrao: int) -> int:
    return getattr(settings, nome, padrao)


def limite_atingido(
    *,
    usuario,
    objeto_tipo: str,
    limite: int,
    janela_minutos: int,
    acao: str = AcaoAuditada.CRIACAO,
) -> bool:
    """
    `True` se `usuario` já produziu `limite` ou mais eventos `acao` sobre
    `objeto_tipo` (ex.: `"ativos.movimentacao"`) nos últimos `janela_minutos`.

    Conta pela trilha automática (`auditoria/rastreamento.py`), que já
    registra toda criação/alteração de model de domínio — não é preciso
    instrumentar cada view que quer se proteger, só consultar o que a
    trilha já grava.
    """
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False

    desde = timezone.now() - timezone.timedelta(minutes=janela_minutos)
    total = RegistroAuditoria.objects.filter(
        usuario=usuario, acao=acao, objeto_tipo=objeto_tipo, criado_em__gte=desde
    ).count()
    return total >= limite


def registrar_limite_atingido(*, request, descricao: str) -> None:
    """
    Uma linha por bloqueio (não por tentativa recusada) — mesmo motivo do
    `bloqueio_tentativas` de login: quem está abusando controla o volume de
    tentativas, então logar cada uma seria o próprio vetor de inundação da
    trilha. `ACESSO_NEGADO` já existe no catálogo fechado de eventos; não é
    caso para um código novo.
    """
    from auditoria.services import registrar  # import tardio: evita ciclo

    registrar(AcaoAuditada.ACESSO_NEGADO, request=request, descricao=descricao)

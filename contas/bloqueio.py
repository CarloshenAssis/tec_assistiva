"""
Bloqueio de autenticação por excesso de tentativas.

O estado do bloqueio é *derivado da trilha de auditoria*, não de uma tabela
própria. Duas razões:

1. Fonte única de verdade — não existe a possibilidade de a trilha dizer uma
   coisa e o contador de bloqueio dizer outra, e todo bloqueio já nasce
   auditado por construção.
2. Funciona em ambiente serverless (Vercel), onde não há cache em memória
   compartilhado entre invocações. Uma implementação baseada em
   `django.core.cache` com LocMemCache seria inofensiva na prática: cada
   invocação começaria com o contador zerado.

Estratégia de janela deslizante com dois limiares distintos:

- **Por identificador** (usuário tentado): limiar baixo. É o ataque comum,
  adivinhar a senha de uma conta conhecida.
- **Por IP**: limiar bem mais alto. Um posto de saúde ou prefeitura tem
  dezenas de funcionários legítimos atrás de um único IP (NAT); usar o mesmo
  limiar dos dois lados transformaria o erro de digitação de um colega em
  negação de serviço para o setor inteiro. O limiar de IP existe para pegar
  *password spraying* (poucas tentativas em muitas contas), não digitação.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.utils import timezone

from auditoria.models import AcaoAuditada, RegistroAuditoria


def _config(nome: str, padrao: int) -> int:
    return getattr(settings, nome, padrao)


@dataclass(frozen=True)
class ResultadoBloqueio:
    """Resposta da consulta de bloqueio — o motivo é para auditoria, não para o usuário."""

    bloqueado: bool
    motivo: str = ""


def _janela_inicio():
    minutos = _config("SEGURANCA_LOGIN_JANELA_MINUTOS", 15)
    return timezone.now() - timezone.timedelta(minutes=minutos)


def _falhas_recentes(**filtros) -> int:
    return RegistroAuditoria.objects.filter(
        acao=AcaoAuditada.LOGIN_FALHA,
        criado_em__gte=_janela_inicio(),
        **filtros,
    ).count()


def esta_bloqueado(*, identificacao: str, ip: Optional[str]) -> ResultadoBloqueio:
    """
    Diz se a combinação usuário/IP está impedida de tentar autenticar agora.

    Não distingue "usuário existe" de "usuário não existe" em momento algum —
    o bloqueio é por string tentada, então a resposta não serve para enumerar
    contas válidas.
    """
    limite_id = _config("SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO", 5)
    limite_ip = _config("SEGURANCA_LOGIN_MAX_TENTATIVAS_IP", 20)

    if identificacao:
        if _falhas_recentes(usuario_identificacao__iexact=identificacao) >= limite_id:
            return ResultadoBloqueio(True, f"limite por identificação atingido ({limite_id})")

    if ip:
        if _falhas_recentes(ip=ip) >= limite_ip:
            return ResultadoBloqueio(True, f"limite por IP atingido ({limite_ip})")

    return ResultadoBloqueio(False)


def registrar_bloqueio_se_atingiu_limite(
    *, identificacao: str, ip: Optional[str], request=None
) -> bool:
    """
    Grava o evento de bloqueio **apenas na transição** para o estado bloqueado.

    Chamado logo depois de cada falha de login. Registrar a cada tentativa
    barrada seria um vetor de inundação: quem ataca controla o volume e
    poderia inflar a tabela de auditoria à vontade. Aqui cada episódio de
    bloqueio produz exatamente uma linha; o volume de tentativas subsequentes
    fica no log de acesso da borda (Vercel), que é o lugar próprio para isso.
    """
    from auditoria.services import registrar  # import tardio: evita ciclo

    limite = _config("SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO", 5)
    if not identificacao:
        return False

    # `== limite` e não `>= limite`: só a falha que cruzou a linha registra.
    if _falhas_recentes(usuario_identificacao__iexact=identificacao) != limite:
        return False

    registrar(
        AcaoAuditada.BLOQUEIO_TENTATIVAS,
        request=request,
        usuario_identificacao=identificacao,
        descricao=f"Bloqueio automático após {limite} tentativas malsucedidas",
    )
    return True


def tentativas_restantes(*, identificacao: str) -> int:
    """
    Quantas tentativas ainda cabem para esta identificação na janela atual.

    Usado apenas em teste e diagnóstico — **não** deve ser exposto na tela de
    login: informar "restam 2 tentativas" confirma para quem ataca que o
    usuário existe e que ele está no caminho certo.
    """
    limite = _config("SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO", 5)
    usadas = _falhas_recentes(usuario_identificacao__iexact=identificacao)
    return max(0, limite - usadas)

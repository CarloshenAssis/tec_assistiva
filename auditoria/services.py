"""
API de gravação da trilha de auditoria.

Todo o resto do sistema registra eventos por aqui — nunca instanciando
`RegistroAuditoria` diretamente — para que o tratamento de IP, o snapshot
do usuário e a política de resiliência fiquem em um lugar só.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any, Optional

from django.conf import settings
from django.db import models

from auditoria.models import AcaoAuditada, RegistroAuditoria

logger = logging.getLogger(__name__)

#: Limite do `user_agent` gravado. O cabeçalho é controlado pelo cliente e
#: pode vir com quilobytes de lixo; truncar evita inflar a tabela de auditoria.
_LIMITE_USER_AGENT = 255


def ip_do_cliente(request) -> Optional[str]:
    """
    IP real do cliente, considerando proxies reversos confiáveis.

    `X-Forwarded-For` é escrito pelo cliente e *complementado* por cada proxy
    no caminho, então confiar no primeiro elemento é uma falha clássica: quem
    ataca simplesmente envia `X-Forwarded-For: 1.2.3.4` e some do log (ou,
    pior, envenena o bloqueio por tentativas de outra pessoa).

    Com N proxies confiáveis à frente da aplicação, o IP autêntico é o
    N-ésimo a contar da direita — tudo à esquerda disso é texto que o cliente
    escolheu. `SEGURANCA_PROXIES_CONFIAVEIS = 0` (padrão) ignora o cabeçalho
    e usa `REMOTE_ADDR`, que é o correto para execução local/direta.
    """
    num_proxies = getattr(settings, "SEGURANCA_PROXIES_CONFIAVEIS", 0)

    if num_proxies > 0:
        encaminhados = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ips = [parte.strip() for parte in encaminhados.split(",") if parte.strip()]
        if len(ips) >= num_proxies:
            return _ip_valido_ou_none(ips[-num_proxies])

    return _ip_valido_ou_none(request.META.get("REMOTE_ADDR"))


def _ip_valido_ou_none(valor: Optional[str]) -> Optional[str]:
    """Só devolve o valor se for de fato um IP — o campo do model recusaria lixo."""
    if not valor:
        return None
    try:
        return str(ipaddress.ip_address(valor.strip()))
    except ValueError:
        return None


def _rotulo_do_objeto(objeto: Optional[models.Model]) -> tuple[str, str]:
    if objeto is None:
        return "", ""
    meta = objeto._meta
    return f"{meta.app_label}.{meta.object_name}", str(objeto.pk or "")


def registrar(
    acao: str,
    *,
    request: Any = None,
    usuario: Any = None,
    tenant: Any = None,
    objeto: Optional[models.Model] = None,
    descricao: str = "",
    envolve_dado_sensivel: bool = False,
    usuario_identificacao: str = "",
) -> Optional[RegistroAuditoria]:
    """
    Grava um evento na trilha.

    `request` é opcional para permitir auditar ações de linha de comando
    (jobs, migrações de dados). Quando informado, dele saem IP, user agent e —
    se não vierem explícitos — usuário e tenant.

    Falha de gravação **não derruba a requisição do usuário**: um problema
    momentâneo na tabela de auditoria não deve impedir um atendimento em
    andamento. O erro vai para o log da aplicação em nível ERROR, onde o
    monitoramento enxerga.
    """
    if request is not None:
        if usuario is None:
            candidato = getattr(request, "user", None)
            if candidato is not None and getattr(candidato, "is_authenticated", False):
                usuario = candidato
        if tenant is None:
            tenant = getattr(request, "tenant", None)

    objeto_tipo, objeto_id = _rotulo_do_objeto(objeto)

    if not usuario_identificacao and usuario is not None:
        usuario_identificacao = getattr(usuario, "username", "") or str(usuario)

    try:
        return RegistroAuditoria.objects.create(
            tenant=tenant,
            usuario=usuario if usuario is not None else None,
            usuario_identificacao=usuario_identificacao[:254],
            acao=acao,
            objeto_tipo=objeto_tipo,
            objeto_id=objeto_id,
            descricao=descricao[:255],
            envolve_dado_sensivel=envolve_dado_sensivel,
            ip=ip_do_cliente(request) if request is not None else None,
            user_agent=(
                request.META.get("HTTP_USER_AGENT", "")[:_LIMITE_USER_AGENT]
                if request is not None
                else ""
            ),
        )
    except Exception:  # noqa: BLE001 — resiliência deliberada, ver docstring
        logger.exception(
            "Falha ao gravar registro de auditoria (acao=%s, objeto=%s#%s)",
            acao,
            objeto_tipo,
            objeto_id,
        )
        return None


def registrar_acesso_dado_pessoal(
    request,
    objeto: models.Model,
    *,
    sensivel: bool = False,
    descricao: str = "",
) -> Optional[RegistroAuditoria]:
    """
    Atalho para o evento mais frequente: alguém abriu a ficha de um titular.

    `sensivel=True` deve ser usado quando o acesso alcança dado de saúde
    (laudo, receita médica) — é o que permite separar, num relatório de
    incidente, "viu o cadastro" de "viu o prontuário".
    """
    return registrar(
        AcaoAuditada.ACESSO_DADO_PESSOAL,
        request=request,
        objeto=objeto,
        descricao=descricao,
        envolve_dado_sensivel=sensivel,
    )

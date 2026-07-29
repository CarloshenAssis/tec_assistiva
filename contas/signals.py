"""
Auditoria automática dos eventos de autenticação.

Ligado por signal, e não dentro da view de login, de propósito: assim o
Django Admin, a API e qualquer fluxo futuro de autenticação caem na mesma
trilha sem precisar lembrar de chamar nada. É a diferença entre "auditamos o
login" e "auditamos *um* login".
"""

from __future__ import annotations

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from auditoria.models import AcaoAuditada
from auditoria.services import ip_do_cliente, registrar
from contas.bloqueio import registrar_bloqueio_se_atingiu_limite


@receiver(user_logged_in)
def _auditar_login_bem_sucedido(sender, request, user, **kwargs):
    registrar(
        AcaoAuditada.LOGIN_SUCESSO,
        request=request,
        usuario=user,
        tenant=getattr(user, "tenant", None),
    )


@receiver(user_login_failed)
def _auditar_login_malsucedido(sender, credentials, request=None, **kwargs):
    # `credentials` já chega com a senha mascarada pelo próprio Django
    # (`django.contrib.auth._clean_credentials`), então é seguro registrar o
    # identificador tentado — que é justamente o que alimenta o bloqueio.
    identificacao = ""
    if credentials:
        identificacao = str(credentials.get("username") or "")

    registrar(
        AcaoAuditada.LOGIN_FALHA,
        request=request,
        usuario_identificacao=identificacao,
        descricao="Credenciais inválidas",
    )

    # Precisa vir depois do registro acima: é essa falha que pode ter
    # cruzado o limiar.
    registrar_bloqueio_se_atingiu_limite(
        identificacao=identificacao,
        ip=ip_do_cliente(request) if request is not None else None,
        request=request,
    )


@receiver(user_logged_out)
def _auditar_logout(sender, request, user, **kwargs):
    if user is None:
        return
    registrar(
        AcaoAuditada.LOGOUT,
        request=request,
        usuario=user,
        tenant=getattr(user, "tenant", None),
    )

"""
Formulários de autenticação com bloqueio por tentativas.
"""

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from auditoria.services import ip_do_cliente
from contas.bloqueio import esta_bloqueado

#: Mensagem deliberadamente genérica e idêntica para todos os casos de
#: bloqueio. Dizer "restam N tentativas" ou "esta conta está bloqueada"
#: confirmaria a existência do usuário para quem está enumerando contas.
MENSAGEM_BLOQUEIO = (
    "Muitas tentativas de acesso a partir deste ponto. "
    "Aguarde alguns minutos antes de tentar novamente."
)


class FormularioLoginSeguro(AuthenticationForm):
    """
    `AuthenticationForm` com verificação de bloqueio antes da autenticação.

    A checagem acontece em `clean()` **antes** de `super().clean()` para que
    uma tentativa barrada nunca chegue a executar o hash da senha: além de
    poupar CPU (o PBKDF2 é caro por definição), isso impede que o tempo de
    resposta diferencie "bloqueado" de "senha errada".
    """

    #: Substitui a mensagem padrão do Django por uma que não revela nada
    #: sobre a existência da conta — e em português, já que é a que o
    #: usuário final lê.
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuário ou senha inválidos.",
        "inactive": "Usuário ou senha inválidos.",
    }

    def clean(self):
        identificacao = (self.data.get("username") or "").strip()
        ip = ip_do_cliente(self.request) if self.request is not None else None

        resultado = esta_bloqueado(identificacao=identificacao, ip=ip)
        if resultado.bloqueado:
            raise forms.ValidationError(MENSAGEM_BLOQUEIO, code="bloqueado_por_tentativas")

        return super().clean()

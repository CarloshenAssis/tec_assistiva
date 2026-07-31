"""
Senha temporária para contas criadas por um administrador (não pela própria
pessoa).

Usada tanto pelo Owner ao gerar o primeiro acesso do administrador de um
tenant (`owner/views.py::criar_administrador`) quanto por um Admin/Gestor ao
criar Gestor/Funcionário no próprio tenant (`contas/views.py::usuarios_criar`).
Em ambos os casos ninguém digita a senha da conta nova — ela é gerada,
mostrada uma única vez na tela de sucesso, e só o hash é persistido. Quem a
recebe troca por uma própria em "Alterar senha" (ver password_change).
"""

from __future__ import annotations

import secrets
import string

#: Sem `0`/`O`, `1`/`l`/`I` — visualmente idênticos ou quase em monoespaçado
#: (é assim que a senha aparece na tela de sucesso, uma única vez, pra quem
#: vai retransmitir ou redigitar de cabeça). Um caso real: usuário criado,
#: 3 tentativas de login com a senha errada — a diferença mais provável
#: entre o que foi gerado e o que foi digitado é exatamente um desses pares.
_AMBIGUOS = "0O1lI"
_ALFABETO = "".join(c for c in string.ascii_letters + string.digits if c not in _AMBIGUOS)
#: Acima do mínimo de 12 do validador de senha (settings.AUTH_PASSWORD_VALIDATORS)
#: com boa margem, já que ninguém memoriza esta — é só a ponte até a troca.
_TAMANHO = 16


def gerar_senha_temporaria() -> str:
    return "".join(secrets.choice(_ALFABETO) for _ in range(_TAMANHO))

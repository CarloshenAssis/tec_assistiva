"""
Views de conta do próprio usuário autenticado.
"""

from __future__ import annotations

from django.contrib.auth import views as auth_views

from auditoria.models import AcaoAuditada
from auditoria.services import registrar


class AlterarSenhaView(auth_views.PasswordChangeView):
    """
    `PasswordChangeView` padrão do Django, com o único acréscimo de gravar o
    evento na trilha de auditoria — troca de senha é o tipo de ação que uma
    investigação de incidente pergunta "quando foi a última vez".
    """

    def form_valid(self, form):
        resposta = super().form_valid(form)
        registrar(
            AcaoAuditada.SENHA_ALTERADA,
            request=self.request,
            usuario=self.request.user,
            tenant=getattr(self.request.user, "tenant", None),
        )
        return resposta

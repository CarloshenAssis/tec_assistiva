from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from contas.forms import FormularioLoginSeguro
from contas.views import AlterarSenhaView
from core.views_saude import saude

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="app:dashboard", permanent=False)),
    # Caminho do admin configurável por ambiente. Manter `/admin/` em
    # produção é entregar o alvo pronto: varredores automatizados batem nesse
    # caminho por padrão, e cada tentativa consome o limite de bloqueio de
    # contas legítimas. Ver DJANGO_ADMIN_URL.
    path(settings.ADMIN_URL, admin.site.urls),
    path("owner/", include("owner.urls")),
    path("saude/", saude, name="saude"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=FormularioLoginSeguro,
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Recuperação de senha. Antes desta rota, a única forma de recuperar
    # acesso era alterar o hash direto no banco — operação que exige acesso
    # privilegiado à base de produção e não deixa trilha de quem pediu.
    path(
        "accounts/senha/recuperar/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.txt",
            subject_template_name="registration/password_reset_subject.txt",
            success_url="/accounts/senha/recuperar/enviado/",
        ),
        name="password_reset",
    ),
    path(
        "accounts/senha/recuperar/enviado/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "accounts/senha/redefinir/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/accounts/senha/redefinir/concluido/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/senha/redefinir/concluido/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    # Troca de senha para quem já está autenticado — antes disso, a única
    # forma de trocar a própria senha era pedir para alguém alterar o hash
    # direto no banco, ou passar pelo fluxo de "esqueci minha senha" por
    # e-mail. `PasswordChangeView` já exige a senha atual, o que a
    # `PasswordResetConfirmView` (via link de e-mail) não faz — mais forte
    # para quem só quer trocar por rotina, sem ter esquecido nada.
    path(
        "accounts/senha/alterar/",
        AlterarSenhaView.as_view(
            template_name="registration/password_change_form.html",
            success_url="/accounts/senha/alterar/concluido/",
        ),
        name="password_change",
    ),
    path(
        "accounts/senha/alterar/concluido/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path("app/", include("core.urls")),
]

# Em produção a mídia NÃO é servida por aqui. Arquivo enviado por usuário
# inclui laudo e receita médica (dado pessoal sensível) e só sai pela view
# autenticada e com escopo de tenant — ver core/arquivos.py e
# beneficiarios.views.baixar_documento.

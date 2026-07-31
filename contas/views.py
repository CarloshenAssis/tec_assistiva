"""
Views de conta do próprio usuário autenticado, gestão de usuários do tenant
e consulta de auditoria com escopo no próprio tenant.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from ativos.domain.acoes import NIVEL_GESTOR
from auditoria.models import AcaoAuditada
from auditoria.selectors import filtrar_registros, listar_registros
from auditoria.services import registrar
from contas.forms import CriarUsuarioForm
from contas.models import Usuario
from contas.senhas import gerar_senha_temporaria
from core.decorators import nivel_hierarquico, tenant_required
from core.paginacao import paginar
from core.relatorios_export import exportar_auditoria_csv


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


def _exigir_gestor_ou_admin(request) -> None:
    if nivel_hierarquico(request) < NIVEL_GESTOR:
        raise PermissionDenied("Somente Gestor ou Admin podem gerenciar usuários.")


@tenant_required
def usuarios_lista(request):
    _exigir_gestor_ou_admin(request)
    usuarios_qs = Usuario.objects.filter(tenant=request.tenant).order_by("username")
    pagina = paginar(request, usuarios_qs)
    # Anotado aqui (não recalculado no template) porque `pode_gerenciar`
    # recebe o outro usuário como argumento — um template não chama método
    # com parâmetro. Sem isto, o botão "Desativar" aparecia para qualquer
    # usuário (só escondido para o próprio logado), inclusive um Gestor
    # vendo o botão no Admin: clicar nele já era bloqueado no servidor
    # (`pode_gerenciar` nega, 403), mas o botão não deveria nem aparecer.
    usuarios = list(pagina.object_list)
    for usuario in usuarios:
        usuario.pode_ser_gerenciado = request.user.pode_gerenciar(usuario)
    return render(
        request,
        "contas/usuarios_lista.html",
        {"nav_atual": "usuarios", "usuarios": usuarios, "pagina": pagina},
    )


@tenant_required
def usuarios_criar(request):
    """
    Cria Gestor/Funcionário no tenant de quem está logado.

    O próprio administrador (ou Gestor, dentro do que lhe é permitido) gera
    o acesso — o Owner da plataforma só cria o primeiro Admin de cada
    contrato (ver owner/views.py::criar_administrador); daqui em diante o
    provisionamento de usuário é interno ao tenant.
    """
    _exigir_gestor_ou_admin(request)
    nivel_criador = nivel_hierarquico(request)

    if request.method == "POST":
        form = CriarUsuarioForm(request.POST, nivel_criador=nivel_criador)
        if form.is_valid():
            senha = gerar_senha_temporaria()
            usuario = Usuario.objects.create(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                password=make_password(senha),
                tenant=request.tenant,
                papel=form.cleaned_data["papel"],
                is_active=True,
            )
            usuario.unidades.set(form.cleaned_data["unidades"])
            registrar(
                AcaoAuditada.CRIACAO,
                request=request,
                tenant=request.tenant,
                objeto=usuario,
                descricao=f"Usuário criado por {request.user.get_username()}",
            )
            return render(
                request,
                "contas/usuario_criado.html",
                {"nav_atual": "usuarios", "usuario": usuario, "senha": senha},
            )
    else:
        form = CriarUsuarioForm(nivel_criador=nivel_criador)

    return render(
        request,
        "contas/usuarios_form.html",
        {"nav_atual": "usuarios", "form": form, "titulo": "Novo usuário"},
    )


@tenant_required
def usuarios_alternar_ativo(request, pk):
    """Ativa/desativa um usuário do próprio tenant. Exige POST (revoga acesso de terceiro)."""
    _exigir_gestor_ou_admin(request)
    if request.method != "POST":
        raise PermissionDenied("Esta operação exige confirmação (POST).")

    usuario_alvo = get_object_or_404(Usuario, pk=pk, tenant=request.tenant)
    if not request.user.pode_gerenciar(usuario_alvo):
        raise PermissionDenied("Você não tem permissão para gerenciar este usuário.")
    if usuario_alvo.pk == request.user.pk:
        raise PermissionDenied("Não é possível desativar a própria conta por aqui.")

    usuario_alvo.is_active = not usuario_alvo.is_active
    usuario_alvo.save()
    messages.success(
        request,
        f"Usuário {usuario_alvo.get_username()} {'reativado' if usuario_alvo.is_active else 'desativado'}.",
    )
    return redirect("app:usuarios:lista")


@tenant_required
def auditoria_lista(request):
    """Trilha de auditoria restrita ao próprio tenant — mesmo seletor da visão cross-tenant do Owner."""
    _exigir_gestor_ou_admin(request)
    pagina = listar_registros(
        tenant_id=request.tenant.pk,
        acao=request.GET.get("acao", ""),
        usuario=request.GET.get("usuario", ""),
        somente_sensivel=request.GET.get("sensivel") == "1",
        pagina=request.GET.get("pagina"),
        por_pagina=request.GET.get("por_pagina"),
    )
    return render(
        request,
        "contas/auditoria.html",
        {
            "nav_atual": "auditoria",
            "pagina": pagina,
            "acoes": AcaoAuditada.choices,
            "acao_filtro": request.GET.get("acao", ""),
            "usuario_filtro": request.GET.get("usuario", ""),
            "somente_sensivel": request.GET.get("sensivel") == "1",
        },
    )


@tenant_required
def auditoria_exportar(request):
    """Mesmo filtro de `auditoria_lista`, em CSV e sem paginar — ver owner/views.py::auditoria_exportar."""
    _exigir_gestor_ou_admin(request)
    registros_qs = filtrar_registros(
        tenant_id=request.tenant.pk,
        acao=request.GET.get("acao", ""),
        usuario=request.GET.get("usuario", ""),
        somente_sensivel=request.GET.get("sensivel") == "1",
    )
    return exportar_auditoria_csv(registros_qs, incluir_tenant=False)

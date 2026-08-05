"""
Área da plataforma (Owner) — controle de contratos (Tenants) e geração do
primeiro acesso do administrador de cada B2G/B2B.

Todo acesso aqui passa por `owner_required`: só equipe Ciclartech
(`is_platform_staff`) entra. É também o único app (além do mixin de admin em
`core/admin.py`) autorizado a chamar `Manager.all_tenants()` — reforçado por
`core/tests/test_architecture.py`.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.models import AcaoAuditada
from auditoria.selectors import filtrar_registros, listar_registros
from auditoria.services import registrar
from contas.models import Papel, Usuario
from contas.senhas import gerar_senha_temporaria
from core import features
from core.models import Modulo, Tenant
from core.paginacao import paginar
from core.relatorios_export import exportar_auditoria_csv
from owner.decorators import owner_required
from owner.forms import CriarAdministradorForm, TenantForm


@owner_required
def dashboard(request):
    """Lista todos os contratos (tenants) da plataforma, paginados."""
    tenants_qs = Tenant.objects.all().order_by("nome")
    pagina = paginar(request, tenants_qs)
    return render(
        request,
        "owner/dashboard.html",
        {
            "nav_atual": "owner_dashboard",
            "tenants": pagina.object_list,
            "pagina": pagina,
            "total_tenants": tenants_qs.count(),
            "total_ativos": tenants_qs.filter(ativo=True).count(),
        },
    )


@owner_required
def criar_tenant(request):
    """Provisiona um novo contrato (tenant) na plataforma."""
    if request.method == "POST":
        form = TenantForm(request.POST)
        if form.is_valid():
            tenant = form.save()
            messages.success(request, f"Contrato {tenant.nome} criado.")
            return redirect("owner:tenant_detalhe", pk=tenant.pk)
    else:
        form = TenantForm(initial={"ativo": True})
    return render(
        request,
        "owner/tenant_form.html",
        {"nav_atual": "owner_dashboard", "form": form, "titulo": "Novo contrato"},
    )


@owner_required
def editar_tenant(request, pk):
    """Atualiza os dados cadastrais de um contrato (tenant) existente."""
    tenant = get_object_or_404(Tenant, pk=pk)
    if request.method == "POST":
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f"Contrato {tenant.nome} atualizado.")
            return redirect("owner:tenant_detalhe", pk=tenant.pk)
    else:
        form = TenantForm(instance=tenant)
    return render(
        request,
        "owner/tenant_form.html",
        {"nav_atual": "owner_dashboard", "form": form, "titulo": f"Editar {tenant.nome}"},
    )


@owner_required
def tenant_detalhe(request, pk):
    """Mostra os dados do contrato, seus usuários e os módulos habilitados."""
    tenant = get_object_or_404(Tenant, pk=pk)
    # `Usuario.objects` já é cross-tenant por padrão — ver owner/forms.py.
    usuarios = Usuario.objects.filter(tenant=tenant).order_by("username")
    return render(
        request,
        "owner/tenant_detalhe.html",
        {
            "nav_atual": "owner_dashboard",
            "tenant": tenant,
            "usuarios": usuarios,
            "modulos": features.modulos_do_tenant(tenant),
        },
    )


@owner_required
def alternar_modulo(request, pk):
    """
    Liga/desliga um módulo para um tenant específico — sobrepõe o padrão do
    segmento (`core.features._MODULOS_PADRAO_POR_SEGMENTO`).

    Exige POST: muda o que a organização inteira enxerga na próxima
    requisição (ex.: campos de contrato de locação aparecerem/sumirem).
    """
    if request.method != "POST":
        raise PermissionDenied("Esta operação exige confirmação (POST).")
    tenant = get_object_or_404(Tenant, pk=pk)
    modulo = get_object_or_404(Modulo, codigo=request.POST.get("modulo"))

    # Estado atual (padrão do segmento OU override já existente) — o toggle
    # sempre inverte o que está em vigor agora, nunca "liga na marra".
    ativo_agora = features.modulo_habilitado(tenant, modulo.codigo)
    features.definir_modulo(tenant, modulo.codigo, not ativo_agora)

    registrar(
        AcaoAuditada.ALTERACAO,
        request=request,
        tenant=tenant,
        objeto=tenant,
        descricao=f"Módulo \"{modulo.nome}\" {'desligado' if ativo_agora else 'ligado'}",
    )

    messages.success(
        request,
        f"Módulo \"{modulo.nome}\" {'desligado' if ativo_agora else 'ligado'} para {tenant.nome}.",
    )
    return redirect("owner:tenant_detalhe", pk=tenant.pk)


@owner_required
def alternar_tenant_ativo(request, pk):
    """Suspende/reativa o contrato. Exige POST: afeta o acesso de todo mundo nele."""
    if request.method != "POST":
        raise PermissionDenied("Esta operação exige confirmação (POST).")
    tenant = get_object_or_404(Tenant, pk=pk)
    tenant.ativo = not tenant.ativo
    tenant.save()
    messages.success(request, f"Contrato {'reativado' if tenant.ativo else 'suspenso'}.")
    return redirect("owner:tenant_detalhe", pk=tenant.pk)


@owner_required
def criar_administrador(request, tenant_id):
    """
    Gera o primeiro acesso do administrador do contrato B2G/B2B.

    A senha é gerada aleatoriamente e mostrada UMA ÚNICA VEZ na tela de
    sucesso — dali em diante só o hash existe, igual a qualquer senha. É
    esse administrador quem depois cria Gestor/Funcionário dentro do próprio
    tenant (ver contas/views.py::usuarios_criar) — o Owner nunca cria usuário
    operacional diretamente, só o primeiro Admin de cada contrato.
    """
    tenant = get_object_or_404(Tenant, pk=tenant_id)

    if request.method == "POST":
        form = CriarAdministradorForm(request.POST)
        if form.is_valid():
            senha = gerar_senha_temporaria()
            usuario = Usuario.objects.create(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                password=make_password(senha),
                tenant=tenant,
                papel=Papel.objects.get(codigo=Papel.Codigo.ADMIN),
                is_active=True,
            )
            registrar(
                AcaoAuditada.CRIACAO,
                request=request,
                tenant=tenant,
                objeto=usuario,
                descricao="Primeiro acesso de administrador gerado pela plataforma",
            )
            return render(
                request,
                "owner/administrador_criado.html",
                {"nav_atual": "owner_dashboard", "tenant": tenant, "usuario": usuario, "senha": senha},
            )
    else:
        form = CriarAdministradorForm()

    return render(
        request,
        "owner/criar_administrador.html",
        {"nav_atual": "owner_dashboard", "tenant": tenant, "form": form},
    )


@owner_required
def auditoria(request):
    """
    Trilha de auditoria cross-tenant — visão da plataforma inteira.

    Usa o mesmo seletor que alimenta a versão por tenant do Admin/Gestor
    (contas/views.py::auditoria_lista), só que sem o filtro de tenant.
    """
    tenant_filtro = request.GET.get("tenant") or None
    pagina = listar_registros(
        tenant_id=tenant_filtro,
        acao=request.GET.get("acao", ""),
        usuario=request.GET.get("usuario", ""),
        somente_sensivel=request.GET.get("sensivel") == "1",
        pagina=request.GET.get("pagina"),
        por_pagina=request.GET.get("por_pagina"),
    )
    return render(
        request,
        "owner/auditoria.html",
        {
            "nav_atual": "owner_auditoria",
            "pagina": pagina,
            "acoes": AcaoAuditada.choices,
            "tenants": Tenant.objects.all().order_by("nome"),
            "tenant_filtro": int(tenant_filtro) if tenant_filtro else None,
            "acao_filtro": request.GET.get("acao", ""),
            "usuario_filtro": request.GET.get("usuario", ""),
            "somente_sensivel": request.GET.get("sensivel") == "1",
        },
    )


@owner_required
def auditoria_exportar(request):
    """
    Mesmo filtro da tela (`auditoria`, acima), mas em CSV e sem paginar —
    exporta todos os registros do filtro aplicado, não só a página em tela.
    """
    tenant_filtro = request.GET.get("tenant") or None
    registros_qs = filtrar_registros(
        tenant_id=tenant_filtro,
        acao=request.GET.get("acao", ""),
        usuario=request.GET.get("usuario", ""),
        somente_sensivel=request.GET.get("sensivel") == "1",
    )
    return exportar_auditoria_csv(registros_qs, incluir_tenant=True)

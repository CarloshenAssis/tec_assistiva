"""
Views do app `ativos` — camada de apresentação "magra" (docs/ESPECIFICACAO_TECNICA.md §3.2):
toda regra de negócio vive em `ativos.services`/`ativos.domain`, aqui só
orquestramos formulários, sessão do wizard e redirecionamentos.
"""

import io

import qrcode
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ativos import services
from ativos.domain.acoes import NIVEL_GESTOR, acoes_disponiveis
from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.domain.exceptions import DominioAtivoError
from ativos.forms import (
    CHECKLIST_ITENS_DEVOLUCAO,
    CHECKLIST_ITENS_EMPRESTIMO,
    AtivoForm,
    DarBaixaForm,
    EnviarManutencaoForm,
    ObservacaoForm,
    RenovarForm,
)
from ativos.models import Ativo, CategoriaAtivo, Movimentacao
from beneficiarios.models import Beneficiario
from core.decorators import nivel_hierarquico, tenant_required

TABS_FICHA = [
    ("informacoes", "Informações"),
    ("timeline", "Timeline"),
    ("movimentacoes", "Movimentações"),
    ("fotos", "Fotos"),
    ("manutencoes", "Manutenções"),
    ("qrcode", "QR Code"),
    ("documentos", "Documentos"),
]


@tenant_required
def lista(request):
    categoria_filtro = request.GET.get("categoria")
    busca = request.GET.get("q", "").strip()

    resumo_categorias = []
    for categoria in CategoriaAtivo.objects.all():
        itens = Ativo.objects.filter(categoria=categoria)
        resumo_categorias.append(
            {
                "id": categoria.id,
                "nome": categoria.nome,
                "total": itens.count(),
                "disponiveis": itens.filter(status=StatusAtivo.DISPONIVEL.value).count(),
                "emprestados": itens.filter(status=StatusAtivo.EMPRESTADO.value).count(),
            }
        )

    ativos_qs = Ativo.objects.select_related("categoria", "unidade").all()
    if categoria_filtro:
        ativos_qs = ativos_qs.filter(categoria_id=categoria_filtro)
    if busca:
        ativos_qs = ativos_qs.filter(
            Q(patrimonio__icontains=busca)
            | Q(numero_serie__icontains=busca)
            | Q(fabricante__icontains=busca)
        )

    return render(
        request,
        "ativos/lista.html",
        {
            "nav_atual": "ativos",
            "resumo_categorias": resumo_categorias,
            "ativos": ativos_qs[:200],
            "categoria_filtro": int(categoria_filtro) if categoria_filtro else None,
            "busca": busca,
        },
    )


@tenant_required
def criar(request):
    if nivel_hierarquico(request) < NIVEL_GESTOR:
        raise PermissionDenied("Somente Gestor ou Admin podem cadastrar ativos.")
    if request.method == "POST":
        form = AtivoForm(request.POST)
        if form.is_valid():
            ativo = form.save(commit=False)
            ativo.tenant = request.tenant
            ativo.save()
            messages.success(request, f"Ativo {ativo.patrimonio} cadastrado com sucesso.")
            return redirect("app:ativos:ficha", pk=ativo.pk)
    else:
        form = AtivoForm()
    return render(request, "ativos/form.html", {"nav_atual": "ativos", "form": form, "titulo": "Novo Ativo"})


@tenant_required
def editar(request, pk):
    if nivel_hierarquico(request) < NIVEL_GESTOR:
        raise PermissionDenied("Somente Gestor ou Admin podem editar ativos.")
    ativo = get_object_or_404(Ativo, pk=pk)
    if request.method == "POST":
        form = AtivoForm(request.POST, instance=ativo)
        if form.is_valid():
            form.save()
            messages.success(request, "Ativo atualizado.")
            return redirect("app:ativos:ficha", pk=ativo.pk)
    else:
        form = AtivoForm(instance=ativo)
    return render(
        request,
        "ativos/form.html",
        {"nav_atual": "ativos", "form": form, "titulo": f"Editar {ativo.patrimonio}", "ativo": ativo},
    )


@tenant_required
def ficha(request, pk):
    ativo = get_object_or_404(
        Ativo.objects.select_related("categoria", "subcategoria", "unidade", "fornecedor"), pk=pk
    )
    aba = request.GET.get("aba", "informacoes")
    acoes = acoes_disponiveis(ativo.status_enum, nivel_hierarquico=nivel_hierarquico(request))
    acoes = _preparar_acoes_para_template(ativo, acoes, origem="ficha")

    contexto = {"nav_atual": "ativos", "ativo": ativo, "aba": aba, "tabs": TABS_FICHA, "acoes": acoes}

    if aba in ("timeline", "movimentacoes"):
        contexto["movimentacoes"] = ativo.movimentacoes.select_related("usuario").all()
    if aba == "fotos":
        contexto["fotos_cadastro"] = ativo.fotos.all()
        ultimo_emprestimo = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.EMPRESTIMO)
        ultima_devolucao = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.DEVOLUCAO)
        ultimo_envio_manutencao = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.MANUTENCAO)
        ultimo_retorno_manutencao = Movimentacao.objects.mais_recente_do_tipo(
            ativo, TipoMovimentacao.RETORNO_MANUTENCAO
        )
        contexto["fotos_entrega"] = ultimo_emprestimo.fotos.all() if ultimo_emprestimo else []
        contexto["fotos_devolucao"] = ultima_devolucao.fotos.all() if ultima_devolucao else []
        contexto["fotos_envio_manutencao"] = (
            ultimo_envio_manutencao.fotos.all() if ultimo_envio_manutencao else []
        )
        contexto["fotos_retorno_manutencao"] = (
            ultimo_retorno_manutencao.fotos.all() if ultimo_retorno_manutencao else []
        )
    if aba == "manutencoes":
        contexto["manutencoes"] = ativo.movimentacoes.filter(
            tipo=TipoMovimentacao.MANUTENCAO.value
        ).select_related("detalhe_manutencao")

    return render(request, "ativos/ficha.html", contexto)


def _contexto_por_status(ativo):
    contexto = {}
    status = ativo.status_enum
    if status == StatusAtivo.EMPRESTADO:
        mov = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.EMPRESTIMO)
        if mov is not None and hasattr(mov, "detalhe_emprestimo"):
            contexto["detalhe_emprestimo"] = mov.detalhe_emprestimo
    elif status == StatusAtivo.MANUTENCAO:
        mov = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.MANUTENCAO)
        if mov is not None and hasattr(mov, "detalhe_manutencao"):
            contexto["detalhe_manutencao"] = mov.detalhe_manutencao
    contexto["ultima_movimentacao"] = ativo.movimentacoes.first()
    return contexto


@tenant_required
def resolver_qr(request, token):
    """
    Modo "Operação por QR Code" — docs/PLANO_DOMINIO_ATIVOS.md §3.4.

    Se o token não pertence ao tenant corrente (ou não existe), a resposta
    é idêntica ("não encontrado") — nunca revelamos que o ativo existe em
    outro tenant (defesa em profundidade, mesmo princípio de
    docs/PLANO_DOMINIO_ATIVOS.md §3.2).
    """
    ativo = Ativo.objects.select_related("categoria", "unidade").filter(qr_token=token).first()
    if ativo is None:
        return render(request, "ativos/quick_panel_nao_encontrado.html", {"nav_atual": "scan"}, status=404)

    acoes = acoes_disponiveis(ativo.status_enum, nivel_hierarquico=nivel_hierarquico(request))
    acoes = _preparar_acoes_para_template(ativo, acoes, origem="quick_panel")
    contexto = {"nav_atual": "scan", "ativo": ativo, "acoes": acoes, **_contexto_por_status(ativo)}
    return render(request, "ativos/quick_panel.html", contexto)


@tenant_required
def scan(request):
    """
    Fallback de entrada manual do código/patrimônio — a leitura por câmera
    (biblioteca client-side) é um incremento posterior sobre esta mesma
    rota de resolução (`resolver_qr`), que já é o backend completo do
    fluxo de QR Code.
    """
    if request.method == "POST":
        codigo = request.POST.get("codigo", "").strip()
        ativo = Ativo.objects.filter(qr_token=codigo).first() or Ativo.objects.filter(
            patrimonio__iexact=codigo
        ).first()
        if ativo is None:
            messages.error(request, "Nenhum ativo encontrado para esse código.")
            return redirect("app:ativos:scan")
        return redirect("app:ativos:resolver_qr", token=ativo.qr_token)
    return render(request, "ativos/scan.html", {"nav_atual": "scan"})


ACOES_SIMPLES = {
    "reservar": lambda ativo, usuario: services.reservar(ativo, usuario),
    "cancelar_reserva": lambda ativo, usuario: services.cancelar_reserva(ativo, usuario),
    "concluir_higienizacao": lambda ativo, usuario: services.concluir_higienizacao(ativo, usuario),
    "finalizar_manutencao": lambda ativo, usuario: services.retornar_manutencao(ativo, usuario),
    "reativar": lambda ativo, usuario: services.reativar(ativo, usuario),
}

ACOES_COM_FORM = {
    "enviar_manutencao": EnviarManutencaoForm,
    "dar_baixa": DarBaixaForm,
    "renovar": RenovarForm,
    "registrar_recuperacao": ObservacaoForm,
}


def _url_redirecionamento(codigo, ativo):
    if codigo in ("emprestar", "confirmar_emprestimo"):
        return f"{reverse('app:ativos:wizard_emprestimo')}?ativo={ativo.pk}"
    if codigo == "receber_devolucao":
        return f"{reverse('app:ativos:devolucao')}?q={ativo.patrimonio}"
    return None


_ACOES_LINK_DIRETO = {
    "editar": lambda ativo: reverse("app:ativos:editar", args=[ativo.pk]),
    "ver_historico": lambda ativo: "?aba=timeline",
    "ver_timeline": lambda ativo: "?aba=timeline",
    "ver_fotos": lambda ativo: "?aba=fotos",
}


def _preparar_acoes_para_template(ativo, acoes, origem):
    """
    Transforma a saída de `AcoesDisponiveis` (dataclasses de domínio) em
    algo que o template pode renderizar sem embutir lógica de roteamento
    no HTML: cada ação já chega com o tipo certo de controle (link de
    navegação vs. formulário POST) e a URL resolvida.
    """
    preparadas = []
    for acao in acoes:
        if acao.codigo in _ACOES_LINK_DIRETO:
            preparadas.append(
                {"codigo": acao.codigo, "rotulo": acao.rotulo, "tipo": "link", "url": _ACOES_LINK_DIRETO[acao.codigo](ativo)}
            )
            continue

        url_redirect = _url_redirecionamento(acao.codigo, ativo)
        if url_redirect or acao.codigo in ACOES_COM_FORM:
            url = url_redirect or reverse("app:ativos:executar_acao", args=[ativo.pk, acao.codigo])
            separador = "&" if "?" in url else "?"
            preparadas.append(
                {"codigo": acao.codigo, "rotulo": acao.rotulo, "tipo": "link", "url": f"{url}{separador}origem={origem}"}
            )
            continue

        preparadas.append(
            {
                "codigo": acao.codigo,
                "rotulo": acao.rotulo,
                "tipo": "form",
                "url": reverse("app:ativos:executar_acao", args=[ativo.pk, acao.codigo]),
            }
        )
    return preparadas


def _executar_acao_com_form(codigo, ativo, usuario, dados):
    if codigo == "enviar_manutencao":
        services.enviar_manutencao(
            ativo, usuario, motivo=dados["motivo"], fornecedor=dados.get("fornecedor"), valor=dados.get("valor")
        )
    elif codigo == "dar_baixa":
        services.dar_baixa(ativo, usuario, motivo=dados["motivo"])
    elif codigo == "renovar":
        services.renovar(ativo, usuario, novo_prazo_dias=dados["novo_prazo_dias"])
    elif codigo == "registrar_recuperacao":
        services.registrar_recuperacao(ativo, usuario, observacoes=dados.get("observacoes", ""))


def _redirecionar_pos_acao(ativo, origem):
    if origem == "quick_panel":
        return redirect("app:ativos:resolver_qr", token=ativo.qr_token)
    if origem == "manutencao":
        return redirect("app:ativos:manutencao_lista")
    return redirect("app:ativos:ficha", pk=ativo.pk)


@tenant_required
def executar_acao(request, pk, codigo):
    """
    Único ponto de entrada para mudar o estado de um Ativo a partir da UI —
    a lista de ações permitidas vem sempre de `AcoesDisponiveis`
    (docs/PLANO_DOMINIO_ATIVOS.md §5.3), nunca de um botão hardcoded por
    tela: a ficha, o painel de QR Code e (futuramente) a API chamam
    exatamente esta mesma verificação.
    """
    ativo = get_object_or_404(Ativo, pk=pk)
    acoes_permitidas = {
        a.codigo: a for a in acoes_disponiveis(ativo.status_enum, nivel_hierarquico=nivel_hierarquico(request))
    }

    url_redirect = _url_redirecionamento(codigo, ativo)
    if url_redirect and codigo in acoes_permitidas:
        return redirect(url_redirect)

    if codigo not in acoes_permitidas:
        raise PermissionDenied("Ação não disponível para o estado atual do ativo ou para o seu perfil.")

    origem = request.GET.get("origem") or request.POST.get("origem") or "ficha"

    if codigo in ACOES_COM_FORM:
        FormClass = ACOES_COM_FORM[codigo]
        if request.method == "POST":
            form = FormClass(request.POST)
            if form.is_valid():
                try:
                    _executar_acao_com_form(codigo, ativo, request.user, form.cleaned_data)
                except DominioAtivoError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Ação registrada com sucesso.")
                return _redirecionar_pos_acao(ativo, origem)
        else:
            form = FormClass()
        return render(
            request,
            "ativos/acao_form.html",
            {
                "nav_atual": "ativos",
                "ativo": ativo,
                "form": form,
                "acao": acoes_permitidas[codigo],
                "origem": origem,
            },
        )

    if request.method != "POST":
        raise PermissionDenied("Esta ação exige confirmação (POST).")

    try:
        ACOES_SIMPLES[codigo](ativo, request.user)
    except DominioAtivoError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Ação registrada com sucesso.")
    return _redirecionar_pos_acao(ativo, origem)


def _passo_wizard_emprestimo(wizard: dict) -> int:
    if not wizard.get("beneficiario_id"):
        return 1
    if not wizard.get("ativo_id"):
        return 2
    if not wizard.get("prazo_dias"):
        return 3
    return 4


@tenant_required
def wizard_emprestimo(request):
    """
    Wizard de 5 passos do protótipo original, com os passos 4 (checklist +
    fotos + assinatura) e 5 (revisar + confirmar) combinados numa única
    página/POST: o upload da foto do termo assinado não pode ser mantido
    entre requisições via sessão, então o envio final acontece no mesmo
    POST que grava o empréstimo — ver docs/PLANO_DOMINIO_ATIVOS.md §5.3/§6.
    """
    wizard = request.session.get("wizard_emprestimo", {})

    ativo_param = request.GET.get("ativo")
    if ativo_param and not wizard.get("ativo_id") and _passo_wizard_emprestimo(wizard) <= 2:
        wizard["ativo_id_sugerido"] = int(ativo_param)

    if request.method == "POST":
        acao = request.POST.get("wizard_acao")

        if acao == "reiniciar":
            request.session.pop("wizard_emprestimo", None)
            return redirect("app:ativos:wizard_emprestimo")

        if acao == "voltar":
            if wizard.get("prazo_dias") is not None:
                wizard.pop("prazo_dias", None)
            elif wizard.get("ativo_id") is not None:
                wizard.pop("ativo_id", None)
            elif wizard.get("beneficiario_id") is not None:
                wizard.pop("beneficiario_id", None)
            request.session["wizard_emprestimo"] = wizard
            return redirect("app:ativos:wizard_emprestimo")

        if acao == "selecionar_beneficiario":
            wizard["beneficiario_id"] = int(request.POST["beneficiario_id"])
        elif acao == "selecionar_ativo":
            wizard["ativo_id"] = int(request.POST["ativo_id"])
        elif acao == "definir_prazo":
            wizard["prazo_dias"] = int(request.POST["prazo_dias"])
        elif acao == "confirmar":
            beneficiario = get_object_or_404(Beneficiario, pk=wizard["beneficiario_id"])
            ativo = get_object_or_404(Ativo, pk=wizard["ativo_id"])
            checklist = {
                chave: (f"checklist_{chave}" in request.POST) for chave, _ in CHECKLIST_ITENS_EMPRESTIMO
            }
            arquivo = request.FILES.get("assinatura_arquivo")
            try:
                movimentacao = services.emprestar(
                    ativo,
                    beneficiario,
                    usuario=request.user,
                    prazo_dias=wizard["prazo_dias"],
                    checklist=checklist,
                    assinatura_arquivo=arquivo,
                )
            except DominioAtivoError as exc:
                messages.error(request, str(exc))
                return redirect("app:ativos:wizard_emprestimo")
            request.session.pop("wizard_emprestimo", None)
            return render(
                request,
                "ativos/wizard_emprestimo_sucesso.html",
                {
                    "nav_atual": "emprestimo",
                    "ativo": ativo,
                    "beneficiario": beneficiario,
                    "movimentacao": movimentacao,
                },
            )

        request.session["wizard_emprestimo"] = wizard
        return redirect("app:ativos:wizard_emprestimo")

    passo = _passo_wizard_emprestimo(wizard)
    contexto = {"nav_atual": "emprestimo", "passo": passo}

    if passo == 1:
        busca = request.GET.get("q", "")
        contexto["busca"] = busca
        contexto["resultados"] = (
            Beneficiario.objects.filter(Q(nome__icontains=busca) | Q(cpf__icontains=busca))[:15]
            if busca
            else []
        )
    elif passo == 2:
        contexto["beneficiario"] = get_object_or_404(Beneficiario, pk=wizard["beneficiario_id"])
        busca = request.GET.get("q", "")
        contexto["busca"] = busca
        qs = Ativo.objects.filter(status=StatusAtivo.DISPONIVEL.value).select_related("categoria")
        if busca:
            qs = qs.filter(Q(patrimonio__icontains=busca) | Q(categoria__nome__icontains=busca))
        contexto["resultados"] = qs[:15]
        contexto["ativo_sugerido_id"] = wizard.get("ativo_id_sugerido")
    elif passo == 3:
        contexto["ativo"] = get_object_or_404(Ativo, pk=wizard["ativo_id"])
        contexto["beneficiario"] = get_object_or_404(Beneficiario, pk=wizard["beneficiario_id"])
    elif passo == 4:
        contexto["ativo"] = get_object_or_404(Ativo, pk=wizard["ativo_id"])
        contexto["beneficiario"] = get_object_or_404(Beneficiario, pk=wizard["beneficiario_id"])
        contexto["prazo_dias"] = wizard.get("prazo_dias")
        contexto["checklist_itens"] = CHECKLIST_ITENS_EMPRESTIMO

    return render(request, "ativos/wizard_emprestimo.html", contexto)


@tenant_required
def devolucao(request):
    busca = (request.GET.get("q") or request.POST.get("q") or "").strip()
    ativo = None
    detalhe_emprestimo = None
    dias_em_posse = None

    if busca:
        ativo = Ativo.objects.filter(
            Q(patrimonio__iexact=busca) | Q(qr_token=busca), status=StatusAtivo.EMPRESTADO.value
        ).first()
        if ativo is None:
            mov = (
                Movimentacao.objects.filter(
                    tipo=TipoMovimentacao.EMPRESTIMO.value, ativo__status=StatusAtivo.EMPRESTADO.value
                )
                .filter(
                    Q(detalhe_emprestimo__beneficiario__nome__icontains=busca)
                    | Q(detalhe_emprestimo__beneficiario__cpf__icontains=busca)
                )
                .select_related("ativo")
                .order_by("-data_hora")
                .first()
            )
            if mov is not None:
                ativo = mov.ativo
        if ativo is not None:
            mov = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.EMPRESTIMO)
            if mov is not None and hasattr(mov, "detalhe_emprestimo"):
                detalhe_emprestimo = mov.detalhe_emprestimo
                dias_em_posse = (timezone.now().date() - mov.data_hora.date()).days

    if request.method == "POST" and request.POST.get("confirmar"):
        ativo_confirmado = get_object_or_404(Ativo, pk=request.POST.get("ativo_id"))
        destino = StatusAtivo(request.POST.get("destino"))
        checklist = {
            chave: (f"checklist_{chave}" in request.POST) for chave, _ in CHECKLIST_ITENS_DEVOLUCAO
        }
        observacoes = request.POST.get("observacoes", "")
        try:
            movimentacao = services.devolver(
                ativo_confirmado,
                usuario=request.user,
                destino=destino,
                observacoes=observacoes,
                checklist=checklist,
            )
            foto = request.FILES.get("foto")
            if foto:
                services.anexar_foto(movimentacao, foto, tipo="frontal")
        except DominioAtivoError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Devolução registrada — {ativo_confirmado.patrimonio} marcado como {destino.rotulo}.",
            )
            return redirect("app:ativos:devolucao")

    return render(
        request,
        "ativos/devolucao.html",
        {
            "nav_atual": "devolucao",
            "busca": busca,
            "ativo": ativo,
            "dias_em_posse": dias_em_posse,
            "detalhe_emprestimo": detalhe_emprestimo,
            "checklist_itens": CHECKLIST_ITENS_DEVOLUCAO,
        },
    )


@tenant_required
def qrcode_imagem(request, pk):
    ativo = get_object_or_404(Ativo, pk=pk)
    url = request.build_absolute_uri(reverse("app:ativos:resolver_qr", args=[ativo.qr_token]))
    imagem = qrcode.make(url)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


@tenant_required
def manutencao_lista(request):
    itens = []
    for ativo in Ativo.objects.filter(status=StatusAtivo.MANUTENCAO.value).select_related("categoria"):
        mov = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.MANUTENCAO)
        detalhe = getattr(mov, "detalhe_manutencao", None) if mov is not None else None
        itens.append({"ativo": ativo, "movimentacao": mov, "detalhe": detalhe})
    return render(request, "ativos/manutencao_lista.html", {"nav_atual": "manutencao", "itens": itens})

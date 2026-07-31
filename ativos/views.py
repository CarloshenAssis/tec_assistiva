"""
Views do app `ativos` — camada de apresentação "magra" (docs/ESPECIFICACAO_TECNICA.md §3.2):
toda regra de negócio vive em `ativos.services`/`ativos.domain`, aqui só
orquestramos formulários, sessão do wizard e redirecionamentos.
"""

import io
from decimal import Decimal, InvalidOperation

import qrcode
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ativos import services
from ativos.domain.acoes import NIVEL_ADMIN, NIVEL_GESTOR, acoes_disponiveis
from auditoria import limitador
from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.domain.exceptions import DominioAtivoError
from ativos.etiquetas import montar_etiquetas
from ativos.forms import (
    CHECKLIST_ITENS_DEVOLUCAO,
    CHECKLIST_ITENS_EMPRESTIMO,
    AtivoForm,
    DarBaixaForm,
    EditarManutencaoForm,
    EnviarManutencaoForm,
    FiltroEtiquetasForm,
    JustificativaForm,
    ObservacaoForm,
    RenovarForm,
    TransferirUnidadeForm,
)
from ativos.models import (
    Ativo,
    CategoriaAtivo,
    DetalheEmprestimo,
    FotoAtivo,
    ImpressaoEtiqueta,
    LayoutEtiqueta,
    Movimentacao,
)
from ativos.patrimonio import gerar_codigo_patrimonial
from ativos.selectors import (
    anotar_impressoes,
    checklist_detalhado,
    cor_de,
    datas_previstas_por_ativo,
    mapa_operacional,
    resolver_busca_patrimonio,
)
from beneficiarios.models import Beneficiario
from core import features
from core.decorators import nivel_hierarquico, tenant_required
from core.models import Unidade
from core.paginacao import paginar
from core.unidades import enxerga_todas_as_unidades, filtrar_por_unidade, unidades_visiveis

TABS_FICHA = [
    ("informacoes", "Informações"),
    ("timeline", "Timeline"),
    ("movimentacoes", "Movimentações"),
    ("fotos", "Fotos"),
    ("manutencoes", "Manutenções"),
    ("qrcode", "QR Code"),
    ("documentos", "Documentos"),
]


def _ativos_no_escopo(request):
    """
    Ativos que o usuário logado pode ver: tenant corrente (via
    `TenantManager`) **e** unidade permitida.

    Todo acesso a Ativo nas views passa por aqui — é o que faz a permissão de
    unidade (`Usuario.unidades`) valer de fato, e não só existir no modelo
    (docs/business-rules/unidades.md). Admin/Owner recebem o queryset sem
    filtro adicional.
    """
    return filtrar_por_unidade(Ativo.objects.all(), request.user)


def _ativo_no_escopo(request, pk):
    """
    Como `get_object_or_404`, mas dentro do escopo de unidade do usuário.

    Um ativo de outra unidade responde 404 — deliberadamente igual a "não
    existe", e não 403: confirmar a existência já entregaria a informação que
    o escopo existe para proteger (mesmo princípio de `resolver_qr`).
    """
    return get_object_or_404(
        _ativos_no_escopo(request).select_related(
            "categoria", "subcategoria", "unidade", "fornecedor"
        ),
        pk=pk,
    )


def _beneficiarios_no_escopo(request):
    """
    Beneficiários visíveis ao usuário: os da unidade dele **mais** os que não
    têm unidade definida (visíveis a toda a organização — ver o comentário no
    campo `Beneficiario.unidade`).
    """
    return filtrar_por_unidade(
        Beneficiario.objects.all(), request.user, incluir_sem_unidade=True
    )


@tenant_required
def lista(request):
    categoria_filtro = request.GET.get("categoria")
    busca = request.GET.get("q", "").strip()

    escopo = _ativos_no_escopo(request)

    resumo_categorias = []
    for categoria in CategoriaAtivo.objects.all():
        itens = escopo.filter(categoria=categoria)
        resumo_categorias.append(
            {
                "id": categoria.id,
                "nome": categoria.nome,
                "total": itens.count(),
                "disponiveis": itens.filter(status=StatusAtivo.DISPONIVEL.value).count(),
                "emprestados": itens.filter(status=StatusAtivo.EMPRESTADO.value).count(),
            }
        )

    ativos_qs = escopo.select_related("categoria", "unidade")
    if categoria_filtro:
        ativos_qs = ativos_qs.filter(categoria_id=categoria_filtro)
    if busca:
        ativos_qs = ativos_qs.filter(
            Q(patrimonio__icontains=busca)
            | Q(numero_serie__icontains=busca)
            | Q(fabricante__icontains=busca)
        )

    pagina = paginar(request, ativos_qs)
    ativos = list(pagina.object_list)
    contexto_emprestimo = datas_previstas_por_ativo([a.id for a in ativos])
    for ativo in ativos:
        ativo.cor_operacional = cor_de(ativo, contexto_emprestimo.get(ativo.id)).value

    return render(
        request,
        "ativos/lista.html",
        {
            "nav_atual": "ativos",
            "resumo_categorias": resumo_categorias,
            "ativos": ativos,
            "pagina": pagina,
            "categoria_filtro": int(categoria_filtro) if categoria_filtro else None,
            "busca": busca,
            "sem_unidade_atribuida": _sem_unidade_atribuida(request),
        },
    )


def _sem_unidade_atribuida(request) -> bool:
    """
    Gestor/Funcionário sem nenhuma unidade atribuída não vê ativo algum —
    comportamento correto (fail-closed), mas indistinguível de "a
    organização não tem ativos" na tela.

    As telas usam isto para explicar a diferença: sem esse aviso, o suporte
    recebe "o sistema apagou meus ativos" quando o que houve foi um cadastro
    de usuário incompleto.
    """
    if enxerga_todas_as_unidades(request.user):
        return False
    return not unidades_visiveis(request.user).exists()


_FOTO_CAMPOS = [
    ("foto_principal", FotoAtivo.Tipo.PRINCIPAL),
    ("foto_lateral", FotoAtivo.Tipo.LATERAL),
    ("foto_traseira", FotoAtivo.Tipo.TRASEIRA),
    ("foto_etiqueta", FotoAtivo.Tipo.ETIQUETA),
]


def _salvar_fotos_cadastro(ativo, arquivos):
    for campo, tipo in _FOTO_CAMPOS:
        arquivo = arquivos.get(campo)
        if arquivo:
            FotoAtivo.objects.create(tenant=ativo.tenant, ativo=ativo, tipo=tipo, arquivo=arquivo)


@tenant_required
def criar(request):
    if nivel_hierarquico(request) < NIVEL_GESTOR:
        raise PermissionDenied("Somente Gestor ou Admin podem cadastrar ativos.")

    # Ativo sem unidade não existe mais (docs/business-rules/unidades.md), então
    # sem nenhuma unidade disponível não há cadastro possível. Explicar isso
    # aqui é melhor que renderizar um formulário cujo único campo obrigatório
    # está vazio e não tem opção.
    unidades_disponiveis = filtrar_por_unidade(
        Unidade.objects.filter(ativo=True), request.user, campo="pk"
    )
    if not unidades_disponiveis.exists():
        return render(
            request,
            "ativos/sem_unidade.html",
            {"nav_atual": "ativos", "eh_admin": nivel_hierarquico(request) >= NIVEL_ADMIN},
        )

    # Mesmo raciocínio para categoria: é FK obrigatória do Ativo, então sem
    # nenhuma cadastrada o formulário teria um campo obrigatório sem opção.
    if not CategoriaAtivo.objects.exists():
        return render(
            request,
            "ativos/sem_categoria.html",
            {"nav_atual": "ativos", "eh_admin": nivel_hierarquico(request) >= NIVEL_ADMIN},
        )

    if request.method == "POST":
        form = AtivoForm(request.POST, usuario=request.user)
        if form.is_valid():
            ativo = form.save(commit=False)
            ativo.tenant = request.tenant
            if not ativo.patrimonio:
                # Usuário não digitou um patrimônio próprio — gera o código
                # sequencial da categoria (ver ativos/patrimonio.py).
                ativo.patrimonio = gerar_codigo_patrimonial(ativo.categoria)
            ativo.save()
            _salvar_fotos_cadastro(ativo, request.FILES)
            messages.success(
                request,
                f"Ativo {ativo.patrimonio} cadastrado. A etiqueta dele já está na fila de impressão.",
            )
            return redirect("app:ativos:ficha", pk=ativo.pk)
    else:
        form = AtivoForm(usuario=request.user)
    return render(
        request,
        "ativos/form.html",
        {"nav_atual": "ativos", "form": form, "titulo": "Novo Ativo", "mostrar_upload_fotos": True},
    )


@tenant_required
def editar(request, pk):
    if nivel_hierarquico(request) < NIVEL_GESTOR:
        raise PermissionDenied("Somente Gestor ou Admin podem editar ativos.")
    ativo = _ativo_no_escopo(request, pk)
    if request.method == "POST":
        form = AtivoForm(request.POST, instance=ativo, usuario=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Ativo atualizado.")
            return redirect("app:ativos:ficha", pk=ativo.pk)
    else:
        form = AtivoForm(instance=ativo, usuario=request.user)
    return render(
        request,
        "ativos/form.html",
        {"nav_atual": "ativos", "form": form, "titulo": f"Editar {ativo.patrimonio}", "ativo": ativo},
    )


@tenant_required
def ficha(request, pk):
    ativo = _ativo_no_escopo(request, pk)
    contexto_emprestimo = datas_previstas_por_ativo([ativo.id]).get(ativo.id)
    ativo.cor_operacional = cor_de(ativo, contexto_emprestimo).value

    aba = request.GET.get("aba", "informacoes")
    acoes = acoes_disponiveis(ativo.status_enum, nivel_hierarquico=nivel_hierarquico(request))
    acoes = _preparar_acoes_para_template(ativo, acoes, origem="ficha")

    contexto = {"nav_atual": "ativos", "ativo": ativo, "aba": aba, "tabs": TABS_FICHA, "acoes": acoes}

    if aba in ("timeline", "movimentacoes"):
        movimentacoes = list(ativo.movimentacoes.select_related("usuario").all())
        for movimentacao in movimentacoes:
            # Traduz o checklist bruto (dados_especificos) para algo legível
            # na tela — é o que responde "quem marcou o quê" num check-in ou
            # devolução, ver ativos/selectors.py::checklist_detalhado.
            movimentacao.checklist = checklist_detalhado(movimentacao)
        contexto["movimentacoes"] = movimentacoes
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
    if aba == "qrcode":
        # "Última impressão"/"Quantidade de impressões"/"Reimprimir" na ficha
        # do ativo (docs/business-rules/etiquetas.md).
        contexto["impressoes"] = ativo.impressoes.select_related("usuario")[:10]
        contexto["total_impressoes"] = ativo.total_impressoes
        contexto["ultima_impressao"] = ativo.ultima_impressao
        contexto["layouts_etiqueta"] = LayoutEtiqueta.choices

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
def localizar(request):
    """
    Porta de entrada única para achar um ativo — reúne as três formas de
    busca da especificação original (escanear QR Code / pesquisar
    patrimônio / pesquisar categoria / pesquisar nome) numa tela só, em vez
    de espalhadas entre `scan`, a lista de ativos e o mapa
    (docs/business-rules/qrcode.md).

    O código manual/câmera continua postando para `scan` (mesmo backend,
    já testado) — esta tela só acrescenta a busca por texto/categoria, que
    `scan` nunca ofereceu.
    """
    busca = request.GET.get("q", "").strip()
    categoria_id = request.GET.get("categoria")

    resultados = []
    if busca or categoria_id:
        qs = _ativos_no_escopo(request).select_related("categoria", "unidade")
        if categoria_id:
            qs = qs.filter(categoria_id=categoria_id)
        if busca:
            qs = qs.filter(
                Q(patrimonio__icontains=busca)
                | Q(categoria__nome__icontains=busca)
                | Q(fabricante__icontains=busca)
                | Q(modelo__icontains=busca)
            )
        resultados = list(qs[:30])

    return render(
        request,
        "ativos/localizar.html",
        {
            "nav_atual": "localizar",
            "busca": busca,
            "categoria_id": int(categoria_id) if categoria_id else None,
            "categorias": CategoriaAtivo.objects.all().order_by("nome"),
            "resultados": resultados,
        },
    )


@tenant_required
def resolver_qr(request, token):
    """
    Modo "Operação por QR Code" — docs/PLANO_DOMINIO_ATIVOS.md §3.4.

    Se o token não pertence ao tenant corrente, a uma unidade que o usuário
    pode operar, ou simplesmente não existe, a resposta é idêntica ("não
    encontrado") — nunca revelamos que o ativo existe fora do escopo de quem
    leu a etiqueta (defesa em profundidade, mesmo princípio de
    docs/PLANO_DOMINIO_ATIVOS.md §3.2).
    """
    ativo = (
        _ativos_no_escopo(request)
        .select_related("categoria", "unidade")
        .filter(qr_token=token)
        .first()
    )
    if ativo is None:
        return render(request, "ativos/quick_panel_nao_encontrado.html", {"nav_atual": "localizar"}, status=404)

    contexto_emprestimo = datas_previstas_por_ativo([ativo.id]).get(ativo.id)
    ativo.cor_operacional = cor_de(ativo, contexto_emprestimo).value

    acoes = acoes_disponiveis(ativo.status_enum, nivel_hierarquico=nivel_hierarquico(request))
    acoes = _preparar_acoes_para_template(ativo, acoes, origem="quick_panel")
    contexto = {"nav_atual": "localizar", "ativo": ativo, "acoes": acoes, **_contexto_por_status(ativo)}
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
        escopo = _ativos_no_escopo(request)
        ativo = (
            escopo.filter(qr_token=codigo).first()
            or escopo.filter(patrimonio__iexact=codigo).first()
        )
        if ativo is None:
            messages.error(request, "Nenhum ativo encontrado para esse código.")
            return redirect("app:ativos:scan")
        return redirect("app:ativos:resolver_qr", token=ativo.qr_token)
    return render(request, "ativos/scan.html", {"nav_atual": "localizar"})


ACOES_SIMPLES = {
    "reservar": lambda ativo, usuario: services.reservar(ativo, usuario),
    "cancelar_reserva": lambda ativo, usuario: services.cancelar_reserva(ativo, usuario),
    "concluir_higienizacao": lambda ativo, usuario: services.concluir_higienizacao(ativo, usuario),
    "finalizar_manutencao": lambda ativo, usuario: services.retornar_manutencao(ativo, usuario),
    "reativar": lambda ativo, usuario: services.reativar(ativo, usuario),
}

ACOES_COM_FORM = {
    "enviar_manutencao": EnviarManutencaoForm,
    "editar_manutencao": EditarManutencaoForm,
    "dar_baixa": DarBaixaForm,
    "renovar": RenovarForm,
    "registrar_recuperacao": ObservacaoForm,
    "registrar_extravio": JustificativaForm,
    "transferir": TransferirUnidadeForm,
}

#: Ações cujo formulário precisa conhecer o ativo para montar as opções
#: (hoje: transferir, que exclui a unidade atual da lista de destinos).
_ACOES_FORM_COM_ATIVO = {"transferir"}


def _url_redirecionamento(codigo, ativo):
    if codigo in ("emprestar", "confirmar_emprestimo"):
        return f"{reverse('app:ativos:wizard_emprestimo')}?ativo={ativo.pk}"
    if codigo == "receber_devolucao":
        return f"{reverse('app:ativos:devolucao')}?q={ativo.patrimonio}"
    if codigo == "imprimir_etiqueta":
        return f"{reverse('app:ativos:etiquetas_centro')}?ativo={ativo.pk}"
    return None


def _initial_da_acao(codigo, ativo):
    """Pré-preenche o formulário quando a ação é uma CORREÇÃO, não um registro novo."""
    if codigo != "editar_manutencao":
        return None
    movimentacao = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.MANUTENCAO)
    detalhe = getattr(movimentacao, "detalhe_manutencao", None) if movimentacao else None
    if detalhe is None:
        return None
    return {"motivo": detalhe.motivo, "fornecedor": detalhe.fornecedor_id, "valor": detalhe.valor}


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
    elif codigo == "editar_manutencao":
        services.editar_manutencao(
            ativo, usuario, motivo=dados["motivo"], fornecedor=dados.get("fornecedor"), valor=dados.get("valor")
        )
    elif codigo == "dar_baixa":
        services.dar_baixa(ativo, usuario, motivo=dados["motivo"])
    elif codigo == "renovar":
        services.renovar(ativo, usuario, novo_prazo_dias=dados["novo_prazo_dias"])
    elif codigo == "registrar_recuperacao":
        services.registrar_recuperacao(ativo, usuario, observacoes=dados.get("observacoes", ""))
    elif codigo == "registrar_extravio":
        services.registrar_extravio(ativo, usuario, observacoes=dados["observacoes"])
    elif codigo == "transferir":
        services.transferir(
            ativo,
            usuario,
            unidade_destino=dados["unidade_destino"],
            observacoes=dados["observacoes"],
        )


def _redirecionar_pos_acao(ativo, origem):
    if origem == "quick_panel":
        return redirect("app:ativos:resolver_qr", token=ativo.qr_token)
    if origem == "manutencao":
        return redirect("app:ativos:manutencao_lista")
    return redirect("app:ativos:ficha", pk=ativo.pk)


#: Quantas movimentações (emprestar, devolver, transferir, dar baixa etc.)
#: uma mesma conta pode gerar numa janela de tempo — barreira contra conta
#: comprometida ou script em loop, não contra uso humano de balcão (ver
#: auditoria/limitador.py). Generoso de propósito: um posto corrido não
#: chega perto disso num atendimento normal.
_LIMITE_MOVIMENTACOES = 60
_LIMITE_MOVIMENTACOES_JANELA_MINUTOS = 5


@tenant_required
def executar_acao(request, pk, codigo):
    """
    Único ponto de entrada para mudar o estado de um Ativo a partir da UI —
    a lista de ações permitidas vem sempre de `AcoesDisponiveis`
    (docs/PLANO_DOMINIO_ATIVOS.md §5.3), nunca de um botão hardcoded por
    tela: a ficha, o painel de QR Code e (futuramente) a API chamam
    exatamente esta mesma verificação.
    """
    ativo = _ativo_no_escopo(request, pk)
    acoes_permitidas = {
        a.codigo: a for a in acoes_disponiveis(ativo.status_enum, nivel_hierarquico=nivel_hierarquico(request))
    }

    url_redirect = _url_redirecionamento(codigo, ativo)
    if url_redirect and codigo in acoes_permitidas:
        return redirect(url_redirect)

    if codigo not in acoes_permitidas:
        raise PermissionDenied("Ação não disponível para o estado atual do ativo ou para o seu perfil.")

    origem = request.GET.get("origem") or request.POST.get("origem") or "ficha"

    if request.method == "POST" and limitador.limite_atingido(
        usuario=request.user,
        objeto_tipo=Movimentacao._meta.label,
        limite=_LIMITE_MOVIMENTACOES,
        janela_minutos=_LIMITE_MOVIMENTACOES_JANELA_MINUTOS,
    ):
        descricao = (
            f"Limite de movimentações atingido "
            f"({_LIMITE_MOVIMENTACOES}/{_LIMITE_MOVIMENTACOES_JANELA_MINUTOS}min)"
        )
        limitador.registrar_limite_atingido(
            request=request,
            objeto_tipo=Movimentacao._meta.label,
            limite=_LIMITE_MOVIMENTACOES,
            janela_minutos=_LIMITE_MOVIMENTACOES_JANELA_MINUTOS,
            descricao=descricao,
        )
        messages.error(
            request,
            "Muitas ações em pouco tempo nesta conta. Aguarde alguns minutos e tente de novo.",
        )
        return _redirecionar_pos_acao(ativo, origem)

    if codigo in ACOES_COM_FORM:
        FormClass = ACOES_COM_FORM[codigo]
        extra = {"ativo": ativo} if codigo in _ACOES_FORM_COM_ATIVO else {}
        if request.method == "POST":
            form = FormClass(request.POST, **extra)
            if form.is_valid():
                try:
                    _executar_acao_com_form(codigo, ativo, request.user, form.cleaned_data)
                except DominioAtivoError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Ação registrada com sucesso.")
                return _redirecionar_pos_acao(ativo, origem)
        else:
            form = FormClass(initial=_initial_da_acao(codigo, ativo), **extra)
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


def _texto_decimal_ou_none(valor: str):
    """
    Valida e normaliza um campo monetário opcional do wizard para string —
    guardado assim na sessão porque `Decimal` não é serializável em JSON
    (`django.contrib.sessions` usa JSON por padrão). Levanta
    `InvalidOperation` se o texto não for um número (não silencia o erro:
    quem chama decide a mensagem).

    Formato brasileiro: "," é o separador decimal, "." é o de milhar (ex.:
    "1.500,00"). Um `.replace(",", ".")` ingênuo tanto rejeita esse caso
    (vira "1.500.00", que `Decimal` recusa) quanto corrompe silenciosamente
    "1.000" (mil reais sem centavos) para 1 real — mesma heurística que o
    Django usa em `django.utils.formats.sanitize_separators` (ticket #22171):
    um único ponto seguido de exatamente 3 dígitos é separador de milhar;
    caso contrário, é separador decimal.
    """
    valor = (valor or "").strip()
    if not valor:
        return None

    if "," in valor:
        parte_inteira, parte_decimal = valor.rsplit(",", 1)
        valor = f"{parte_inteira.replace('.', '')}.{parte_decimal}"
    elif valor.count(".") > 1:
        valor = valor.replace(".", "")
    elif "." in valor:
        parte_inteira, parte_decimal = valor.split(".")
        if len(parte_decimal) == 3:
            valor = parte_inteira + parte_decimal

    return str(Decimal(valor))


def _decimal_da_sessao(valor):
    return Decimal(valor) if valor is not None else None


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
            if features.modulo_habilitado(request.tenant, features.LOCACAO_FINANCEIRO):
                # A sessão do Django serializa em JSON — `Decimal` não é
                # serializável, então o wizard guarda string (ou None) e só
                # vira Decimal de fato no momento de chamar `services.emprestar`.
                try:
                    wizard["valor_diaria"] = _texto_decimal_ou_none(request.POST.get("valor_diaria"))
                    wizard["caucao"] = _texto_decimal_ou_none(request.POST.get("caucao"))
                    wizard["percentual_multa_atraso_dia"] = _texto_decimal_ou_none(
                        request.POST.get("percentual_multa_atraso_dia")
                    )
                except InvalidOperation:
                    messages.error(request, "Valor de locação inválido — use só números e ponto decimal.")
                    return redirect("app:ativos:wizard_emprestimo")
        elif acao == "confirmar":
            beneficiario = get_object_or_404(_beneficiarios_no_escopo(request), pk=wizard["beneficiario_id"])
            ativo = _ativo_no_escopo(request, wizard["ativo_id"])
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
                    valor_diaria=_decimal_da_sessao(wizard.get("valor_diaria")),
                    caucao=_decimal_da_sessao(wizard.get("caucao")),
                    percentual_multa_atraso_dia=_decimal_da_sessao(
                        wizard.get("percentual_multa_atraso_dia")
                    ),
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
            _beneficiarios_no_escopo(request).filter(Q(nome__icontains=busca) | Q(documento__icontains=busca))[:15]
            if busca
            else []
        )
    elif passo == 2:
        contexto["beneficiario"] = get_object_or_404(_beneficiarios_no_escopo(request), pk=wizard["beneficiario_id"])
        busca = request.GET.get("q", "")
        contexto["busca"] = busca
        qs = _ativos_no_escopo(request).filter(status=StatusAtivo.DISPONIVEL.value).select_related("categoria")
        if busca:
            qs = qs.filter(Q(patrimonio__icontains=busca) | Q(categoria__nome__icontains=busca))
        contexto["resultados"] = qs[:15]
        contexto["ativo_sugerido_id"] = wizard.get("ativo_id_sugerido")
    elif passo == 3:
        contexto["ativo"] = _ativo_no_escopo(request, wizard["ativo_id"])
        contexto["beneficiario"] = get_object_or_404(_beneficiarios_no_escopo(request), pk=wizard["beneficiario_id"])
    elif passo == 4:
        contexto["ativo"] = _ativo_no_escopo(request, wizard["ativo_id"])
        contexto["beneficiario"] = get_object_or_404(_beneficiarios_no_escopo(request), pk=wizard["beneficiario_id"])
        contexto["prazo_dias"] = wizard.get("prazo_dias")
        contexto["checklist_itens"] = CHECKLIST_ITENS_EMPRESTIMO
        contexto["valor_diaria"] = wizard.get("valor_diaria")
        contexto["caucao"] = wizard.get("caucao")
        contexto["percentual_multa_atraso_dia"] = wizard.get("percentual_multa_atraso_dia")

    return render(request, "ativos/wizard_emprestimo.html", contexto)


@tenant_required
def devolucao(request):
    busca = (request.GET.get("q") or request.POST.get("q") or "").strip()
    ativo = None
    detalhe_emprestimo = None
    dias_em_posse = None

    if busca:
        escopo = _ativos_no_escopo(request)
        ativo = escopo.filter(
            Q(patrimonio__iexact=busca) | Q(qr_token=busca), status=StatusAtivo.EMPRESTADO.value
        ).first()
        if ativo is None:
            mov = (
                Movimentacao.objects.filter(
                    tipo=TipoMovimentacao.EMPRESTIMO.value,
                    ativo__status=StatusAtivo.EMPRESTADO.value,
                    ativo__in=escopo,
                )
                .filter(
                    Q(detalhe_emprestimo__beneficiario__nome__icontains=busca)
                    | Q(detalhe_emprestimo__beneficiario__documento__icontains=busca)
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

    if request.method == "POST" and request.POST.get("destino"):
        ativo_confirmado = _ativo_no_escopo(request, request.POST.get("ativo_id"))
        try:
            destino = StatusAtivo(request.POST["destino"])
        except ValueError:
            # `destino` vem do name/value do botão, portanto é entrada do
            # cliente como qualquer outra: um valor forjado vira erro de
            # formulário, não 500.
            messages.error(request, "Destino de devolução inválido.")
            return redirect("app:ativos:devolucao")
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
    ativo = _ativo_no_escopo(request, pk)
    url = request.build_absolute_uri(reverse("app:ativos:resolver_qr", args=[ativo.qr_token]))
    imagem = qrcode.make(url)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


@tenant_required
def agenda(request):
    """
    Devoluções hoje, próximos vencimentos (7 dias) e atrasados — mesma
    consulta usada pelo job diário de notificações
    (notificacoes/management/commands/enviar_notificacoes_diarias.py),
    aqui só para exibição.
    """
    hoje = timezone.now().date()
    detalhes = DetalheEmprestimo.objects.filter(
        movimentacao__ativo__status=StatusAtivo.EMPRESTADO.value,
        movimentacao__ativo__in=_ativos_no_escopo(request),
    ).select_related("movimentacao__ativo", "movimentacao__ativo__categoria", "beneficiario")

    hoje_lista, proximos, atrasados = [], [], []
    for detalhe in detalhes:
        dias = (detalhe.data_prevista_devolucao - hoje).days
        item = {"beneficiario": detalhe.beneficiario, "ativo": detalhe.movimentacao.ativo, "dias": dias}
        if dias == 0:
            hoje_lista.append(item)
        elif 0 < dias <= 7:
            proximos.append(item)
        elif dias < 0:
            atrasados.append({**item, "dias": abs(dias)})

    return render(
        request,
        "ativos/agenda.html",
        {"nav_atual": "agenda", "hoje_lista": hoje_lista, "proximos": proximos, "atrasados": atrasados},
    )


@tenant_required
def mapa(request):
    """
    Mapa Operacional de Ativos: não é geolocalização em tempo real — é
    "onde cada ativo está" a partir de dados já cadastrados (unidade
    física, endereço/bairro do beneficiário quando emprestado, oficina de
    manutenção). Ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md.
    """
    categoria_id = request.GET.get("categoria")
    status_filtro = request.GET.get("status")
    unidade_id = request.GET.get("unidade")
    bairro = request.GET.get("bairro", "").strip()
    busca = request.GET.get("q", "").strip()

    ativos_qs = _ativos_no_escopo(request)
    if categoria_id:
        ativos_qs = ativos_qs.filter(categoria_id=categoria_id)
    if status_filtro:
        ativos_qs = ativos_qs.filter(status=status_filtro)
    if unidade_id:
        ativos_qs = ativos_qs.filter(unidade_id=unidade_id)
    if bairro:
        ativos_qs = ativos_qs.filter(
            status=StatusAtivo.EMPRESTADO.value,
            movimentacoes__tipo=TipoMovimentacao.EMPRESTIMO.value,
            movimentacoes__detalhe_emprestimo__beneficiario__bairro__iexact=bairro,
        ).distinct()

    dados = mapa_operacional(ativos_qs)

    resultado_busca = (
        resolver_busca_patrimonio(busca, ativos_qs=_ativos_no_escopo(request)) if busca else None
    )

    return render(
        request,
        "ativos/mapa.html",
        {
            "nav_atual": "mapa",
            "por_unidade": dados["por_unidade"],
            "por_bairro": dados["por_bairro"],
            "categorias": CategoriaAtivo.objects.all(),
            "unidades": unidades_visiveis(request.user).order_by("nome"),
            "status_opcoes": list(StatusAtivo),
            "categoria_id": categoria_id,
            "status_filtro": status_filtro,
            "unidade_id": unidade_id,
            "bairro": bairro,
            "busca": busca,
            "resultado_busca": resultado_busca,
        },
    )


@tenant_required
def manutencao_lista(request):
    ativos_qs = _ativos_no_escopo(request).filter(
        status=StatusAtivo.MANUTENCAO.value
    ).select_related("categoria")
    pagina = paginar(request, ativos_qs)

    itens = []
    for ativo in pagina.object_list:
        mov = Movimentacao.objects.mais_recente_do_tipo(ativo, TipoMovimentacao.MANUTENCAO)
        detalhe = getattr(mov, "detalhe_manutencao", None) if mov is not None else None
        itens.append({"ativo": ativo, "movimentacao": mov, "detalhe": detalhe})
    return render(
        request,
        "ativos/manutencao_lista.html",
        {"nav_atual": "manutencao", "itens": itens, "pagina": pagina},
    )


# ------------------------------------------------ Centro de Etiquetas ----
# docs/business-rules/etiquetas.md


@tenant_required
def etiquetas_centro(request):
    """
    Centro de Etiquetas: filtra o acervo, seleciona os ativos e gera a folha
    de etiquetas para impressão.

    O parâmetro `?ativo=<pk>` vem da ação "Imprimir Etiqueta" da ficha/painel
    de QR — abre a tela já com aquele ativo pré-marcado, em vez de obrigar o
    operador a caçá-lo numa lista de centenas.
    """
    form = FiltroEtiquetasForm(request.GET or None, usuario=request.user)
    ativos_qs = anotar_impressoes(_ativos_no_escopo(request)).select_related(
        "categoria", "unidade"
    )

    if form.is_valid():
        dados = form.cleaned_data
        if dados.get("categoria"):
            ativos_qs = ativos_qs.filter(categoria=dados["categoria"])
        if dados.get("unidade"):
            ativos_qs = ativos_qs.filter(unidade=dados["unidade"])
        if dados.get("status"):
            ativos_qs = ativos_qs.filter(status=dados["status"])
        if dados.get("somente_sem_etiqueta"):
            ativos_qs = ativos_qs.filter(impressoes__isnull=True)

    # Etiqueta de ativo baixado não é impressa (ver ativos/domain/acoes.py):
    # o ativo saiu do patrimônio, uma etiqueta nova só confundiria o
    # inventário. Fica fora da lista mesmo sem filtro de status.
    ativos_qs = ativos_qs.exclude(status=StatusAtivo.BAIXADO.value)

    ativo_pre_selecionado = request.GET.get("ativo")
    total_na_fila = (
        _ativos_no_escopo(request)
        .filter(impressoes__isnull=True)
        .exclude(status=StatusAtivo.BAIXADO.value)
        .count()
    )

    return render(
        request,
        "ativos/etiquetas_centro.html",
        {
            "nav_atual": "etiquetas",
            "form": form,
            "ativos": ativos_qs.order_by("patrimonio")[:300],
            "ativo_pre_selecionado": int(ativo_pre_selecionado) if ativo_pre_selecionado else None,
            "total_na_fila": total_na_fila,
            "sem_unidade_atribuida": _sem_unidade_atribuida(request),
        },
    )


@tenant_required
def etiquetas_folha(request):
    """
    Gera a folha de etiquetas (HTML pronto para impressão) e registra o
    histórico de impressão.

    Exige POST porque produz efeito colateral (grava `ImpressaoEtiqueta`) —
    um GET tornaria o registro acionável por pré-visualização de link,
    inflando o histórico com impressões que nunca aconteceram.

    A conversão para PDF é feita pela caixa de impressão do navegador
    ("Salvar como PDF") — ver a justificativa em ativos/etiquetas.py.
    """
    if request.method != "POST":
        raise PermissionDenied("A geração de etiquetas exige confirmação (POST).")

    layout = request.POST.get("layout") or LayoutEtiqueta.MEDIO
    if layout not in LayoutEtiqueta.values:
        messages.error(request, "Tamanho de etiqueta inválido.")
        return redirect("app:ativos:etiquetas_centro")

    ids = request.POST.getlist("ativos")
    ativos = list(
        _ativos_no_escopo(request)
        .filter(pk__in=ids)
        .exclude(status=StatusAtivo.BAIXADO.value)
        .select_related("categoria")
        .order_by("patrimonio")
    )
    if not ativos:
        messages.error(request, "Selecione ao menos um ativo para imprimir.")
        return redirect("app:ativos:etiquetas_centro")

    def url_de(ativo):
        return request.build_absolute_uri(
            reverse("app:ativos:resolver_qr", args=[ativo.qr_token])
        )

    etiquetas = montar_etiquetas(
        ativos, url_de=url_de, instituicao=request.tenant.nome, layout=layout
    )
    services.registrar_impressao_etiquetas(ativos, usuario=request.user, layout=layout)

    return render(
        request,
        "ativos/etiquetas_folha.html",
        {"etiquetas": etiquetas, "layout": layout, "total": len(etiquetas)},
    )


@tenant_required
def etiquetas_historico(request):
    """
    Histórico de impressão, agrupado por lote — "40 etiquetas médias em
    12/03, por João" em vez de 40 linhas soltas.
    """
    registros = (
        ImpressaoEtiqueta.objects.filter(ativo__in=_ativos_no_escopo(request))
        .select_related("usuario", "ativo")
        .order_by("-impresso_em")
    )

    # Agrupado por lote antes de paginar (não depois): um corte fixo em cima
    # dos registros individuais partiria um lote ao meio sem avisar. `lotes`
    # já sai ordenado (dict preserva ordem de inserção, e `registros` já
    # está do mais recente para o mais antigo).
    lotes = {}
    for registro in registros:
        bucket = lotes.setdefault(
            registro.lote,
            {
                "lote": registro.lote,
                "impresso_em": registro.impresso_em,
                "usuario": registro.usuario,
                "layout": registro.get_layout_display(),
                "ativos": [],
            },
        )
        bucket["ativos"].append(registro.ativo)

    pagina = paginar(request, list(lotes.values()))

    return render(
        request,
        "ativos/etiquetas_historico.html",
        {"nav_atual": "etiquetas", "lotes": pagina.object_list, "pagina": pagina},
    )

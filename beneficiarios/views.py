import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from auditoria.models import AcaoAuditada
from auditoria.services import registrar, registrar_acesso_dado_pessoal
from beneficiarios.forms import BeneficiarioForm
from beneficiarios.lgpd import anonimizar, exportar_dados
from beneficiarios.models import Beneficiario, DocumentoBeneficiario
from core.arquivos import resposta_de_download
from core.decorators import nivel_hierarquico, tenant_required
from core.unidades import filtrar_por_unidade

#: Exportar e anonimizar são operações sobre a totalidade dos dados de uma
#: pessoa — ficam restritas a Admin (nível 30). Um funcionário de balcão
#: precisa ver a ficha para atender, não baixar o dossiê completo.
NIVEL_ADMIN = 30


def _no_escopo(request):
    """
    Beneficiários visíveis ao usuário — os da unidade dele e os que não têm
    unidade definida (docs/business-rules/unidades.md; ver o comentário no
    campo `Beneficiario.unidade` para por que o nulo é inclusivo aqui e
    exclusivo em Ativo).
    """
    return filtrar_por_unidade(Beneficiario.objects.all(), request.user, incluir_sem_unidade=True)


@tenant_required
def lista(request):
    busca = request.GET.get("q", "").strip()
    qs = _no_escopo(request)
    if busca:
        qs = qs.filter(Q(nome__icontains=busca) | Q(documento__icontains=busca) | Q(telefone__icontains=busca))
    return render(
        request,
        "beneficiarios/lista.html",
        {"nav_atual": "beneficiarios", "beneficiarios": qs[:200], "busca": busca},
    )


@tenant_required
def criar(request):
    if request.method == "POST":
        form = BeneficiarioForm(request.POST, usuario=request.user)
        if form.is_valid():
            beneficiario = form.save(commit=False)
            beneficiario.tenant = request.tenant
            beneficiario.save()
            messages.success(
                request,
                f"{request.tenant.rotulo_beneficiario_singular} {beneficiario.nome} cadastrado com sucesso.",
            )
            return redirect("app:beneficiarios:ficha", pk=beneficiario.pk)
    else:
        form = BeneficiarioForm(usuario=request.user)
    return render(
        request,
        "beneficiarios/form.html",
        {
            "nav_atual": "beneficiarios",
            "form": form,
            "titulo": f"Novo {request.tenant.rotulo_beneficiario_singular}",
        },
    )


@tenant_required
def ficha(request, pk):
    beneficiario = get_object_or_404(_no_escopo(request), pk=pk)
    emprestimos = beneficiario.emprestimos.select_related("movimentacao", "movimentacao__ativo").order_by(
        "-movimentacao__data_hora"
    )

    # Abrir a ficha é acesso a dado pessoal e precisa constar na trilha
    # (LGPD Art. 37) — é o registro que responde "quem consultou quem".
    registrar_acesso_dado_pessoal(request, beneficiario, descricao="Ficha do titular consultada")

    return render(
        request,
        "beneficiarios/ficha.html",
        {
            "nav_atual": "beneficiarios",
            "beneficiario": beneficiario,
            "emprestimos": emprestimos,
            "pode_gerir_lgpd": nivel_hierarquico(request) >= NIVEL_ADMIN,
        },
    )


@tenant_required
def baixar_documento(request, pk):
    """
    Entrega de documento anexado (RG, comprovante, laudo, receita médica).

    O registro é resolvido pelo manager com escopo de tenant, então um
    documento de outro tenant simplesmente não existe para esta consulta —
    a autorização não depende de comparar caminhos de arquivo.
    """
    documento = get_object_or_404(
        DocumentoBeneficiario.objects.select_related("beneficiario"), pk=pk
    )

    # Laudo e receita médica são dados sobre saúde: dado pessoal sensível
    # (Art. 5º, II). A marcação separa, num relatório de incidente, quem viu
    # o cadastro de quem viu o prontuário.
    sensivel = documento.tipo in (
        DocumentoBeneficiario.Tipo.LAUDO,
        DocumentoBeneficiario.Tipo.RECEITA_MEDICA,
    )
    registrar_acesso_dado_pessoal(
        request,
        documento.beneficiario,
        sensivel=sensivel,
        descricao=f"Download de documento: {documento.get_tipo_display()}",
    )

    nome = f"{slugify(documento.beneficiario.nome)}-{documento.tipo}"
    extensao = documento.arquivo.name.rsplit(".", 1)[-1] if documento.arquivo else ""
    return resposta_de_download(
        documento.arquivo, nome_sugerido=f"{nome}.{extensao}" if extensao else nome
    )


@tenant_required
def exportar(request, pk):
    """Direito de acesso e portabilidade (LGPD Art. 18, II e V)."""
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode exportar os dados de um titular.")

    beneficiario = get_object_or_404(_no_escopo(request), pk=pk)
    dados = exportar_dados(beneficiario)

    registrar(
        AcaoAuditada.EXPORTACAO_DADOS,
        request=request,
        objeto=beneficiario,
        descricao="Exportação de dados a pedido do titular (Art. 18, V)",
        envolve_dado_sensivel=True,
    )

    resposta = HttpResponse(
        json.dumps(dados, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    nome = slugify(beneficiario.nome) or f"titular-{beneficiario.pk}"
    resposta["Content-Disposition"] = f'attachment; filename="dados-{nome}.json"'
    resposta["Cache-Control"] = "private, no-store"
    return resposta


@tenant_required
def anonimizar_titular(request, pk):
    """
    Direito de eliminação (LGPD Art. 18, VI).

    Exige POST: é uma operação irreversível, e um GET a tornaria acionável
    por um link, uma pré-visualização de mensageiro ou um crawler.
    """
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode anonimizar os dados de um titular.")

    beneficiario = get_object_or_404(_no_escopo(request), pk=pk)

    if request.method != "POST":
        raise PermissionDenied("Esta operação é irreversível e exige confirmação (POST).")

    anonimizar(beneficiario, request=request, usuario=request.user)
    messages.success(
        request,
        "Dados identificáveis removidos. O histórico de empréstimos foi "
        "preservado sem vínculo com a pessoa.",
    )
    return redirect("app:beneficiarios:ficha", pk=beneficiario.pk)

"""
Views operacionais do cadastro de titulares (`Beneficiario`).

Cobre o CRUD de ficha, o upload/download de documentos anexados e as duas
views que atendem aos direitos do titular sob a LGPD — exportação (Art. 18,
II e V) e anonimização (Art. 18, VI), cuja lógica de domínio mora em
`beneficiarios/lgpd.py`; aqui só entra o controle de acesso (Admin, taxa) e
a resposta HTTP.
"""

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from auditoria import limitador
from auditoria.models import AcaoAuditada
from auditoria.services import registrar, registrar_acesso_dado_pessoal
from beneficiarios.forms import BeneficiarioForm, DocumentoBeneficiarioForm
from beneficiarios.lgpd import anonimizar, exportar_dados
from beneficiarios.models import Beneficiario, DocumentoBeneficiario
from core import features
from core.arquivos import resposta_de_download
from core.decorators import nivel_hierarquico, tenant_required
from core.paginacao import paginar
from core.unidades import filtrar_por_unidade

#: Exportar e anonimizar são operações sobre a totalidade dos dados de uma
#: pessoa — ficam restritas a Admin (nível 30). Um funcionário de balcão
#: precisa ver a ficha para atender, não baixar o dossiê completo.
NIVEL_ADMIN = 30

#: Limites de taxa (auditoria/limitador.py) — bem mais apertados que o de
#: movimentação de ativo: exportar e anonimizar não são operação de balcão,
#: são exceção rara pedida pelo titular. Ninguém legítimo faz isso em lote.
_LIMITE_EXPORTACOES = 20
_LIMITE_EXPORTACOES_JANELA_MINUTOS = 60
_LIMITE_ANONIMIZACOES = 5
_LIMITE_ANONIMIZACOES_JANELA_MINUTOS = 60


def _no_escopo(request):
    """Devolve o queryset de `Beneficiario` visível ao usuário da requisição.

    São os titulares da unidade do usuário mais os que não têm unidade
    definida (docs/business-rules/unidades.md; ver o comentário no campo
    `Beneficiario.unidade` para por que o nulo é inclusivo aqui e exclusivo
    em `Ativo`). Base de toda view que busca um titular por `pk`, para que
    um usuário não consiga acessar (nem por 404 disfarçado) titular de
    unidade que não opera.

    Args:
        request: A requisição corrente, com `request.user` resolvido.

    Returns:
        QuerySet de `Beneficiario` já filtrado por unidade.
    """
    return filtrar_por_unidade(Beneficiario.objects.all(), request.user, incluir_sem_unidade=True)


@tenant_required
def lista(request):
    """Lista paginada de titulares do tenant, com busca por nome, documento ou telefone."""
    busca = request.GET.get("q", "").strip()
    qs = _no_escopo(request)
    if busca:
        qs = qs.filter(Q(nome__icontains=busca) | Q(documento__icontains=busca) | Q(telefone__icontains=busca))
    pagina = paginar(request, qs)
    return render(
        request,
        "beneficiarios/lista.html",
        {"nav_atual": "beneficiarios", "beneficiarios": pagina.object_list, "pagina": pagina, "busca": busca},
    )


@tenant_required
def criar(request):
    """Cadastra um novo titular no tenant."""
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
def editar(request, pk):
    """Edita o cadastro de um titular já existente, registrando a alteração na trilha de auditoria."""
    beneficiario = get_object_or_404(_no_escopo(request), pk=pk)
    if request.method == "POST":
        form = BeneficiarioForm(request.POST, instance=beneficiario, usuario=request.user)
        if form.is_valid():
            form.save()
            registrar(
                AcaoAuditada.ALTERACAO,
                request=request,
                objeto=beneficiario,
                descricao="Cadastro do titular editado",
            )
            messages.success(request, f"{request.tenant.rotulo_beneficiario_singular} atualizado com sucesso.")
            return redirect("app:beneficiarios:ficha", pk=beneficiario.pk)
    else:
        form = BeneficiarioForm(instance=beneficiario, usuario=request.user)
    return render(
        request,
        "beneficiarios/form.html",
        {
            "nav_atual": "beneficiarios",
            "form": form,
            "titulo": f"Editar {request.tenant.rotulo_beneficiario_singular}",
        },
    )


@tenant_required
def ficha(request, pk):
    """Exibe a ficha completa do titular: dados, empréstimos e documentos anexados.

    Abrir a ficha é, em si, acesso a dado pessoal e por isso fica registrado
    na trilha de auditoria (LGPD Art. 37) — é o registro que responde "quem
    consultou quem" caso o titular questione o tratamento de seus dados.
    """
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
            "documentos": beneficiario.documentos.order_by("-enviado_em"),
            "form_documento": DocumentoBeneficiarioForm(),
            "documentos_habilitado": features.modulo_habilitado(
                request.tenant, features.DOCUMENTOS_BENEFICIARIO
            ),
            "pode_gerir_lgpd": nivel_hierarquico(request) >= NIVEL_ADMIN,
        },
    )


@tenant_required
def documento_novo(request, pk):
    """Anexa um documento (RG, comprovante, laudo, receita) ao titular.

    Exige o módulo `documentos_beneficiario` habilitado para o tenant
    (docs/business-rules/modulos.md) — upload de documento é opcional, não
    presumido; um POST forjado com o módulo desligado é recusado aqui, não
    só escondido da tela.

    Args:
        request: A requisição, com o arquivo em `request.FILES`.
        pk: Chave primária do `Beneficiario` a receber o documento.

    Returns:
        Redireciona para a ficha do titular, com mensagem de sucesso ou
        os erros de validação do formulário.

    Raises:
        django.core.exceptions.PermissionDenied: Se a requisição não for
            POST, ou se o módulo `documentos_beneficiario` não estiver
            habilitado para o tenant.
    """
    beneficiario = get_object_or_404(_no_escopo(request), pk=pk)
    if request.method != "POST":
        raise PermissionDenied("Envio de documento exige POST.")
    if not features.modulo_habilitado(request.tenant, features.DOCUMENTOS_BENEFICIARIO):
        raise PermissionDenied("Upload de documento não está habilitado para esta instituição.")

    form = DocumentoBeneficiarioForm(request.POST, request.FILES)
    if form.is_valid():
        documento = form.save(commit=False)
        documento.tenant = request.tenant
        documento.beneficiario = beneficiario
        documento.save()
        sensivel = documento.tipo in (
            DocumentoBeneficiario.Tipo.LAUDO,
            DocumentoBeneficiario.Tipo.RECEITA_MEDICA,
        )
        registrar(
            AcaoAuditada.CRIACAO,
            request=request,
            objeto=beneficiario,
            descricao=f"Documento anexado: {documento.get_tipo_display()}",
            envolve_dado_sensivel=sensivel,
        )
        messages.success(request, "Documento anexado com sucesso.")
    else:
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
    return redirect("app:beneficiarios:ficha", pk=beneficiario.pk)


@tenant_required
def baixar_documento(request, pk):
    """Entrega o arquivo de um documento anexado (RG, comprovante, laudo, receita médica).

    O documento só existe para esta consulta se o beneficiário dele estiver
    no escopo de unidade do usuário — mesmo filtro de `ficha()`. Sem isso,
    quem só devia enxergar uma unidade conseguia baixar dado sensível (RG,
    laudo, receita) de beneficiário de outra unidade só sabendo o id do
    documento, mesmo recebendo 404 ao tentar abrir a ficha dele.

    Args:
        request: A requisição corrente.
        pk: Chave primária do `DocumentoBeneficiario` a baixar.

    Returns:
        A resposta HTTP de download do arquivo.
    """
    documento = get_object_or_404(
        DocumentoBeneficiario.objects.select_related("beneficiario").filter(
            beneficiario__in=_no_escopo(request)
        ),
        pk=pk,
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
    """Exporta o dossiê completo do titular em JSON — direito de acesso e portabilidade (LGPD Art. 18, II e V).

    Restrito a Admin e sujeito a limite de taxa (`_LIMITE_EXPORTACOES`):
    diferente de consultar a ficha, exportar entrega o dado bruto e por
    completo, então o controle de quem pode e com que frequência é mais
    apertado.

    Args:
        request: A requisição corrente.
        pk: Chave primária do `Beneficiario` a exportar.

    Returns:
        `HttpResponse` com o JSON como anexo para download (sempre
        `Cache-Control: private, no-store`, por ser dado pessoal), ou um
        redirecionamento à ficha se o limite de taxa foi atingido.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin (`nivel_hierarquico(request) < NIVEL_ADMIN`).
    """
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode exportar os dados de um titular.")

    beneficiario = get_object_or_404(_no_escopo(request), pk=pk)

    if limitador.limite_atingido(
        usuario=request.user,
        objeto_tipo=Beneficiario._meta.label,
        acao=AcaoAuditada.EXPORTACAO_DADOS,
        limite=_LIMITE_EXPORTACOES,
        janela_minutos=_LIMITE_EXPORTACOES_JANELA_MINUTOS,
    ):
        descricao = (
            f"Limite de exportações atingido "
            f"({_LIMITE_EXPORTACOES}/{_LIMITE_EXPORTACOES_JANELA_MINUTOS}min)"
        )
        limitador.registrar_limite_atingido(
            request=request,
            objeto_tipo=Beneficiario._meta.label,
            limite=_LIMITE_EXPORTACOES,
            janela_minutos=_LIMITE_EXPORTACOES_JANELA_MINUTOS,
            descricao=descricao,
        )
        messages.error(request, "Muitas exportações em pouco tempo nesta conta. Aguarde e tente de novo.")
        return redirect("app:beneficiarios:ficha", pk=beneficiario.pk)

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
    """Anonimiza os dados identificáveis do titular — direito de eliminação (LGPD Art. 18, VI).

    Exige POST: é uma operação irreversível (ver `beneficiarios.lgpd.anonimizar`),
    e um GET a tornaria acionável por um link, uma pré-visualização de
    mensageiro ou um crawler. Restrita a Admin e sujeita a limite de taxa
    (`_LIMITE_ANONIMIZACOES`), mais apertado que o de exportação.

    Args:
        request: A requisição corrente.
        pk: Chave primária do `Beneficiario` a anonimizar.

    Returns:
        Redireciona para a ficha do titular, com mensagem de sucesso ou
        de limite de taxa atingido.

    Raises:
        django.core.exceptions.PermissionDenied: Se o usuário não for
            Admin, ou se a requisição não for POST.
    """
    if nivel_hierarquico(request) < NIVEL_ADMIN:
        raise PermissionDenied("Somente Admin pode anonimizar os dados de um titular.")

    beneficiario = get_object_or_404(_no_escopo(request), pk=pk)

    if request.method != "POST":
        raise PermissionDenied("Esta operação é irreversível e exige confirmação (POST).")

    if limitador.limite_atingido(
        usuario=request.user,
        objeto_tipo=Beneficiario._meta.label,
        acao=AcaoAuditada.ANONIMIZACAO,
        limite=_LIMITE_ANONIMIZACOES,
        janela_minutos=_LIMITE_ANONIMIZACOES_JANELA_MINUTOS,
    ):
        descricao = (
            f"Limite de anonimizações atingido "
            f"({_LIMITE_ANONIMIZACOES}/{_LIMITE_ANONIMIZACOES_JANELA_MINUTOS}min)"
        )
        limitador.registrar_limite_atingido(
            request=request,
            objeto_tipo=Beneficiario._meta.label,
            limite=_LIMITE_ANONIMIZACOES,
            janela_minutos=_LIMITE_ANONIMIZACOES_JANELA_MINUTOS,
            descricao=descricao,
        )
        messages.error(request, "Muitas anonimizações em pouco tempo nesta conta. Aguarde e tente de novo.")
        return redirect("app:beneficiarios:ficha", pk=beneficiario.pk)

    anonimizar(beneficiario, request=request, usuario=request.user)
    messages.success(
        request,
        "Dados identificáveis removidos. O histórico de empréstimos foi "
        "preservado sem vínculo com a pessoa.",
    )
    return redirect("app:beneficiarios:ficha", pk=beneficiario.pk)

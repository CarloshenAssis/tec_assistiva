"""
Exportação de relatórios em CSV (docs/business-rules/relatorios.md).

Cada função devolve um `HttpResponse` pronto para download — mantém a view
fina (só resolve o queryset com o escopo de unidade certo e delega aqui a
montagem do arquivo). Usa `;` como separador e `utf-8-sig` (BOM) porque é o
que o Excel em português abre corretamente sem pedir para escolher
codificação — `,` e UTF-8 puro quebram acentuação nele.
"""

from __future__ import annotations

import csv

from django.http import HttpResponse


def _resposta_csv(nome_arquivo: str) -> tuple[HttpResponse, "csv._writer"]:
    # Charset "utf-8" na resposta, não "utf-8-sig": o codec `utf-8-sig`
    # insere um BOM a CADA chamada de `.encode()`, e `HttpResponse.write()`
    # recodifica a cada chamada — como `csv.writer` faz um `write()` por
    # linha, declarar a resposta como utf-8-sig contaminava toda linha
    # (menos a primeira) com um BOM extra no meio do arquivo. O BOM correto
    # é só no início, escrito uma única vez abaixo como bytes crus — que
    # `HttpResponse` grava sem recodificar.
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    resposta.write(b"\xef\xbb\xbf")
    escritor = csv.writer(resposta, delimiter=";")
    return resposta, escritor


def exportar_ativos_csv(ativos_qs) -> HttpResponse:
    resposta, escritor = _resposta_csv("ativos.csv")
    escritor.writerow([
        "Patrimônio", "Categoria", "Subcategoria", "Fabricante", "Modelo",
        "Nº de série", "Status", "Unidade", "Data de aquisição",
    ])
    for ativo in ativos_qs.select_related("categoria", "subcategoria", "unidade").order_by("patrimonio"):
        escritor.writerow([
            ativo.patrimonio,
            ativo.categoria.nome,
            ativo.subcategoria.nome if ativo.subcategoria_id else "",
            ativo.fabricante,
            ativo.modelo,
            ativo.numero_serie,
            ativo.get_status_display(),
            ativo.unidade.nome if ativo.unidade_id else "",
            ativo.data_aquisicao.isoformat() if ativo.data_aquisicao else "",
        ])
    return resposta


def exportar_beneficiarios_csv(beneficiarios_qs, rotulo_singular: str) -> HttpResponse:
    resposta, escritor = _resposta_csv("beneficiarios.csv")
    escritor.writerow([
        rotulo_singular, "Tipo de documento", "Documento", "Telefone", "WhatsApp",
        "E-mail", "Unidade", "Cidade",
    ])
    for beneficiario in beneficiarios_qs.select_related("unidade").order_by("nome"):
        escritor.writerow([
            beneficiario.nome,
            beneficiario.get_tipo_documento_display(),
            beneficiario.documento,
            beneficiario.telefone,
            beneficiario.whatsapp,
            beneficiario.email,
            beneficiario.unidade.nome if beneficiario.unidade_id else "",
            beneficiario.cidade,
        ])
    return resposta


def exportar_movimentacoes_csv(movimentacoes_qs) -> HttpResponse:
    resposta, escritor = _resposta_csv("movimentacoes.csv")
    escritor.writerow([
        "Data/hora", "Ativo", "Tipo", "Status anterior", "Status novo",
        "Usuário", "Unidade", "Beneficiário", "Prazo (dias)", "Devolução prevista", "Observações",
    ])
    qs = movimentacoes_qs.select_related(
        "ativo", "usuario", "unidade", "detalhe_emprestimo", "detalhe_emprestimo__beneficiario"
    ).order_by("-data_hora")
    for mov in qs:
        detalhe = getattr(mov, "detalhe_emprestimo", None)
        escritor.writerow([
            mov.data_hora.strftime("%d/%m/%Y %H:%M"),
            mov.ativo.patrimonio,
            mov.get_tipo_display(),
            mov.get_status_anterior_display(),
            mov.get_status_novo_display(),
            mov.usuario.get_username() if mov.usuario_id else "",
            mov.unidade.nome if mov.unidade_id else "",
            detalhe.beneficiario.nome if detalhe else "",
            detalhe.prazo_dias if detalhe else "",
            detalhe.data_prevista_devolucao.isoformat() if detalhe else "",
            mov.observacoes,
        ])
    return resposta


def exportar_auditoria_csv(registros_qs, *, incluir_tenant: bool = False) -> HttpResponse:
    """
    `incluir_tenant=True` na visão cross-tenant do Owner — na visão por
    tenant do Admin/Gestor a coluna seria sempre o mesmo valor, então nem
    aparece (docs/business-rules/auditoria.md).
    """
    resposta, escritor = _resposta_csv("auditoria.csv")
    cabecalho = ["Quando", "Usuário", "Ação", "Objeto", "Sensível", "Descrição", "IP"]
    if incluir_tenant:
        cabecalho.insert(1, "Organização")
    escritor.writerow(cabecalho)

    for registro in registros_qs:
        objeto = registro.objeto_tipo
        if registro.objeto_id:
            objeto = f"{objeto} #{registro.objeto_id}"
        linha = [
            registro.criado_em.strftime("%d/%m/%Y %H:%M"),
            registro.usuario_identificacao,
            registro.get_acao_display(),
            objeto,
            "Sim" if registro.envolve_dado_sensivel else "Não",
            registro.descricao,
            registro.ip or "",
        ]
        if incluir_tenant:
            linha.insert(1, registro.tenant.nome if registro.tenant_id else "—")
        escritor.writerow(linha)
    return resposta

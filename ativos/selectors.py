"""
Consultas de leitura complexas isoladas da lógica de escrita (docs/ESPECIFICACAO_TECNICA.md §3.2)
— usadas pelo Dashboard, pela Lista de Ativos e pelo Mapa Operacional.
"""

from collections import defaultdict
from typing import Dict, Optional

from django.db.models import Count, Max
from django.utils import timezone

from ativos.domain.cores import CorOperacional, cor_operacional
from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.forms import CHECKLIST_ITENS_DEVOLUCAO, CHECKLIST_ITENS_EMPRESTIMO
from ativos.models import Ativo, DetalheEmprestimo, Movimentacao


def datas_previstas_por_ativo(ativos_ids=None) -> Dict[int, dict]:
    """Mapeia cada ativo emprestado à data prevista de devolução e ao beneficiário.

    Uma única query, evitando N+1 ao colorir uma lista inteira de
    ativos.

    Nota de implementação: como só existe um empréstimo "aberto" por
    ativo por vez (garantido pela máquina de estados —
    docs/PLANO_DOMINIO_ATIVOS.md §5.2), a primeira ocorrência ao iterar
    em ordem decrescente de data é a vigente; por isso o loop só define a
    chave se ainda não existir.

    Args:
        ativos_ids: Lista de PKs de `Ativo` a restringir a consulta. Se
            `None`, considera todos os ativos emprestados.

    Returns:
        Dicionário `{ativo_id: {"data_prevista_devolucao": date,
        "beneficiario": Beneficiario}}`, só com os ativos que têm
        empréstimo em aberto.
    """
    qs = DetalheEmprestimo.objects.filter(
        movimentacao__ativo__status=StatusAtivo.EMPRESTADO.value
    ).select_related("movimentacao", "beneficiario")
    if ativos_ids is not None:
        qs = qs.filter(movimentacao__ativo_id__in=ativos_ids)
    qs = qs.order_by("-movimentacao__data_hora")

    resultado: Dict[int, dict] = {}
    for detalhe in qs:
        ativo_id = detalhe.movimentacao.ativo_id
        if ativo_id not in resultado:
            resultado[ativo_id] = {
                "data_prevista_devolucao": detalhe.data_prevista_devolucao,
                "beneficiario": detalhe.beneficiario,
            }
    return resultado


def cor_de(ativo: Ativo, contexto_emprestimo: Optional[dict] = None, hoje=None) -> CorOperacional:
    """Calcula a cor operacional de um ativo específico.

    Args:
        ativo: O `Ativo` a colorir.
        contexto_emprestimo: Dicionário com `data_prevista_devolucao`,
            no formato devolvido por `datas_previstas_por_ativo`. Só
            relevante quando `ativo.status_enum` for `EMPRESTADO`.
        hoje: Data de referência para o cálculo. Default a data corrente.

    Returns:
        A `CorOperacional` do ativo (ver
        `ativos.domain.cores.cor_operacional`).
    """
    hoje = hoje or timezone.now().date()
    data_prevista = None
    if contexto_emprestimo:
        data_prevista = contexto_emprestimo.get("data_prevista_devolucao")
    return cor_operacional(ativo.status_enum, data_prevista, hoje=hoje)


def resumo_cores(ativos_qs) -> Dict[str, int]:
    """Conta os ativos de um queryset por cor operacional.

    Usado no resumo colorido do Dashboard. Materializa o queryset
    inteiro — para um dashboard com muitos ativos, prefira
    `resumo_cores_agregado`.

    Args:
        ativos_qs: Queryset de `Ativo` a resumir.

    Returns:
        Dicionário `{cor.value: quantidade}`.
    """
    ativos = list(ativos_qs)
    contexto = datas_previstas_por_ativo([a.id for a in ativos])
    hoje = timezone.now().date()
    contagem: Dict[str, int] = defaultdict(int)
    for ativo in ativos:
        cor = cor_de(ativo, contexto.get(ativo.id), hoje=hoje)
        contagem[cor.value] += 1
    return dict(contagem)


def mapa_operacional(ativos_qs):
    """Agrega os ativos filtrados em duas visões: por Unidade e por Bairro.

    Ver docs — Módulo Mapa Operacional de Ativos.

    - por Unidade: onde o ativo está fisicamente alocado.
    - por Bairro: do beneficiário, apenas para ativos emprestados (não é
      geolocalização em tempo real — é o endereço cadastrado, conforme
      decisão explícita do módulo).

    Args:
        ativos_qs: Queryset de `Ativo` já filtrado pelo escopo desejado.

    Returns:
        Dicionário `{"por_unidade": [...], "por_bairro": [...]}`, cada
        lista com itens `{"nome": ..., "total": ..., "cores":
        {cor.value: quantidade}}`, ordenados por `total` decrescente.
    """
    ativos = list(ativos_qs.select_related("categoria", "unidade"))
    contexto = datas_previstas_por_ativo([a.id for a in ativos])
    hoje = timezone.now().date()

    por_unidade: Dict[str, dict] = {}
    por_bairro: Dict[str, dict] = {}

    for ativo in ativos:
        info = contexto.get(ativo.id)
        cor = cor_de(ativo, info, hoje=hoje)

        nome_unidade = ativo.unidade.nome if ativo.unidade else "Sem unidade definida"
        bucket_unidade = por_unidade.setdefault(nome_unidade, {"total": 0, "cores": defaultdict(int)})
        bucket_unidade["total"] += 1
        bucket_unidade["cores"][cor.value] += 1

        if ativo.status_enum == StatusAtivo.EMPRESTADO and info and info.get("beneficiario"):
            bairro = info["beneficiario"].bairro or "Bairro não informado"
            bucket_bairro = por_bairro.setdefault(bairro, {"total": 0, "cores": defaultdict(int)})
            bucket_bairro["total"] += 1
            bucket_bairro["cores"][cor.value] += 1

    def _finalizar(buckets: dict) -> list:
        """Converte os buckets acumulados em lista ordenada por total decrescente.

        Args:
            buckets: Dicionário intermediário `{chave: {"total": int,
                "cores": dict}}`.

        Returns:
            Lista de `{"nome": ..., "total": ..., "cores": ...}`.
        """
        itens = [{"nome": nome, "total": dados["total"], "cores": dict(dados["cores"])} for nome, dados in buckets.items()]
        return sorted(itens, key=lambda item: item["total"], reverse=True)

    return {
        "por_unidade": _finalizar(por_unidade),
        "por_bairro": _finalizar(por_bairro),
    }


#: Rótulos de checklist, por tipo de movimentação — é o mesmo catálogo que
#: os formulários de empréstimo/devolução usam para desenhar as caixinhas
#: (ativos/forms.py), reaproveitado aqui para traduzir a chave técnica
#: salva em `Movimentacao.dados_especificos` no rótulo que um humano lê.
_ROTULOS_CHECKLIST_POR_TIPO = {
    TipoMovimentacao.EMPRESTIMO.value: dict(CHECKLIST_ITENS_EMPRESTIMO),
    TipoMovimentacao.DEVOLUCAO.value: dict(CHECKLIST_ITENS_DEVOLUCAO),
}


def checklist_detalhado(movimentacao: Movimentacao) -> list[dict]:
    """Traduz o checklist bruto salvo em `dados_especificos` para exibição.

    Existe para responder exatamente o cenário que motivou o pedido: um
    funcionário confirma no check-in/devolução que o ativo "está em boas
    condições", mas na prática não estava — e depois é preciso ver,
    ativo a ativo, quem marcou o quê e quando (`movimentacao.usuario` e
    `movimentacao.data_hora` já existem no model; isto só decodifica o
    conteúdo do checklist em si, que sem isso fica ilegível como JSON
    cru).

    Args:
        movimentacao: A `Movimentacao` cujo checklist será decodificado.

    Returns:
        Lista de `{"rotulo": str, "marcado": bool}`, na ordem em que os
        itens aparecem no formulário. Lista vazia para tipos de
        movimentação sem checklist (retorno de manutenção, renovação
        etc.) — nada a mostrar, não é erro.
    """
    rotulos = _ROTULOS_CHECKLIST_POR_TIPO.get(movimentacao.tipo)
    if not rotulos:
        return []

    checklist = movimentacao.dados_especificos.get("checklist") or {}
    return [
        {"rotulo": rotulo, "marcado": bool(checklist.get(chave, False))}
        for chave, rotulo in rotulos.items()
    ]


#: Status considerados "fora de operação" no resumo por unidade — não
#: entram na conta de disponível/emprestado/manutenção, mas o total tem de
#: fechar com a quantidade real de ativos da unidade.
_STATUS_DESTAQUE_UNIDADE = [
    StatusAtivo.DISPONIVEL,
    StatusAtivo.EMPRESTADO,
    StatusAtivo.MANUTENCAO,
]


def indicadores_por_status(ativos_qs) -> Dict[str, int]:
    """Conta os ativos de um queryset por status, em uma única consulta agregada.

    Substitui o padrão anterior de um `COUNT(*)` por status (8 queries
    para montar o cabeçalho do dashboard). O ganho real não é o número de
    round-trips: é que a contagem passa a ser resolvida pelo banco em
    cima do índice, sem trazer linha nenhuma para a aplicação —
    docs/business-rules/dashboard.md.

    Args:
        ativos_qs: Queryset de `Ativo` a resumir.

    Returns:
        Dicionário `{status.value: quantidade}`, com todos os valores de
        `StatusAtivo` presentes (zerados quando não há ativo naquele
        status).
    """
    contagem = {status.value: 0 for status in StatusAtivo}
    for linha in ativos_qs.values("status").annotate(total=Count("id")):
        contagem[linha["status"]] = linha["total"]
    return contagem


def resumo_por_unidade(ativos_qs) -> list[dict]:
    """Resume total/disponíveis/emprestados/em manutenção por unidade.

    Uma única consulta (docs/business-rules/dashboard.md — "Dashboard
    por Unidade"). Agrupa por `unidade` e `status` de uma vez e pivota
    em memória sobre o resultado agregado (poucas dezenas de linhas), em
    vez de rodar uma consulta por unidade × status.

    Args:
        ativos_qs: Queryset de `Ativo` a resumir.

    Returns:
        Lista de dicionários, um por unidade, com `unidade_id`, `nome`,
        `total` e a contagem para cada status em
        `_STATUS_DESTAQUE_UNIDADE`, ordenada por `total` decrescente.
    """
    linhas = ativos_qs.values("unidade_id", "unidade__nome", "status").annotate(
        total=Count("id")
    )

    por_unidade: Dict[object, dict] = {}
    for linha in linhas:
        chave = linha["unidade_id"]
        bucket = por_unidade.setdefault(
            chave,
            {
                "unidade_id": chave,
                "nome": linha["unidade__nome"] or "Sem unidade definida",
                "total": 0,
                **{status.value: 0 for status in _STATUS_DESTAQUE_UNIDADE},
            },
        )
        bucket["total"] += linha["total"]
        if linha["status"] in bucket:
            bucket[linha["status"]] += linha["total"]

    return sorted(por_unidade.values(), key=lambda item: item["total"], reverse=True)


def resumo_cores_agregado(ativos_qs) -> Dict[str, int]:
    """Conta os ativos por cor operacional sem carregar todos na memória.

    `resumo_cores` (acima) materializa o queryset inteiro porque precisa
    do objeto Ativo para colorir item a item — aceitável numa lista
    paginada, caro no dashboard de um tenant com muitos ativos. Aqui a
    conta é feita em duas consultas: uma agregação por status (que já
    resolve todas as cores que não dependem de prazo) e uma varredura
    apenas dos ativos EMPRESTADOS, cuja cor depende da data prevista de
    devolução.

    Args:
        ativos_qs: Queryset de `Ativo` a resumir.

    Returns:
        Dicionário `{cor.value: quantidade}`.
    """
    por_status = indicadores_por_status(ativos_qs)
    hoje = timezone.now().date()
    contagem: Dict[str, int] = defaultdict(int)

    for status in StatusAtivo:
        total = por_status.get(status.value, 0)
        if not total or status == StatusAtivo.EMPRESTADO:
            continue
        # Sem empréstimo em aberto, a cor é função apenas do status.
        contagem[cor_operacional(status, None, hoje=hoje).value] += total

    emprestados = ativos_qs.filter(status=StatusAtivo.EMPRESTADO.value).values_list("id", flat=True)
    datas = datas_previstas_por_ativo(list(emprestados))
    for ativo_id in emprestados:
        info = datas.get(ativo_id)
        data_prevista = info.get("data_prevista_devolucao") if info else None
        contagem[cor_operacional(StatusAtivo.EMPRESTADO, data_prevista, hoje=hoje).value] += 1

    return dict(contagem)


def anotar_impressoes(ativos_qs):
    """Anota contagem e data da última impressão de etiqueta, em lote.

    Evita o N+1 que as properties `Ativo.total_impressoes`/
    `ultima_impressao` causariam ao serem lidas dentro de um loop de
    template (docs/business-rules/etiquetas.md).

    Args:
        ativos_qs: Queryset de `Ativo` a anotar.

    Returns:
        O mesmo queryset, com as anotações `qtd_impressoes` (int) e
        `impresso_em_ultima` (datetime ou `None`) acrescentadas.
    """
    return ativos_qs.annotate(
        qtd_impressoes=Count("impressoes", distinct=True),
        impresso_em_ultima=Max("impressoes__impresso_em"),
    )


def resolver_busca_patrimonio(termo: str, ativos_qs=None):
    """Busca um ativo por patrimônio exato (case-insensitive).

    Usado pela caixa de pesquisa do Mapa Operacional.

    Args:
        termo: O código patrimonial buscado.
        ativos_qs: Queryset de `Ativo` já restrito ao escopo de unidade
            do usuário. Se omitido, usa `Ativo.objects.all()` — sem essa
            restrição pela view, a pesquisa por patrimônio viraria uma
            porta lateral para consultar um ativo de unidade que o
            usuário não opera.

    Returns:
        `None` se nenhum ativo corresponder a `termo`. Caso contrário,
        dicionário com `ativo`, `cor` (`CorOperacional`), `beneficiario`,
        `data_prevista_devolucao` e `ultima_movimentacao`.
    """
    base = ativos_qs if ativos_qs is not None else Ativo.objects.all()
    ativo = base.select_related("categoria", "unidade").filter(patrimonio__iexact=termo).first()
    if ativo is None:
        return None
    contexto = datas_previstas_por_ativo([ativo.id]).get(ativo.id)
    cor = cor_de(ativo, contexto)
    ultima_movimentacao = ativo.movimentacoes.select_related("usuario").first()
    return {
        "ativo": ativo,
        "cor": cor,
        "beneficiario": contexto.get("beneficiario") if contexto else None,
        "data_prevista_devolucao": contexto.get("data_prevista_devolucao") if contexto else None,
        "ultima_movimentacao": ultima_movimentacao,
    }

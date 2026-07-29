"""
Consultas de leitura complexas isoladas da lógica de escrita (docs/ESPECIFICACAO_TECNICA.md §3.2)
— usadas pelo Dashboard, pela Lista de Ativos e pelo Mapa Operacional.
"""

from collections import defaultdict
from typing import Dict, Optional

from django.utils import timezone

from ativos.domain.cores import CorOperacional, cor_operacional
from ativos.domain.enums import StatusAtivo, TipoMovimentacao
from ativos.forms import CHECKLIST_ITENS_DEVOLUCAO, CHECKLIST_ITENS_EMPRESTIMO
from ativos.models import Ativo, DetalheEmprestimo, Movimentacao


def datas_previstas_por_ativo(ativos_ids=None) -> Dict[int, dict]:
    """
    Para cada ativo atualmente emprestado, a data prevista de devolução e
    o beneficiário do empréstimo em aberto — uma única query, evitando
    N+1 ao colorir uma lista inteira de ativos.

    Como só existe um empréstimo "aberto" por ativo por vez (garantido
    pela máquina de estados — docs/PLANO_DOMINIO_ATIVOS.md §5.2), a
    primeira ocorrência ao iterar em ordem decrescente de data é a
    vigente; por isso o loop só define a chave se ainda não existir.
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
    hoje = hoje or timezone.now().date()
    data_prevista = None
    if contexto_emprestimo:
        data_prevista = contexto_emprestimo.get("data_prevista_devolucao")
    return cor_operacional(ativo.status_enum, data_prevista, hoje=hoje)


def resumo_cores(ativos_qs) -> Dict[str, int]:
    """Contagem por cor operacional — usado no resumo colorido do Dashboard."""
    ativos = list(ativos_qs)
    contexto = datas_previstas_por_ativo([a.id for a in ativos])
    hoje = timezone.now().date()
    contagem: Dict[str, int] = defaultdict(int)
    for ativo in ativos:
        cor = cor_de(ativo, contexto.get(ativo.id), hoje=hoje)
        contagem[cor.value] += 1
    return dict(contagem)


def mapa_operacional(ativos_qs):
    """
    Agrega os ativos filtrados em duas visões (docs — Módulo Mapa
    Operacional de Ativos):

    - por Unidade: onde o ativo está fisicamente alocado.
    - por Bairro: do beneficiário, apenas para ativos emprestados (não é
      geolocalização em tempo real — é o endereço cadastrado, conforme
      decisão explícita do módulo).
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
    """
    Traduz o checklist bruto salvo em `dados_especificos` para uma lista de
    `{"rotulo": ..., "marcado": bool}`, na ordem em que os itens aparecem no
    formulário.

    Existe para responder exatamente o cenário que motivou o pedido: um
    funcionário confirma no check-in/devolução que o ativo "está em boas
    condições", mas na prática não estava — e depois é preciso ver, ativo a
    ativo, *quem* marcou *o quê* e *quando* (`movimentacao.usuario` e
    `movimentacao.data_hora` já existem no model; isto só decodifica o
    conteúdo do checklist em si, que sem isso fica ilegível como JSON cru).

    Devolve lista vazia para tipos de movimentação sem checklist (retorna
    de manutenção, renovação etc.) — nada a mostrar, não é erro.
    """
    rotulos = _ROTULOS_CHECKLIST_POR_TIPO.get(movimentacao.tipo)
    if not rotulos:
        return []

    checklist = movimentacao.dados_especificos.get("checklist") or {}
    return [
        {"rotulo": rotulo, "marcado": bool(checklist.get(chave, False))}
        for chave, rotulo in rotulos.items()
    ]


def resolver_busca_patrimonio(termo: str):
    """Busca exata (case-insensitive) por patrimônio, para a caixa de pesquisa do Mapa."""
    ativo = Ativo.objects.select_related("categoria", "unidade").filter(patrimonio__iexact=termo).first()
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

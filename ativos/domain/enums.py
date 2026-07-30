"""
Enums de domínio do Ativo — deliberadamente `enum.Enum` puro, sem
dependência de Django.

Justificativa (docs/PLANO_DOMINIO_ATIVOS.md §1): a máquina de estados é a
parte do sistema com maior densidade de regra de negócio e a mais
reaproveitada (QR Code, ficha, painel rápido, API). Mantê-la livre de
framework permite testá-la em isolamento total (sem banco, sem settings
Django) e é o único ponto do produto onde vale pagar esse desacoplamento —
ver a justificativa de "DDD cirúrgico" no mesmo documento.

`ativos/models.py` deriva os `choices` do Django a partir destes mesmos
enums, para nunca haver duas fontes de verdade sobre os valores válidos.
"""

from enum import Enum


class StatusAtivo(str, Enum):
    DISPONIVEL = "disponivel"
    EMPRESTADO = "emprestado"
    RESERVADO = "reservado"
    MANUTENCAO = "manutencao"
    HIGIENIZACAO = "higienizacao"
    BAIXADO = "baixado"
    EXTRAVIADO = "extraviado"
    INATIVO = "inativo"

    @property
    def rotulo(self) -> str:
        return _ROTULOS_STATUS[self]


_ROTULOS_STATUS = {
    StatusAtivo.DISPONIVEL: "Disponível",
    StatusAtivo.EMPRESTADO: "Emprestado",
    StatusAtivo.RESERVADO: "Reservado",
    StatusAtivo.MANUTENCAO: "Em Manutenção",
    StatusAtivo.HIGIENIZACAO: "Em Higienização",
    StatusAtivo.BAIXADO: "Baixado",
    StatusAtivo.EXTRAVIADO: "Extraviado",
    StatusAtivo.INATIVO: "Inativo",
}


class TipoMovimentacao(str, Enum):
    EMPRESTIMO = "emprestimo"
    DEVOLUCAO = "devolucao"
    RENOVACAO = "renovacao"
    TRANSFERENCIA = "transferencia"
    RESERVA = "reserva"
    MANUTENCAO = "manutencao"
    RETORNO_MANUTENCAO = "retorno_manutencao"
    HIGIENIZACAO = "higienizacao"
    BAIXA = "baixa"
    EXTRAVIO = "extravio"
    #: Ativo extraviado que foi encontrado. Antes desta separação, a
    #: recuperação era registrada como `transferencia` — o que deixava o
    #: tipo com dois significados incompatíveis e impedia usá-lo para o que
    #: o nome diz (mudança de unidade responsável). Ver a migration
    #: `ativos/migrations/0005_*` para a reclassificação dos registros
    #: históricos.
    RECUPERACAO = "recuperacao"

    @property
    def rotulo(self) -> str:
        return _ROTULOS_TIPO[self]


_ROTULOS_TIPO = {
    TipoMovimentacao.EMPRESTIMO: "Empréstimo",
    TipoMovimentacao.DEVOLUCAO: "Devolução",
    TipoMovimentacao.RENOVACAO: "Renovação",
    TipoMovimentacao.TRANSFERENCIA: "Transferência entre Unidades",
    TipoMovimentacao.RESERVA: "Reserva",
    TipoMovimentacao.MANUTENCAO: "Manutenção",
    TipoMovimentacao.RETORNO_MANUTENCAO: "Retorno de Manutenção",
    TipoMovimentacao.HIGIENIZACAO: "Higienização",
    TipoMovimentacao.BAIXA: "Baixa Patrimonial",
    TipoMovimentacao.EXTRAVIO: "Extravio",
    TipoMovimentacao.RECUPERACAO: "Recuperação de Extravio",
}

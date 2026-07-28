"""
Cor operacional do Ativo — mesma lógica usada em toda a plataforma
(dashboard, listagens, ficha, timeline, mapa), conforme decisão de
produto: o gestor deve identificar a situação só pela cor, sem precisar
ler o status em texto.

Paleta oficial:
    azul            -> disponível (neutro, aguardando ação)
    verde           -> emprestado, dentro do prazo (situação saudável)
    verde_claro     -> emprestado, vence em até 7 dias (atenção)
    amarelo         -> em manutenção (atenção)
    vermelho_claro  -> atrasado até 7 dias
    vermelho_medio  -> atrasado de 8 a 30 dias
    vermelho_escuro -> atrasado há mais de 30 dias (ação urgente)
    cinza           -> baixado / extraviado / inativo / reservado / higienização (fora de operação ou transitório)

Pura (sem Django), assim como o restante do domínio — ver
ativos/domain/state_machine.py para a mesma justificativa.
"""

from datetime import date
from enum import Enum
from typing import Optional

from ativos.domain.enums import StatusAtivo


class CorOperacional(str, Enum):
    AZUL = "azul"
    VERDE = "verde"
    VERDE_CLARO = "verde_claro"
    AMARELO = "amarelo"
    VERMELHO_CLARO = "vermelho_claro"
    VERMELHO_MEDIO = "vermelho_medio"
    VERMELHO_ESCURO = "vermelho_escuro"
    CINZA = "cinza"

    @property
    def rotulo(self) -> str:
        return _ROTULOS[self]


_ROTULOS = {
    CorOperacional.AZUL: "Disponível",
    CorOperacional.VERDE: "Emprestado · dentro do prazo",
    CorOperacional.VERDE_CLARO: "Emprestado · vence em breve",
    CorOperacional.AMARELO: "Em manutenção",
    CorOperacional.VERMELHO_CLARO: "Atrasado",
    CorOperacional.VERMELHO_MEDIO: "Atrasado",
    CorOperacional.VERMELHO_ESCURO: "Atrasado",
    CorOperacional.CINZA: "Fora de operação",
}

_LIMIAR_PROXIMO_VENCIMENTO_DIAS = 7
_LIMIAR_ATRASO_MEDIO_DIAS = 8
_LIMIAR_ATRASO_GRAVE_DIAS = 30


def cor_operacional(
    status: StatusAtivo,
    data_prevista_devolucao: Optional[date] = None,
    hoje: Optional[date] = None,
) -> CorOperacional:
    hoje = hoje or date.today()

    if status == StatusAtivo.DISPONIVEL:
        return CorOperacional.AZUL
    if status == StatusAtivo.MANUTENCAO:
        return CorOperacional.AMARELO
    if status in (StatusAtivo.BAIXADO, StatusAtivo.EXTRAVIADO, StatusAtivo.INATIVO):
        return CorOperacional.CINZA
    if status in (StatusAtivo.RESERVADO, StatusAtivo.HIGIENIZACAO):
        return CorOperacional.CINZA

    if status == StatusAtivo.EMPRESTADO:
        if data_prevista_devolucao is None:
            return CorOperacional.VERDE
        dias = (data_prevista_devolucao - hoje).days
        if dias < 0:
            atraso = abs(dias)
            if atraso < _LIMIAR_ATRASO_MEDIO_DIAS:
                return CorOperacional.VERMELHO_CLARO
            if atraso <= _LIMIAR_ATRASO_GRAVE_DIAS:
                return CorOperacional.VERMELHO_MEDIO
            return CorOperacional.VERMELHO_ESCURO
        if dias <= _LIMIAR_PROXIMO_VENCIMENTO_DIAS:
            return CorOperacional.VERDE_CLARO
        return CorOperacional.VERDE

    return CorOperacional.CINZA

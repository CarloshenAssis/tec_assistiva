"""
Direitos do titular dos dados (LGPD Art. 18).

Implementa as duas operações que o controlador precisa conseguir executar sob
demanda e com prazo legal:

- **Portabilidade / acesso** (Art. 18, II e V): entregar ao titular, em
  formato estruturado, tudo que a plataforma tem sobre ele.
- **Eliminação** (Art. 18, VI): remover os dados identificáveis.

Sobre a eliminação — a operação aqui é *anonimização*, não `DELETE`. Não é um
atalho de implementação, é o comportamento correto:

1. O histórico de movimentação de um ativo é registro imutável por desenho
   (`ativos.Movimentacao`) e responde a uma finalidade distinta — prestação
   de contas sobre patrimônio público ou de terceiros. O Art. 16, I permite
   a conservação para cumprimento de obrigação legal.
2. O que a lei protege é a *identificabilidade* do titular. Dado anonimizado,
   nos termos do Art. 5º, XI, deixa de ser dado pessoal — logo, remover os
   identificadores satisfaz o direito sem destruir a trilha patrimonial.
3. Um `DELETE` em cascata levaria junto empréstimos e devoluções de
   equipamentos que continuam existindo no mundo físico.

Já os documentos anexados (laudo, receita médica — dado sensível) são
efetivamente **apagados do storage**: eles não têm função patrimonial, só
identificam.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from auditoria.models import AcaoAuditada
from auditoria.services import registrar

#: Marcador gravado nos campos de texto após a anonimização. Explícito de
#: propósito: string vazia seria indistinguível de "nunca preenchido".
MARCADOR_ANONIMO = "[anonimizado]"


def exportar_dados(beneficiario) -> dict[str, Any]:
    """
    Monta o pacote de dados do titular para atender ao direito de acesso e
    portabilidade.

    Formato de dicionário (serializável para JSON) em vez de arquivo pronto:
    quem chama decide se vira download, anexo de e-mail ou resposta de API,
    e a função continua testável sem tocar em I/O.
    """
    emprestimos = (
        beneficiario.emprestimos.select_related("movimentacao", "movimentacao__ativo")
        .order_by("-movimentacao__data_hora")
    )

    return {
        "titular": {
            "nome": beneficiario.nome,
            "cpf": beneficiario.cpf,
            "rg": beneficiario.rg,
            "data_nascimento": (
                beneficiario.data_nascimento.isoformat()
                if beneficiario.data_nascimento
                else None
            ),
            "telefone": beneficiario.telefone,
            "whatsapp": beneficiario.whatsapp,
            "email": beneficiario.email,
            "endereco": beneficiario.endereco,
            "bairro": beneficiario.bairro,
            "cidade": beneficiario.cidade,
            "cep": beneficiario.cep,
            "contato_emergencia": {
                "nome": beneficiario.contato_emergencia_nome,
                "telefone": beneficiario.contato_emergencia_telefone,
                "parentesco": beneficiario.contato_emergencia_parentesco,
            },
        },
        "tratamento": {
            "base_legal": beneficiario.get_base_legal_display(),
            "consentimento_em": (
                beneficiario.consentimento_em.isoformat()
                if beneficiario.consentimento_em
                else None
            ),
            "consentimento_revogado_em": (
                beneficiario.consentimento_revogado_em.isoformat()
                if beneficiario.consentimento_revogado_em
                else None
            ),
            "cadastrado_em": beneficiario.criado_em.isoformat(),
            "atualizado_em": beneficiario.atualizado_em.isoformat(),
        },
        "documentos": [
            {
                "tipo": documento.get_tipo_display(),
                "enviado_em": documento.enviado_em.isoformat(),
            }
            for documento in beneficiario.documentos.all()
        ],
        "emprestimos": [
            {
                "ativo_patrimonio": detalhe.movimentacao.ativo.patrimonio,
                "data": detalhe.movimentacao.data_hora.isoformat(),
                "prazo_dias": detalhe.prazo_dias,
                "data_prevista_devolucao": detalhe.data_prevista_devolucao.isoformat(),
            }
            for detalhe in emprestimos
        ],
    }


#: Campos de texto zerados na anonimização. `bairro` e `cidade` entram na
#: lista apesar de alimentarem o Mapa Operacional: localidade somada ao
#: histórico de equipamento é combinação suficiente para reidentificar uma
#: pessoa, e o Art. 5º, XI só considera anônimo o dado que não permite isso.
_CAMPOS_TEXTO_ANONIMIZAVEIS = (
    "rg",
    "telefone",
    "whatsapp",
    "email",
    "endereco",
    "bairro",
    "cidade",
    "cep",
    "contato_emergencia_nome",
    "contato_emergencia_telefone",
    "contato_emergencia_parentesco",
)


@transaction.atomic
def anonimizar(beneficiario, *, request=None, usuario=None) -> None:
    """
    Remove os dados identificáveis do titular, preservando a trilha patrimonial.

    Idempotente: chamar de novo em um titular já anonimizado não faz nada e
    não gera novo registro de auditoria.
    """
    if beneficiario.esta_anonimizado:
        return

    agora = timezone.now()

    beneficiario.nome = f"{MARCADOR_ANONIMO} #{beneficiario.pk}"
    # O CPF tem unicidade por tenant, então não pode virar string vazia em
    # massa — derivar do PK mantém a restrição satisfeita sem reter o número.
    beneficiario.cpf = f"000.000.000-{beneficiario.pk:02d}"[:14]
    beneficiario.data_nascimento = None

    for campo in _CAMPOS_TEXTO_ANONIMIZAVEIS:
        setattr(beneficiario, campo, "")

    beneficiario.anonimizado_em = agora
    beneficiario.save()

    # Documentos são dado pessoal sensível sem função patrimonial: apagados
    # do storage, não apenas desvinculados.
    for documento in beneficiario.documentos.all():
        if documento.arquivo:
            documento.arquivo.delete(save=False)
        documento.delete()

    registrar(
        AcaoAuditada.ANONIMIZACAO,
        request=request,
        usuario=usuario,
        tenant=beneficiario.tenant,
        objeto=beneficiario,
        descricao="Dados identificáveis removidos a pedido do titular (Art. 18, VI)",
        envolve_dado_sensivel=True,
    )


def revogar_consentimento(beneficiario, *, request=None, usuario=None) -> None:
    """
    Registra a revogação do consentimento (Art. 8º, §5º).

    Não anonimiza automaticamente: revogar consentimento interrompe o
    tratamento que dependia dele, mas o titular pode ter equipamento em posse,
    e a devolução é obrigação contratual com base legal própria. Anonimizar
    junto seria decidir pelo titular algo que ele não pediu.
    """
    if beneficiario.consentimento_revogado_em is not None:
        return

    beneficiario.consentimento_revogado_em = timezone.now()
    beneficiario.save(update_fields=["consentimento_revogado_em", "atualizado_em"])

    registrar(
        AcaoAuditada.CONSENTIMENTO_REVOGADO,
        request=request,
        usuario=usuario,
        tenant=beneficiario.tenant,
        objeto=beneficiario,
        descricao="Consentimento revogado pelo titular",
    )

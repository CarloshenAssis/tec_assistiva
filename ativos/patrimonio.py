"""
Geração de código patrimonial (docs/features/identificacao-patrimonial-e-unidades.md).

O usuário nunca é obrigado a digitar o código: ao deixar o campo em branco,
o sistema gera `PREFIXO-NNNNNN` sequencial por categoria e por tenant (ex.:
CAD-000001, CAD-000002...). Quem já tem patrimônio próprio (ex.: de um
sistema antigo) pode digitar o código personalizado — a validação de
unicidade nesse caso é feita no formulário (`ativos.forms.AtivoForm`), não
aqui.
"""

from __future__ import annotations

import re

from ativos.models import Ativo, CategoriaAtivo

#: Zero-padding do número sequencial — 6 dígitos cobre até 999.999 ativos
#: por categoria/tenant sem precisar mudar o formato depois.
_LARGURA_SEQUENCIA = 6


def _prefixo_de(categoria: CategoriaAtivo) -> str:
    if categoria.prefixo:
        return categoria.prefixo.strip().upper()
    # Deriva das letras do nome (ignora espaços/pontuação) — "Cadeira de
    # Rodas" -> "CAD". Sem o prefixo cadastrado, ainda assim gera algo
    # legível e estável (mesmo nome sempre deriva o mesmo prefixo).
    letras = re.sub(r"[^A-Za-z]", "", categoria.nome).upper()
    return letras[:3] or "AT"


def gerar_codigo_patrimonial(categoria: CategoriaAtivo) -> str:
    """
    Próximo código sequencial disponível para a categoria, no tenant dela.

    Não usa `COUNT(*) + 1` de propósito: se um ativo no meio da sequência
    for excluído (raro, mas possível via Django Admin), contar registros
    geraria um código já usado por outro ativo ainda existente. Em vez
    disso, olha o MAIOR número entre os ativos EXISTENTES com este prefixo e
    soma 1.

    Isso não é um contador persistente: se o ÚLTIMO ativo da sequência for
    excluído, o número dele pode ser reaproveitado no próximo cadastro. Não
    há fluxo de exclusão de ativo na aplicação (só baixa/mudança de status),
    então esse caso só ocorre via Django Admin — aceito como limitação
    conhecida em vez de justificar uma tabela de contador dedicada.
    """
    prefixo = _prefixo_de(categoria)
    padrao = re.compile(rf"^{re.escape(prefixo)}-(\d+)$")

    maior_numero = 0
    # `all_tenants()` + filtro explícito por `categoria` (que já pertence a
    # um tenant específico) — não pelo `Ativo.objects` normal, que depende
    # do ContextVar de tenant corrente (`core/tenancy.py`) e devolveria
    # vazio se esta função for chamada fora de uma requisição HTTP ativa
    # (ex.: um script de importação em lote, ou os próprios testes). Ver o
    # mesmo raciocínio em `core.unidades.unidades_visiveis`.
    codigos = Ativo.objects.all_tenants().filter(categoria=categoria).values_list(
        "patrimonio", flat=True
    )
    for codigo in codigos:
        m = padrao.match(codigo or "")
        if m:
            maior_numero = max(maior_numero, int(m.group(1)))

    proximo = maior_numero + 1
    return f"{prefixo}-{proximo:0{_LARGURA_SEQUENCIA}d}"

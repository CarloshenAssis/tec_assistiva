"""
Validadores reutilizáveis de entrada.

Dois grupos, com motivações distintas:

- **CPF**: qualidade do dado. A LGPD (Art. 6º, V) exige exatidão e relevância
  dos dados tratados; além disso, um CPF digitado errado no cadastro impede
  o titular de exercer os direitos do Art. 18 depois (ele não se encontra na
  própria base).
- **Upload**: superfície de ataque. Todo arquivo aceito é conteúdo controlado
  por quem envia; sem restrição de tipo e tamanho, o campo "laudo" vira
  vetor de XSS armazenado e de esgotamento de disco/memória.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError

# ---------------------------------------------------------------- CPF ----

_APENAS_DIGITOS = re.compile(r"\D")


def _digito_verificador(digitos: str, peso_inicial: int) -> str:
    soma = sum(int(d) * (peso_inicial - i) for i, d in enumerate(digitos))
    resto = (soma * 10) % 11
    return "0" if resto == 10 else str(resto)


def cpf_e_valido(valor: str) -> bool:
    """
    Confere os dois dígitos verificadores do CPF.

    Rejeita também as sequências de dígito repetido (`111.111.111-11` e
    companhia): elas passam no cálculo do verificador mas não são CPFs
    emitidos, e são exatamente o que se digita para "preencher o campo".
    """
    numeros = _APENAS_DIGITOS.sub("", valor or "")

    if len(numeros) != 11:
        return False
    if numeros == numeros[0] * 11:
        return False

    if _digito_verificador(numeros[:9], 10) != numeros[9]:
        return False
    return _digito_verificador(numeros[:10], 11) == numeros[10]


def validar_cpf(valor: str) -> None:
    """Validador no formato esperado pelo Django (levanta `ValidationError`)."""
    if not cpf_e_valido(valor):
        raise ValidationError("CPF inválido — confira os números digitados.", code="cpf_invalido")


def normalizar_cpf(valor: str) -> str:
    """Reduz o CPF a 11 dígitos, para que a unicidade por tenant não dependa da máscara."""
    return _APENAS_DIGITOS.sub("", valor or "")


# --------------------------------------------------------------- CNPJ ----

#: Pesos do cálculo de módulo 11 do CNPJ — não seguem uma progressão simples
#: (voltam a 9 depois de descer até 2), por isso ficam explícitos em vez de
#: gerados por fórmula.
_PESOS_CNPJ_PRIMEIRO_DIGITO = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_SEGUNDO_DIGITO = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def cnpj_e_valido(valor: str) -> bool:
    """Confere os dois dígitos verificadores do CNPJ, mesmo princípio de `cpf_e_valido`."""
    numeros = _APENAS_DIGITOS.sub("", valor or "")

    if len(numeros) != 14:
        return False
    if numeros == numeros[0] * 14:
        return False

    soma = sum(int(d) * peso for d, peso in zip(numeros[:12], _PESOS_CNPJ_PRIMEIRO_DIGITO))
    resto = soma % 11
    digito1 = "0" if resto < 2 else str(11 - resto)
    if numeros[12] != digito1:
        return False

    soma = sum(int(d) * peso for d, peso in zip(numeros[:13], _PESOS_CNPJ_SEGUNDO_DIGITO))
    resto = soma % 11
    digito2 = "0" if resto < 2 else str(11 - resto)
    return numeros[13] == digito2


def validar_cnpj(valor: str) -> None:
    if not cnpj_e_valido(valor):
        raise ValidationError("CNPJ inválido — confira os números digitados.", code="cnpj_invalido")


def normalizar_cnpj(valor: str) -> str:
    return _APENAS_DIGITOS.sub("", valor or "")


def validar_documento(valor: str, tipo_documento: str) -> None:
    """
    Despacha para `validar_cpf`/`validar_cnpj` conforme `tipo_documento`
    (`beneficiarios.models.Beneficiario.TipoDocumento`) — ponto único usado
    pelo formulário de cadastro, para o CPF e o CNPJ nunca terem validação
    divergente entre as duas telas que os usam.
    """
    if tipo_documento == "cnpj":
        validar_cnpj(valor)
    else:
        validar_cpf(valor)


# ------------------------------------------------------------- Upload ----

#: Allowlist — nunca uma blocklist. Extensão fora desta lista é recusada,
#: então um tipo novo e perigoso (hoje desconhecido) já nasce bloqueado.
EXTENSOES_DOCUMENTO_PERMITIDAS = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".webp"})
EXTENSOES_IMAGEM_PERMITIDAS = frozenset({".jpg", ".jpeg", ".png", ".webp"})

#: 10 MB. Um laudo digitalizado cabe folgadamente; acima disso é quase sempre
#: engano do usuário ou tentativa de esgotar recurso.
TAMANHO_MAXIMO_UPLOAD_BYTES = 10 * 1024 * 1024

#: Assinaturas de arquivo (magic numbers) dos formatos aceitos. Conferimos o
#: conteúdo porque a extensão é só o nome que quem envia escolheu — renomear
#: `payload.svg` para `laudo.png` é trivial.
_ASSINATURAS = {
    b"%PDF": ".pdf",
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp",  # RIFF....WEBP
}


def _extensao(nome: str) -> str:
    _, _, ext = (nome or "").rpartition(".")
    return f".{ext.lower()}" if ext else ""


def _conteudo_confere(arquivo) -> bool:
    """Lê os primeiros bytes e verifica se batem com algum formato aceito."""
    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    try:
        arquivo.seek(0)
        cabecalho = arquivo.read(16)
    except (AttributeError, OSError):
        # Storage que não permite leitura antecipada: a validação de extensão
        # e tamanho já foi feita, seguimos sem o reforço do magic number.
        return True
    finally:
        try:
            arquivo.seek(posicao)
        except (AttributeError, OSError):
            pass

    return any(cabecalho.startswith(assinatura) for assinatura in _ASSINATURAS)


def validar_upload(arquivo, *, extensoes_permitidas=EXTENSOES_DOCUMENTO_PERMITIDAS) -> None:
    """
    Valida extensão, tamanho e conteúdo real de um arquivo enviado.

    A verificação tripla é proposital: extensão barra o engano honesto,
    tamanho barra o abuso de recurso, e o magic number barra a renomeação
    maliciosa — que é o caso que realmente importa aqui, porque um SVG com
    script servido na origem da aplicação rouba a sessão de quem abrir.
    """
    if arquivo is None:
        return

    extensao = _extensao(getattr(arquivo, "name", ""))
    if extensao not in extensoes_permitidas:
        permitidas = ", ".join(sorted(extensoes_permitidas))
        raise ValidationError(
            f"Tipo de arquivo não permitido ({extensao or 'sem extensão'}). "
            f"Aceitos: {permitidas}.",
            code="extensao_nao_permitida",
        )

    tamanho = getattr(arquivo, "size", 0) or 0
    if tamanho > TAMANHO_MAXIMO_UPLOAD_BYTES:
        limite_mb = TAMANHO_MAXIMO_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError(
            f"Arquivo muito grande ({tamanho / 1024 / 1024:.1f} MB). "
            f"O limite é {limite_mb} MB.",
            code="arquivo_muito_grande",
        )

    if not _conteudo_confere(arquivo):
        raise ValidationError(
            "O conteúdo do arquivo não corresponde a um documento ou imagem "
            "válida. Envie o arquivo original, sem renomear a extensão.",
            code="conteudo_invalido",
        )


def validar_upload_imagem(arquivo) -> None:
    validar_upload(arquivo, extensoes_permitidas=EXTENSOES_IMAGEM_PERMITIDAS)

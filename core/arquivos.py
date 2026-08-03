"""
Entrega segura de arquivos enviados pelos usuários.

Motivação — o modelo ingênuo (`static(MEDIA_URL, document_root=MEDIA_ROOT)`)
serve qualquer arquivo por caminho, sem autenticação e sem noção de tenant.
Num sistema que armazena laudo e receita médica isso é vazamento de dado
pessoal sensível (LGPD Art. 5º, II c/c Art. 46): basta descobrir ou adivinhar
um caminho.

Aqui a entrega é sempre *por objeto*: a view resolve o registro pelo manager
com escopo de tenant, o que faz a verificação de propriedade virar uma
consulta ao banco em vez de uma comparação de string de caminho.

O segundo risco tratado é XSS armazenado. Um arquivo `.svg` ou `.html`
enviado como "laudo" e depois aberto na mesma origem da aplicação executa
script com a sessão da vítima. Por isso toda resposta sai como anexo, com
`Content-Type` neutro e `nosniff` — o navegador baixa, nunca renderiza.
"""

from __future__ import annotations

from django.http import FileResponse, Http404

#: Tipo genérico para toda entrega. Não usamos o content type adivinhado a
#: partir da extensão: se o arquivo for um SVG malicioso, `image/svg+xml`
#: reabre exatamente o vetor de XSS que o `attachment` fecha.
_TIPO_NEUTRO = "application/octet-stream"


def resposta_de_download(campo_arquivo, *, nome_sugerido: str = "") -> FileResponse:
    """Devolve o conteúdo de um `FileField`/`ImageField` como anexo seguro.

    A entrega é sempre por objeto: quem chama já deve ter resolvido o
    registro através de um manager com escopo de tenant, e passa o campo
    de arquivo já autorizado — esta função só cuida da resposta HTTP.

    Args:
        campo_arquivo: Um `FieldFile` (valor de `FileField`/`ImageField`)
            já resolvido e pertencente a um registro que o usuário tem
            permissão de acessar.
        nome_sugerido: Nome de arquivo a sugerir no cabeçalho
            `Content-Disposition`. Se omitido, usa o nome original do
            arquivo no storage.

    Returns:
        Uma `FileResponse` com `Content-Type` neutro
        (`application/octet-stream`), sempre como anexo (nunca renderizado
        inline) e sem cache compartilhado.

    Raises:
        django.http.Http404: Se `campo_arquivo` for vazio ou o arquivo não
            existir mais no storage — situação real em ambiente
            serverless, onde o disco não persiste entre invocações e um
            registro pode apontar para um arquivo que não está mais lá.
    """
    if not campo_arquivo:
        raise Http404("Arquivo não encontrado.")

    try:
        handle = campo_arquivo.open("rb")
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404("Arquivo não encontrado.") from exc

    resposta = FileResponse(
        handle,
        content_type=_TIPO_NEUTRO,
        as_attachment=True,
        filename=nome_sugerido or campo_arquivo.name.rsplit("/", 1)[-1],
    )
    # Reforça o que o `as_attachment` já sinaliza: nem o navegador nem um
    # proxy intermediário deve tentar inferir um tipo "melhor" e renderizar.
    resposta["X-Content-Type-Options"] = "nosniff"
    # Documento clínico não deve ficar em cache compartilhado.
    resposta["Cache-Control"] = "private, no-store"
    return resposta

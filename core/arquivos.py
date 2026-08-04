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

import mimetypes

from django.http import FileResponse, Http404

#: Tipo genérico para toda entrega. Não usamos o content type adivinhado a
#: partir da extensão: se o arquivo for um SVG malicioso, `image/svg+xml`
#: reabre exatamente o vetor de XSS que o `attachment` fecha.
_TIPO_NEUTRO = "application/octet-stream"

#: Um ano — mesmo raciocínio de cache "imutável" de qualquer asset com nome
#: de arquivo estável: `Storage.save()` do Django nunca sobrescreve um
#: caminho já existente (acrescenta um sufixo aleatório em caso de colisão
#: de nome), então o conteúdo em `campo_arquivo.name` nunca muda depois de
#: publicado — é seguro cachear por muito tempo.
_CACHE_IMAGEM_SEGUNDOS = 31536000


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


def resposta_de_imagem(campo_arquivo) -> FileResponse:
    """Devolve uma imagem já validada como conteúdo renderizável, com cache longo.

    Diferente de `resposta_de_download`: aqui o conteúdo é sempre um
    `ImageField` que já passou por `core.validadores.validar_upload_imagem`
    (extensão restrita a jpg/jpeg/png/webp, sem SVG — o vetor de XSS que
    justifica o tratamento neutro de `resposta_de_download` não existe
    aqui), então é seguro renderizar inline com o `Content-Type` real.

    Servida por uma view autenticada (nunca por link direto ao storage)
    para nunca gerar signed URL nova a cada carregamento de página — o
    problema que motivou esta função: sem uma URL estável, o navegador
    nunca reaproveita cache entre visitas, e cada render de uma ficha com
    fotos rebaixa o arquivo inteiro de novo do Supabase Storage.
    `Cache-Control: private` (não `public`) porque o acesso ainda depende
    de sessão autenticada e escopo de tenant/unidade — só o navegador de
    quem tem permissão pode cachear, nunca um proxy compartilhado.

    Args:
        campo_arquivo: Um `FieldFile` (valor de `ImageField`) já resolvido
            e pertencente a um registro que o usuário tem permissão de
            acessar.

    Returns:
        Uma `FileResponse` com o `Content-Type` real da imagem, renderizável
        inline, com `Cache-Control: private, max-age=31536000, immutable`.

    Raises:
        django.http.Http404: Se `campo_arquivo` for vazio ou o arquivo não
            existir mais no storage.
    """
    if not campo_arquivo:
        raise Http404("Imagem não encontrada.")

    try:
        handle = campo_arquivo.open("rb")
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404("Imagem não encontrada.") from exc

    tipo = mimetypes.guess_type(campo_arquivo.name)[0] or _TIPO_NEUTRO
    resposta = FileResponse(handle, content_type=tipo)
    resposta["Cache-Control"] = f"private, max-age={_CACHE_IMAGEM_SEGUNDOS}, immutable"
    return resposta

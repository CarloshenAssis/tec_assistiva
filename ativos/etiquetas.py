"""
Centro de Etiquetas — geração da folha de etiquetas patrimoniais
(docs/business-rules/etiquetas.md).

Decisão de arquitetura: a "geração de PDF" pedida na especificação é
resolvida por uma página HTML com CSS `@page` e a caixa de impressão do
navegador ("Salvar como PDF"), não por uma biblioteca de PDF no servidor.

Motivos, em ordem de peso:

1. Impressão de etiqueta é sempre um ato local — quem imprime está na frente
   da impressora e precisa escolher bandeja, escala e alinhamento do rolo. A
   caixa de diálogo do navegador dá esse controle; um PDF pronto do servidor
   tira.
2. `reportlab`/`weasyprint` no runtime serverless da Vercel significa peso de
   bundle e (no caso do weasyprint) bibliotecas de sistema — custo
   permanente para replicar o que o navegador já faz nativamente.
3. O resultado é o mesmo artefato: o usuário obtém um PDF se quiser, pela
   própria caixa de impressão.

Se um dia for preciso PDF sem intervenção humana (envio por e-mail, geração
em lote agendada), o ponto de troca é só a view que renderiza esta folha — o
cálculo de conteúdo das etiquetas fica aqui e é reaproveitável.
"""

from __future__ import annotations

import base64
import io

import qrcode

from ativos.models import LayoutEtiqueta

#: Quanto de conteúdo cabe em cada tamanho de etiqueta. O template lê estas
#: flags em vez de comparar strings de layout no HTML, para que acrescentar um
#: tamanho novo seja mudança de uma linha aqui.
_CONTEUDO_POR_LAYOUT = {
    LayoutEtiqueta.PEQUENO: {"categoria": False, "instituicao": False},
    LayoutEtiqueta.MEDIO: {"categoria": True, "instituicao": False},
    LayoutEtiqueta.GRANDE: {"categoria": True, "instituicao": True},
}


def _qr_data_uri(url: str) -> str:
    """
    QR Code como `data:` URI embutido no HTML.

    Não usamos `<img src="{% url 'qrcode_imagem' %}">` de propósito: uma folha
    de 60 etiquetas geraria 60 requisições ao servidor no momento da
    impressão, e qualquer uma que falhe imprime uma etiqueta sem QR — papel
    de etiqueta desperdiçado, que é o insumo caro aqui. Embutido, a folha é
    autocontida: o que apareceu na pré-visualização é exatamente o que sai
    na impressora. A CSP do produto já libera `data:` em `img-src`
    (core/middleware.py).
    """
    imagem = qrcode.make(url, box_size=4, border=1)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    codificado = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{codificado}"


def montar_etiquetas(ativos, url_de, instituicao: str, layout: str) -> list[dict]:
    """
    Constrói os dados de cada etiqueta da folha.

    `url_de(ativo)` é injetado pela view (que é quem sabe construir uma URL
    absoluta a partir da requisição) — mantém este módulo livre de `request`
    e, portanto, testável sem cliente HTTP.
    """
    conteudo = _CONTEUDO_POR_LAYOUT[LayoutEtiqueta(layout)]
    return [
        {
            "ativo": ativo,
            "qr": _qr_data_uri(url_de(ativo)),
            "patrimonio": ativo.patrimonio,
            "categoria": ativo.categoria.nome if conteudo["categoria"] else "",
            "instituicao": instituicao if conteudo["instituicao"] else "",
        }
        for ativo in ativos
    ]

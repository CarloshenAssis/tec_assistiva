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
import mimetypes

import qrcode

from ativos.models import LayoutEtiqueta

#: Dimensões físicas de cada tamanho de etiqueta, em milímetros — usadas
#: tanto pelo CSS de impressão (`templates/ativos/etiquetas_folha.html`)
#: quanto para decidir o layout da folha (etiqueta única vs. grade de
#: várias). Mudar um valor aqui exige mudar o CSS correspondente.
LAYOUT_DIMENSOES_MM = {
    LayoutEtiqueta.PEQUENO: (33, 22),
    LayoutEtiqueta.MEDIO: (50, 30),
    LayoutEtiqueta.GRANDE: (80, 50),
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


def _logo_data_uri(tenant) -> str:
    """
    Logotipo do tenant como `data:` URI embutido — mesmo raciocínio do QR:
    a folha precisa continuar autocontida, sem depender de uma requisição
    de rede ao storage (S3/Supabase) no momento da impressão.

    Devolve string vazia se o tenant não tiver logotipo configurado (ver
    `/app/instituicao/`) — o template cai de volta no símbolo padrão.
    """
    if not tenant.logo:
        return ""
    try:
        tenant.logo.open("rb")
        conteudo = tenant.logo.read()
    except (OSError, ValueError):
        # Arquivo referenciado no banco mas ausente/inacessível no storage —
        # etiqueta sai sem logo em vez de derrubar a geração da folha inteira.
        return ""
    finally:
        tenant.logo.close()
    mime = mimetypes.guess_type(tenant.logo.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(conteudo).decode('ascii')}"


def montar_etiquetas(ativos, url_de, tenant, layout: str) -> list[dict]:
    """
    Constrói os dados de cada etiqueta da folha.

    Todo tamanho mostra o mesmo conteúdo (QR, patrimônio, categoria, nome e
    logotipo da instituição) — só muda a escala física da etiqueta, não o
    que cabe nela. Decisão registrada em docs/business-rules/etiquetas.md.

    `url_de(ativo)` é injetado pela view (que é quem sabe construir uma URL
    absoluta a partir da requisição) — mantém este módulo livre de `request`
    e, portanto, testável sem cliente HTTP.
    """
    LayoutEtiqueta(layout)  # valida o valor, mesma exigência de antes
    logo = _logo_data_uri(tenant)
    return [
        {
            "ativo": ativo,
            "qr": _qr_data_uri(url_de(ativo)),
            "patrimonio": ativo.patrimonio,
            "categoria": ativo.categoria.nome,
            "instituicao": tenant.nome,
            "logo": logo,
        }
        for ativo in ativos
    ]

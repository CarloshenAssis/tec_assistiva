# Paginação das telas de lista

## Objetivo

Toda tela de lista (Ativos, Beneficiários, Notificações, Usuários,
Manutenção, Etiquetas, Unidades, Categorias, Fornecedores, Auditoria,
Contratos) usa o mesmo mecanismo de paginação, com tamanho de página
escolhível pelo usuário — em vez do corte fixo (`[:200]`, `[:500]`) que
várias telas usavam antes, sem paginação nenhuma: acima do corte, o resto
simplesmente não aparecia, sem aviso e sem link para "ver mais".

## Como funciona

- `core/paginacao.py::paginar(request, queryset)` lê `?pagina=` e
  `?por_pagina=` da querystring e devolve uma `Page` do Django.
- `?por_pagina=` só aceita os valores de `TAMANHOS_DISPONIVEIS` (10, 15,
  25, 30, 50, 100) — qualquer outro valor (ausente, não numérico, ou fora
  da lista) cai no padrão de 25. Isso é deliberado: sem a lista fechada,
  `?por_pagina=999999` viraria "traga o acervo inteiro numa página só",
  exatamente o problema que a paginação existe para evitar.
- `templates/_paginacao.html` é o componente visual único (resumo de
  total/página atual, seletor de tamanho, links anterior/próxima) — toda
  tela inclui o mesmo partial (`{% include "_paginacao.html" %}`) em vez de
  montar sua própria barra.
- O seletor de tamanho é um `<form method="get">` com um `<select>` que
  reenvia a página assim que o usuário escolhe uma opção — via
  `static/js/paginacao.js` (arquivo estático, não `onchange="..."` inline:
  a CSP do produto bloqueia atributo de evento inline do mesmo jeito que um
  `<script>` solto, `core/middleware.py`).
- Os links de "página anterior/seguinte" preservam qualquer filtro já
  aplicado (busca, categoria, ação, etc.) via a tag
  `{% querystring_trocando pagina=N %}` (`core/templatetags/
  querystring_extras.py`), que reaproveita a querystring atual trocando só
  o parâmetro pedido.

## Onde usar num model novo

Basta em: importar `from core.paginacao import paginar`, chamar
`pagina = paginar(request, queryset)` no lugar de um corte fixo, passar
`"pagina": pagina` no contexto do `render`, e incluir
`{% include "_paginacao.html" %}` no template logo depois da tabela.

## Auditoria (Admin/Gestor e Owner)

As duas telas de auditoria (`contas/views.py::auditoria_lista` e
`owner/views.py::auditoria`) já tinham paginação fixa em 50 registros via
`auditoria/selectors.py::listar_registros`. Essa função ganhou o parâmetro
`por_pagina` (mesma lista fechada de `core.paginacao`), e as duas telas
passaram a usar o mesmo partial — o que também corrigiu, de propósito, um
bug existente: o filtro "só dado sensível" (checkbox) se perdia ao trocar
de página, porque os links de anterior/próxima eram montados à mão sem
incluir esse parâmetro.

## Casos de exceção

- `ativos.views.etiquetas_historico` agrupa por lote de impressão antes de
  paginar — paginar os registros individuais primeiro poderia cortar um
  lote ao meio sem avisar.

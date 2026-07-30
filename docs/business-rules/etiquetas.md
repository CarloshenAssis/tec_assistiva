# Centro de Etiquetas

## Objetivo

Emitir as etiquetas patrimoniais dos ativos — individualmente ou em lote —
e saber, a qualquer momento, quais ativos ainda não têm etiqueta colada.

## Fluxo operacional

```text
Cadastrar ativo

↓

Entra automaticamente na fila de impressão

↓

Filtrar (categoria / unidade / status / só sem etiqueta)

↓

Selecionar ativos

↓

Escolher tamanho da etiqueta

↓

Gerar folha

↓

Imprimir (ou salvar como PDF)

↓

Histórico de impressão registrado
```

## Regras de negócio

- Todo ativo recém-cadastrado entra na **fila de impressão** — que é
  simplesmente "ativos que nunca tiveram etiqueta emitida". Não existe uma
  fila separada a ser mantida em sincronia: a fila é derivada do histórico,
  então nunca divergir dele é uma garantia estrutural, não um cuidado
  operacional.
- Três tamanhos de etiqueta, com conteúdo crescente:
  - **Pequeno (33×22 mm)**: QR Code + código patrimonial.
  - **Médio (50×30 mm)**: + categoria.
  - **Grande (80×50 mm)**: + nome da instituição, com o símbolo Ciclartech
    (traço único, `symbol-black.svg` inline — sem chamada de rede extra,
    pela mesma razão do QR embutido: a folha continua autocontida).
- Impressão em lote com filtros por categoria, unidade, status, e a opção
  "somente ativos sem etiqueta impressa". "Selecionar todos" marca apenas o
  que está visível na lista já filtrada — nunca o acervo inteiro.
- **Reimprimir é operação normal, não correção de erro.** O sistema registra
  "folha emitida" no momento em que a gera; não tem como saber se o papel
  saiu da impressora, se a etiqueta descolou ou se o ativo foi reformado.
  Cada emissão soma no contador, nenhuma substitui a anterior.
- Ativo **baixado** não tem etiqueta emitida: o item saiu do patrimônio, e
  uma etiqueta nova só confundiria o inventário. Fica fora da lista mesmo
  sem filtro de status.
- Na ficha do ativo (aba QR Code): "Última impressão", "Quantidade de
  impressões", botão "Reimprimir" e o histórico daquele ativo.
- Histórico de impressão é **append-only** — não pode ser alterado nem
  excluído, como `Movimentacao`.
- O histórico é agrupado por lote: "40 etiquetas médias em 12/03, por João",
  não 40 linhas soltas.

## Validações

- Layout fora dos três valores conhecidos é recusado (entrada do cliente
  como qualquer outra).
- Gerar folha exige POST — um GET tornaria o registro de impressão acionável
  por pré-visualização de link, inflando o histórico com impressões que
  nunca aconteceram.
- Nenhum ativo selecionado → mensagem de erro, não folha vazia.
- Só entram na folha ativos dentro do escopo de unidade do usuário, mesmo
  que o POST seja forjado com outros IDs.

## Permissões por perfil

| Ação | Nível mínimo |
|---|---|
| Acessar o Centro de Etiquetas | Funcionário |
| Gerar / reimprimir etiquetas | Funcionário |
| Ver histórico de impressão | Funcionário |

Imprimir etiqueta é tarefa de quem está com o ativo em mãos — exigir Gestor
só criaria fila de espera para colar adesivo.

## Estados possíveis

Do ponto de vista da etiqueta, um ativo está em um de dois estados:
**na fila** (nunca impressa) ou **etiquetado** (uma ou mais impressões
registradas). Não é um campo no ativo — é derivado do histórico.

## Casos de exceção

- Ativo em qualquer status operacional pode ter etiqueta impressa, exceto
  `Baixado`.
- Se a caixa de impressão do navegador não abrir automaticamente, a folha
  tem um botão de impressão visível só na tela (nunca no papel).

## Decisão de arquitetura: PDF pela caixa de impressão do navegador

A especificação pede "gerar PDF". Isso é atendido por uma página HTML com
CSS `@page` e a caixa de impressão do navegador ("Salvar como PDF"), não por
uma biblioteca de PDF no servidor. Motivos, em ordem de peso:

1. Impressão de etiqueta é sempre um ato local — quem imprime está na frente
   da impressora e precisa escolher bandeja, escala e alinhamento do rolo. A
   caixa de diálogo do navegador dá esse controle; um PDF pronto do servidor
   tira.
2. `reportlab`/`weasyprint` no runtime serverless significam peso de bundle
   e (no caso do weasyprint) bibliotecas de sistema — custo permanente para
   replicar o que o navegador já faz nativamente.
3. O usuário obtém um PDF se quiser, pela própria caixa de impressão. O
   artefato final é o mesmo.

Os QR Codes vão embutidos na página como `data:` URI, não como `<img src>`
apontando para o servidor: uma folha de 60 etiquetas geraria 60 requisições
no momento da impressão, e qualquer uma que falhasse imprimiria uma etiqueta
sem QR — papel de etiqueta desperdiçado, que é o insumo caro aqui.

Se um dia for preciso PDF sem intervenção humana (envio por e-mail, geração
agendada), o ponto de troca é só a view que renderiza a folha — o cálculo do
conteúdo das etiquetas (`ativos/etiquetas.py`) é reaproveitável.

## Impactos em outros módulos

- Depende do `qr_token` e do código patrimonial do ativo
  (`docs/business-rules/qrcode.md`).
- Respeita o escopo de unidade do usuário
  (`docs/business-rules/unidades.md`) — o Centro de Etiquetas não é porta
  lateral para ver o acervo de outra unidade.
- A ação "Imprimir Etiqueta" aparece no catálogo de ações do ativo
  (`docs/business-rules/arquitetura-funcional.md`), abrindo o Centro com o
  ativo já pré-marcado.

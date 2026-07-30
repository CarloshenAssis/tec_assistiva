# Dashboard

## Objetivo

Dar uma visão rápida da situação da frota de ativos do tenant: quantos
estão disponíveis, emprestados, em manutenção, e qual a taxa de utilização.

## Fluxo operacional

```text
Usuário acessa o Dashboard

↓

Sistema conta ativos por status

↓

Sistema lista as últimas movimentações
```

## Regras de negócio

- Métricas mostradas: total de ativos, disponíveis, emprestados, em
  manutenção, taxa de utilização (`emprestados / total × 100`).
- Resumo colorido por faixa de urgência: disponíveis, emprestados em dia,
  empréstimos vencendo em breve, em manutenção, atrasados (três faixas de
  gravidade), baixados/inativos.
- Últimas 10 movimentações aparecem na tela principal.
- **Todos os números respeitam o escopo de unidade do usuário**
  (`docs/business-rules/unidades.md`) — inclusive as contagens agregadas: um
  Gestor de uma unidade nunca vê no total um número que inclua ativos de
  outra, o que seria um vazamento pela agregação.
- **Dashboard por unidade**: quebra de total / disponíveis / emprestados / em
  manutenção por unidade, para quem enxerga mais de uma. Para um Gestor de
  unidade única a tabela não aparece — seria uma linha só, repetindo os
  cartões acima.
- Relatórios complementares: contagem por status, total de beneficiários,
  beneficiários com empréstimo ativo, total de notificações enviadas, e a
  mesma quebra por unidade.

## Validações

Não aplicável — o Dashboard é somente leitura.

## Permissões por perfil

Qualquer usuário autenticado do tenant (Funcionário em diante) acessa o
Dashboard, com os dados restritos às unidades que ele pode ver.

## Estados possíveis

Não aplicável.

## Casos de exceção

Não há caso de exceção de negócio — é uma tela de leitura agregada.

## Decisão de arquitetura: indicadores agregados no banco

A regra pedida era "Dashboard nunca consulta movimentações, consulta
indicadores já processados — muito mais rápido". O objetivo real — custo de
consulta que não cresce com o tamanho do acervo — é atendido por **agregação
no banco em consulta única**, não por uma tabela de indicadores
materializados:

- Contagem por status: uma consulta agregada (`GROUP BY status`), não uma
  contagem por status (eram 8 consultas).
- Resumo colorido: as cores que dependem só do status saem da mesma
  agregação; apenas os ativos **emprestados** — cuja cor depende da data
  prevista de devolução — são varridos, e não o acervo inteiro. Antes, a
  tela materializava todos os ativos do tenant em memória para colorir um a
  um.
- Quebra por unidade: uma consulta (`GROUP BY unidade, status`), pivotada
  sobre o resultado agregado (poucas dezenas de linhas).

Uma tabela materializada foi deliberadamente **não** construída: ela troca um
custo de consulta que já é O(1) por um risco permanente de divergência entre
o indicador e a realidade — e um dashboard que mostra número errado é pior
que um dashboard lento. Se o volume algum dia justificar, o ponto de troca
é apenas `ativos/selectors.py`, sem tocar nas views.

## Impactos em outros módulos

Consome dados de Ativos, Movimentações, Beneficiários e Notificações. Não
escreve em nenhum outro módulo.

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
- Últimas 10 movimentações do tenant aparecem na tela principal.
- Relatórios complementares: contagem por status, total de beneficiários,
  beneficiários com empréstimo ativo, total de notificações enviadas.

## Validações

Não aplicável — o Dashboard é somente leitura.

## Permissões por perfil

Qualquer usuário autenticado do tenant (Funcionário em diante) acessa o
Dashboard. O escopo de dados hoje é sempre o tenant inteiro — ver
Pendências abaixo.

## Estados possíveis

Não aplicável.

## Casos de exceção

Não há caso de exceção de negócio — é uma tela de leitura agregada.

## Pendências (divergências entre a regra desejada e o implementado hoje)

- **O Dashboard consulta o model `Ativo`/`Movimentacao` diretamente a cada
  acesso** (`Ativo.objects.filter(status=...).count()` por status), em vez
  de consultar indicadores já processados/pré-agregados. A regra de
  negócio desejada é "Dashboard nunca consulta movimentações, consulta
  indicadores já processados — muito mais rápido". Hoje isso ainda não é
  verdade; é uma otimização pendente para quando o volume de dados por
  tenant justificar (tabela de indicadores materializados, atualizada por
  job ou por sinal a cada movimentação).
- **Não há Dashboard por unidade.** As contagens são sempre globais ao
  tenant — quando `unidades_visiveis()` for aplicado às listagens (ver
  `docs/business-rules/unidades.md`), o Dashboard também deveria oferecer
  a visão segmentada por unidade para o Admin.

## Impactos em outros módulos

Consome dados de Ativos, Movimentações, Beneficiários e Notificações. Não
escreve em nenhum outro módulo.

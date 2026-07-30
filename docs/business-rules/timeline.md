# Timeline

## Objetivo

Garantir que nenhum evento relevante do ciclo de vida de um ativo aconteça
sem deixar rastro visível na ficha dele.

## Fluxo operacional

```text
Cadastro

↓

Emprestou / Reservou

↓

Renovou

↓

Devolveu (→ Disponível / Higienização / Manutenção)

↓

Manutenção

↓

Retornou da manutenção

↓

Baixado
```

Tudo registrado, na ordem em que aconteceu, sem edição posterior.

## Regras de negócio

- A Timeline de um ativo é construída diretamente a partir de
  `Movimentacao` (`ativos/models.py`) — não é um módulo separado, é a
  visão cronológica das movimentações daquele ativo específico.
- `Movimentacao` é **append-only**: o model bloqueia `delete()`
  explicitamente. Nenhum evento pode ser apagado do histórico.
- Cada entrada guarda: tipo, data/hora, usuário responsável, unidade (se
  houver), status anterior e status novo, observações, e dados específicos
  da ação (ex.: checklist marcado, novo prazo de renovação).
- O checklist de empréstimo/devolução aparece na Timeline detalhado item a
  item, com quem marcou cada item e quando — é assim que se responde
  "quem confirmou que o ativo estava em boas condições" quando ele aparece
  com problema depois.

## Validações

- Não é possível registrar uma movimentação fora das transições permitidas
  pela máquina de estados (`docs/business-rules/arquitetura-funcional.md`)
  — a Timeline nunca mostra uma sequência de status inconsistente.

## Permissões por perfil

Visualização da Timeline segue a mesma permissão de consulta do ativo
(Funcionário em diante). Não há edição de Timeline por nenhum perfil — só
leitura.

## Estados possíveis

Não aplicável — a Timeline reflete os estados do Ativo (ver
`docs/business-rules/ativos.md`).

## Casos de exceção

- Alterações feitas em massa via `bulk_create`/`bulk_update`/
  `QuerySet.update()` no admin do Django não passam pelos sinais de
  auditoria (ver `docs/business-rules/auditoria.md`) — mas a Timeline do
  ativo em si, por ser baseada em `Movimentacao`, só é alimentada pelos
  serviços de negócio (`ativos/services.py`), que sempre criam o registro
  explicitamente.

## Impactos em outros módulos

- É a fonte de dados para o Dashboard (movimentações recentes) e para os
  relatórios.
- É diferente e complementar à trilha de auditoria LGPD
  (`docs/business-rules/auditoria.md`): a Timeline conta a história
  operacional do ativo; a auditoria é a trilha de segurança/conformidade de
  quem alterou o quê no sistema como um todo.

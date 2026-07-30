# Empréstimos e Devoluções

## Objetivo

Registrar a saída de um ativo para um beneficiário e o seu retorno,
garantindo que nenhum ativo seja emprestado em condição incompatível com o
seu estado atual, e que toda devolução seja conferida antes de voltar ao
estoque.

## Fluxo operacional

```text
Buscar beneficiário

↓

Buscar ativo disponível

↓

Definir prazo

↓

Checklist + assinatura + confirmação

↓

Emprestado
```

```text
Emprestado

↓

Devolver

↓

Registrar fotos (opcional)

↓

Registrar observação

↓

Escolher destino:

* Disponível
* Higienização
* Manutenção
```

O empréstimo é conduzido por um wizard de 5 passos guardado em sessão
(`ativos/views.py::wizard_emprestimo`). O passo de busca de ativo só lista
ativos com status `Disponível` — um ativo emprestado, em manutenção ou
baixado nunca aparece como opção nesse passo.

## Regras de negócio

Um ativo somente pode ser emprestado quando:

- ✓ Estiver `Disponível` **ou** `Reservado` (confirmação de reserva vira
  empréstimo).
- ✓ Não estiver em manutenção.
- ✓ Não estiver baixado.
- ✓ Não possuir empréstimo ativo.

Se qualquer condição não for atendida, o sistema bloqueia — a ação
"Emprestar" simplesmente não aparece para o ativo naquele estado
(`ativos/domain/acoes.py::acoes_disponiveis`), e mesmo que a requisição seja
forjada diretamente, `executar_acao` recalcula as ações permitidas no
servidor e recusa qualquer código fora da lista.

Devolução:

- Só é possível existindo um empréstimo ativo.
- Exige a escolha de um destino: `Disponível`, `Higienização` ou
  `Manutenção`. **Nunca volta automaticamente para "Disponível"** — a
  escolha é sempre manual, porque o ativo pode retornar quebrado ou sujo.
- Fotos e observação são opcionais na devolução, mas o campo destino é
  obrigatório.

Renovação:

- Só é permitida com o ativo `Emprestado`.
- **Não muda o status do ativo** (continua `Emprestado`) — grava apenas o
  novo prazo (`novo_prazo_dias`, `nova_data_devolucao`) na movimentação.
- O registro original de retirada (`DetalheEmprestimo`) não é substituído;
  a renovação é um evento adicional na timeline, não uma reescrita do
  histórico.

Checklist:

- Empréstimo: rodas, freios, apoio de braço, apoio de pé, ferrugem,
  higienizado, termo impresso, termo assinado fisicamente pelo
  beneficiário.
- Devolução: estado igual à retirada, limpa, funcionando.
- Cada item marcado fica associado à `Movimentacao` (e, por consequência,
  ao `usuario` e ao `data_hora` daquela movimentação) — é assim que se
  responde "quem confirmou que estava em boas condições" quando um ativo
  aparece com problema depois.

## Validações

- Toda ação passa por `ativos/domain/state_machine.py`: transição fora da
  tabela permitida levanta erro (`TransicaoInvalidaError`) — nunca chega a
  gravar no banco.
- Destino de devolução fora de `{disponivel, higienizacao, manutencao}`
  gera erro de formulário amigável, nunca 500.
- Renovação exige `novo_prazo_dias >= 1`.

## Permissões por perfil

| Ação | Nível mínimo |
|---|---|
| Emprestar / confirmar reserva | Funcionário |
| Devolver | Funcionário |
| Renovar | Funcionário |
| Registrar extravio | Gestor |
| Registrar recuperação de ativo extraviado | Gestor |

## Estados possíveis

`Disponível`, `Reservado`, `Emprestado`, `Em Higienização`, `Em Manutenção`.

## Transições permitidas

| De | Ação | Para |
|---|---|---|
| Disponível | Emprestar | Emprestado |
| Disponível | Reservar | Reservado |
| Reservado | Confirmar empréstimo | Emprestado |
| Reservado | Cancelar reserva | Disponível |
| Emprestado | Renovar | Emprestado (sem mudança de status) |
| Emprestado | Devolver → Disponível | Disponível |
| Emprestado | Devolver → Higienização | Em Higienização |
| Emprestado | Devolver → Manutenção | Em Manutenção |
| Emprestado | Extravio | Extraviado |
| Disponível | Extravio | Extraviado |
| Em Higienização | Concluir higienização | Disponível |

## Casos de exceção

- Registrar extravio e registrar recuperação exigem **justificativa
  obrigatória**: sem o "por quê", o registro não tem nada a contar depois.
  Extravio pode ser registrado tanto a partir de `Emprestado` (o beneficiário
  não devolveu) quanto de `Disponível` (o inventário não encontrou o item na
  prateleira).
- Recuperação de extravio tem tipo próprio de movimentação
  (`Recuperação de Extravio`), separado de `Transferência entre Unidades` —
  antes os dois compartilhavam o mesmo tipo, o que deixava o histórico
  ambíguo.
- **Não se transfere ativo emprestado** entre unidades — ver
  `docs/business-rules/unidades.md`.
- Falha ao enviar a notificação de confirmação de empréstimo nunca impede o
  empréstimo em si — a notificação é best-effort (ver
  `docs/business-rules/notificacoes.md`).
- Todo o fluxo (busca de beneficiário, busca de ativo, devolução) respeita o
  escopo de unidade do usuário: o wizard não oferece ativo de unidade que ele
  não opera, e a busca da devolução não o encontra.

## Impactos em outros módulos

- Toda ação gera `Movimentacao`, visível na Timeline do ativo.
- Empréstimo dispara notificação de confirmação; a proximidade/vencimento
  do prazo dispara avisos automáticos diários (7 dias antes, no vencimento,
  em atraso).
- Contagem de "emprestados" no Dashboard reflete diretamente o status do
  ativo após cada operação.

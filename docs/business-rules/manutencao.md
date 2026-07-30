# Manutenção

## Objetivo

Registrar o envio de um ativo para conserto e o seu retorno ao estoque,
sempre com motivo e responsável identificados.

## Fluxo operacional

```text
Disponível (ou Emprestado, via devolução)

↓

Enviar para manutenção

↓

Em Manutenção

↓

Finalizar manutenção

↓

Disponível
```

Um ativo chega em manutenção por dois caminhos: diretamente do estoque
(ação "Enviar para manutenção") ou como destino escolhido numa devolução
(ver `docs/business-rules/emprestimos.md`).

## Regras de negócio

- Só é possível enviar para manutenção um ativo `Disponível` (fora do
  fluxo de devolução).
- Enviar para manutenção exige motivo; fornecedor e valor são opcionais.
- **Corrigir os dados da manutenção em curso é permitido ao Funcionário.**
  Quem está com o ativo na oficina é quem sabe o motivo real, o fornecedor e
  o valor — exigir aprovação de Gestor para isso só geraria dado errado
  esperando liberação. A correção fica rastreada na auditoria.
- O formulário de correção abre preenchido com os valores atuais: é uma
  correção, não um registro novo — abrir vazio convidaria a apagar dado.
- Finalizar manutenção só é possível com o ativo `Em Manutenção`, e sempre
  retorna para `Disponível` — nunca para `Emprestado` diretamente.
- Um ativo em manutenção pode ir direto para baixa (`Em Manutenção →
  Baixado`), quando o conserto é inviável.
- Cada envio para manutenção cria um registro `DetalheManutencao`
  (fornecedor, motivo, valor); ao finalizar, a `data_conclusao` do
  registro **mais recente** é preenchida.

## Validações

- Transição bloqueada pela máquina de estados fora dos casos acima.
- Formulário de envio (`EnviarManutencaoForm`) exige motivo (texto livre).

## Permissões por perfil

| Ação | Nível mínimo |
|---|---|
| Enviar para manutenção | Funcionário |
| Finalizar manutenção | Funcionário |
| Editar dados de manutenção em curso | Funcionário |
| Dar baixa a partir de manutenção | Gestor |

## Estados possíveis

`Disponível`, `Em Manutenção`, `Baixado`.

## Transições permitidas

| De | Ação | Para |
|---|---|---|
| Disponível | Enviar para manutenção | Em Manutenção |
| Emprestado | Devolver → Manutenção | Em Manutenção |
| Em Manutenção | Finalizar manutenção | Disponível |
| Em Manutenção | Transferir de unidade | Em Manutenção (sem troca de status) |
| Em Manutenção | Dar baixa | Baixado |

## Casos de exceção

- **Editar manutenção em curso não gera `Movimentacao`.** É correção de
  metadado (motivo/fornecedor/valor), não evento de estado: o ativo continua
  em manutenção. A alteração fica registrada na trilha de auditoria
  (`docs/business-rules/auditoria.md`), que guarda quem alterou, quais campos
  e quando. A Timeline registra transições de estado; a Auditoria registra
  alterações de dado — ver a distinção em `docs/business-rules/timeline.md`.
- Um ativo em manutenção sem registro de detalhe (importação antiga, ou
  manutenção criada fora dos serviços) tem o detalhe criado na primeira
  edição, em vez de erro na cara do operador — que não teria como resolver
  isso.
- Um ativo com múltiplas manutenções no histórico só tem a manutenção mais
  recente considerada ao finalizar ou editar — registros antigos permanecem
  intactos na timeline.

## Impactos em outros módulos

- Toda mudança gera `Movimentacao`, refletida na Timeline e no contador de
  "manutenção" do Dashboard.
- Enquanto `Em Manutenção`, o ativo não aparece como opção no wizard de
  empréstimo.

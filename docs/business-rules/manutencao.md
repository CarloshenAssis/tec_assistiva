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
| Editar dados de manutenção em curso | Gestor |
| Dar baixa a partir de manutenção | Gestor |

## Estados possíveis

`Disponível`, `Em Manutenção`, `Baixado`.

## Transições permitidas

| De | Ação | Para |
|---|---|---|
| Disponível | Enviar para manutenção | Em Manutenção |
| Emprestado | Devolver → Manutenção | Em Manutenção |
| Em Manutenção | Finalizar manutenção | Disponível |
| Em Manutenção | Dar baixa | Baixado |

## Casos de exceção

- A ação "Editar manutenção em curso" está definida no catálogo de ações
  (nível Gestor) mas **não tem handler correspondente** implementado nas
  views — funcionalidade pendente, não deve ser anunciada como disponível
  até ser implementada.
- Um ativo com múltiplas manutenções no histórico só tem a manutenção mais
  recente considerada ao finalizar — registros antigos permanecem intactos
  na timeline.

## Impactos em outros módulos

- Toda mudança gera `Movimentacao`, refletida na Timeline e no contador de
  "manutenção" do Dashboard.
- Enquanto `Em Manutenção`, o ativo não aparece como opção no wizard de
  empréstimo.

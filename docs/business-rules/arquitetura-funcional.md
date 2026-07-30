# Arquitetura Funcional da Plataforma

Este documento define os estados possíveis do sistema de forma que
qualquer funcionalidade nova respeite essas regras. Antes de desenvolver
uma tela, a pergunta é sempre: isso já está descrito aqui? Se não estiver,
o documento é atualizado primeiro — o código vem depois.

Este é o documento normativo para o modelo de estados do Ativo. Os demais
arquivos em `docs/business-rules/` referenciam este, em vez de duplicar a
tabela.

## Quais são os status válidos de um ativo?

`Disponível`, `Emprestado`, `Reservado`, `Em Manutenção`, `Em
Higienização`, `Extraviado`, `Inativo`, `Baixado`.

`Baixado` é estado **terminal**: a partir dele, nenhuma ação de
movimentação é oferecida — só consulta (histórico, fotos, timeline).

## Estados e transições do Ativo

```text
                    ┌──────────────┐
                    │  Disponível  │◄────────────────────────┐
                    └──────┬───────┘                          │
        ┌───────────┬──────┼──────┬────────────┐              │
        ▼           ▼      ▼      ▼            ▼              │
   Reservado   Emprestado  Manutenção   Baixado         Em Higienização
        │           │           │                              ▲
        │           │           └──────────────┐               │
        ▼           ▼                          ▼               │
   Disponível   Emprestado (renovar)      Disponível            │
   (cancelar)        │                    (finalizar)           │
                      ▼                                         │
                  Devolver
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   Disponível   Em Higienização  Manutenção
                      │
                      └──────────────────────────────────────────┘
```

| De | Evento | Para | Regra correspondente |
|---|---|---|---|
| Disponível | Emprestar | Emprestado | `emprestimos.md` |
| Disponível | Reservar | Reservado | `emprestimos.md` |
| Disponível | Enviar manutenção | Em Manutenção | `manutencao.md` |
| Disponível | Dar baixa | Baixado | `ativos.md` |
| Reservado | Confirmar empréstimo | Emprestado | `emprestimos.md` |
| Reservado | Cancelar reserva | Disponível | `emprestimos.md` |
| Emprestado | Renovar | Emprestado (sem troca de status) | `emprestimos.md` |
| Emprestado | Devolver → Disponível | Disponível | `emprestimos.md` |
| Emprestado | Devolver → Higienização | Em Higienização | `emprestimos.md` |
| Emprestado | Devolver → Manutenção | Em Manutenção | `emprestimos.md` |
| Emprestado | Extravio | Extraviado | `emprestimos.md` |
| Disponível | Extravio | Extraviado | `ativos.md` |
| Em Higienização | Concluir higienização | Disponível | `emprestimos.md` |
| Em Manutenção | Finalizar manutenção | Disponível | `manutencao.md` |
| Em Manutenção | Dar baixa | Baixado | `manutencao.md` |
| Extraviado | Registrar recuperação | Disponível | `emprestimos.md` |
| Disponível / Reservado / Manutenção / Higienização | Transferir de unidade | o mesmo estado | `unidades.md` |
| Disponível / Manutenção / Reservado | Inativar | Inativo | `ativos.md` |
| Inativo | Reativar | Disponível | `ativos.md` |

Qualquer combinação fora desta tabela levanta erro — tanto na UI quanto em
qualquer chamada direta de serviço. Nenhuma tela pode oferecer uma ação que
não conste aqui.

## Quem pode alterar cada status?

Ver a matriz completa em `docs/business-rules/permissoes.md`. Regra geral:
Funcionário opera o dia a dia (emprestar, devolver, renovar, manutenção
simples); Gestor cadastra e desfaz situações excepcionais (baixa,
recuperação de extravio); Admin reativa ativos inativados e administra
unidades/usuários.

## Em quais situações uma operação deve ser bloqueada?

- O status atual do ativo não permite a ação (fora da tabela acima).
- O usuário não tem nível hierárquico suficiente para a ação.
- O usuário não pertence ao tenant do ativo (isolamento multi-tenant,
  reforçado por teste de arquitetura — nunca é possível operar um ativo
  de outra organização, mesmo por engano de URL).
- O ativo pertence a uma unidade que o usuário não opera
  (`docs/business-rules/unidades.md`). Nesse caso a resposta é 404, não 403:
  confirmar a existência já entregaria a informação que o escopo protege.
- Campos obrigatórios da ação (motivo de manutenção, destino de devolução,
  prazo de renovação) não foram informados.

## Quais eventos obrigatoriamente geram registros na timeline?

Toda transição de status listada na tabela acima gera uma `Movimentacao`
— sem exceção. Ver `docs/business-rules/timeline.md`.

## Quais notificações devem ser disparadas?

- Confirmação de empréstimo: imediata, ao emprestar.
- Aviso 7 dias antes do vencimento, no vencimento, e diariamente em
  atraso: job diário. Ver `docs/business-rules/notificacoes.md`.

## O que acontece quando um ativo muda de unidade?

A transferência gera uma `Movimentacao` do tipo "Transferência entre
Unidades", que **preserva o estado operacional** do ativo (um ativo em
manutenção transferido continua em manutenção) e registra origem e destino
por nome, além da referência. Não é permitida com o ativo emprestado, e
exige justificativa. Detalhe completo em `docs/business-rules/unidades.md`.

Consequência de negócio a ter em mente: depois da transferência, o ativo sai
da visão de quem o transferiu (se a unidade de destino não estiver atribuída
a ele). Isso é esperado, e é a razão de a justificativa ser obrigatória.

## Princípios que toda funcionalidade nova deve respeitar

1. Nenhuma tela decide sozinha o que é permitido — a permissão e a
   transição de estado são sempre recalculadas no servidor, nunca
   confiadas ao que a UI exibiu.
2. Nenhum registro de movimentação, auditoria ou notificação enviada é
   editável ou removível depois de criado — histórico é imutável.
3. Toda ação de negócio relevante identifica o usuário responsável — a
   pergunta "quem fez isso" sempre tem resposta.
4. Isolamento entre tenants é a regra padrão; acesso cross-tenant é
   exceção auditada e documentada, nunca um efeito colateral de um bug. O
   mesmo vale, dentro de um tenant, para o escopo de unidade: o filtro é
   aplicado por padrão e falha fechado (vê nada) quando não há atribuição,
   nunca aberto.
5. Falha em um sistema auxiliar (notificação, auditoria) nunca impede a
   operação principal de negócio — é sempre best-effort e isolada.

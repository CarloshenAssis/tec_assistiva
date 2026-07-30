# Notificações

## Objetivo

Avisar automaticamente o beneficiário sobre a confirmação, a proximidade e
o vencimento de um empréstimo, sem depender de ação manual do operador.

## Fluxo operacional

```text
Empréstimo confirmado

↓

Notificação de confirmação (imediata)

↓

Job diário verifica prazos

↓

7 dias antes do vencimento → aviso

No vencimento → aviso

Após o vencimento → aviso de atraso (repetido, uma vez por dia)
```

## Regras de negócio

- Quatro tipos de notificação: `confirmacao_emprestimo`, `aviso_7_dias`,
  `vencimento`, `atraso`.
- Cada tenant tem seu próprio template por tipo
  (`UniqueConstraint(tenant, tipo)`); se o tenant não cadastrar um
  template para um tipo, aquele tipo simplesmente não é disparado para
  ele — é a forma de "desativar" uma notificação, sem precisar de um
  campo de liga/desliga separado.
- Envio ocorre em **todos os canais disponíveis** do beneficiário:
  WhatsApp (se tiver telefone) e e-mail (se tiver e-mail) — não escolhe um
  só canal.
- O job diário (`enviar_notificacoes_diarias`) roda por tenant ativo,
  calcula os dias até o vencimento e dispara o tipo correspondente:
  `dias == 7` → aviso de 7 dias; `dias == 0` → vencimento; `dias < 0` →
  atraso.
- Nunca duplica o mesmo aviso no mesmo dia para o mesmo empréstimo
  (`ja_notificado_hoje`).

## Validações

- Falha ao enviar uma notificação nunca derruba a operação que a originou
  (ex.: confirmar um empréstimo nunca falha por causa de notificação) —
  isolado em try/except, com log da falha.

## Permissões por perfil

Notificações são automáticas — não há ação manual de usuário para
disparar. Consulta ao histórico de notificações enviadas segue a
permissão de relatórios (Gestor/Admin).

## Estados possíveis

`Pendente`, `Enviado`, `Falhou` (por tentativa de envio).

## Casos de exceção

- **O canal de envio ainda é um backend de log**, sem provedor real de
  WhatsApp Business API ou SMTP configurado — toda notificação "enviada"
  hoje só é registrada, não chega de fato ao beneficiário. O ponto de
  extensão (`_despachar`) já está isolado para plugar um provedor real
  sem alterar a lógica de regras.
- Beneficiário sem telefone nem e-mail não recebe nenhuma notificação — o
  sistema não bloqueia o empréstimo por isso, só não há canal de envio.

## Impactos em outros módulos

- Depende diretamente da `Movimentacao` de empréstimo e do
  `DetalheEmprestimo` (data prevista de devolução).
- Contagem de notificações enviadas aparece nos relatórios do Dashboard.

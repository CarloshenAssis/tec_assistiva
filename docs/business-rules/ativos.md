# Ativos

## Objetivo

Cadastrar um ativo individualmente identificável, que poderá ser emprestado,
transferido, enviado para manutenção ou baixado ao longo de todo o seu ciclo
de vida.

## Fluxo operacional

```text
Cadastrar

↓

Em estoque (Disponível)

↓

Emprestar / Reservar / Manutenção / Baixa
```

O cadastro é o único ponto de entrada de um ativo no sistema. Não existe
fluxo de "ativo sem dono": todo ativo nasce vinculado a um tenant e a uma
categoria antes de qualquer outra operação ser possível.

## Regras de negócio

- Todo ativo pertence a uma organização (`tenant`) — obrigatório, herdado de
  `TenantModel`. Isolamento garantido por teste de arquitetura
  (`core/tests/test_architecture.py`).
- Todo ativo possui QR Code, gerado automaticamente ao salvar
  (`qr_token = gerar_qr_token()`, `ativos/models.py`). Nunca é gerado
  manualmente. O token é único **globalmente**, não por tenant — decisão
  proposital: uma etiqueta impressa pode circular fisicamente fora do
  controle do sistema, então dois ativos de tenants diferentes nunca podem
  colidir no mesmo QR.
- Todo ativo possui código patrimonial único por tenant
  (`UniqueConstraint(tenant, patrimonio)`). Gerado automaticamente
  (`ativos/patrimonio.py`) no formato `PREFIXO-NNNNNN` quando o campo fica
  em branco, ou digitado manualmente (validado por unicidade,
  case-insensitive) — ver `docs/business-rules/qrcode.md` para o
  detalhamento da geração.
- Todo ativo possui categoria — obrigatória (`on_delete=PROTECT`: uma
  categoria em uso nunca pode ser excluída, só desativada).
- Todo ativo nasce com status `Disponível` (default do model).
- Todo ativo gera timeline automaticamente a partir da primeira movimentação
  registrada contra ele (ver `docs/business-rules/timeline.md`).
- Subcategoria, modelo, fabricante, número de série, fornecedor, data de
  aquisição, vida útil e observações são opcionais.

## Validações

- `patrimonio`: se preenchido manualmente, deve ser único no tenant
  (`AtivoForm.clean_patrimonio`) — erro de formulário, nunca
  `IntegrityError`/500.
- `categoria`: obrigatória, restrita às categorias do tenant corrente.
- Toda ação de mutação de estado (emprestar, devolver, dar baixa etc.)
  passa pela máquina de estados (`ativos/domain/state_machine.py`) antes de
  gravar qualquer coisa — nunca é possível colocar um ativo num status
  inconsistente, mesmo chamando o serviço diretamente (sem passar pela UI).

## Permissões por perfil

| Ação | Nível mínimo |
|---|---|
| Cadastrar ativo | Gestor |
| Editar ativo | Gestor |
| Consultar ativo / localizar por QR | Funcionário |
| Ações de movimentação (emprestar, devolver, manutenção etc.) | ver `docs/business-rules/emprestimos.md` e `manutencao.md` |

## Estados possíveis

`Disponível`, `Emprestado`, `Reservado`, `Em Manutenção`, `Em Higienização`,
`Extraviado`, `Inativo`, `Baixado` (terminal).

Detalhamento completo de transições em
`docs/business-rules/arquitetura-funcional.md`.

## Transições permitidas

Ver a tabela consolidada de transições em
`docs/business-rules/arquitetura-funcional.md#estados-e-transições-do-ativo`
— este documento não duplica a tabela para evitar duas fontes divergentes.

## Casos de exceção

- **Ativo sem unidade é permitido hoje.** O campo `Ativo.unidade` é opcional
  (`null=True, blank=True`) tanto no model quanto no formulário de cadastro.
  Isso diverge da regra desejada "nenhum ativo existe sem unidade, mesmo que
  exista apenas uma" (ver `docs/business-rules/unidades.md`, seção
  Pendências) — hoje o sistema não impede o cadastro sem unidade.
- QR Code apontando para um ativo de outro tenant (ou inexistente) sempre
  responde com a mesma página de "não encontrado" — nunca revela se o
  ativo existe em outra organização.

## Impactos em outros módulos

- Toda mudança de status gera uma `Movimentacao`, que alimenta a Timeline
  (`docs/business-rules/timeline.md`) e o Dashboard
  (`docs/business-rules/dashboard.md`).
- Criação/alteração/exclusão do registro `Ativo` é capturada automaticamente
  pela trilha de auditoria LGPD (`docs/business-rules/auditoria.md`).
- Empréstimos vencendo/vencidos disparam notificações
  (`docs/business-rules/notificacoes.md`).

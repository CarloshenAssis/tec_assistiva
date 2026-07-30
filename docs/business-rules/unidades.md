# Unidades

## Objetivo

Permitir que um cliente possua diversas unidades físicas sob um único
contrato, e controlar quem enxerga e opera os dados de cada unidade sem
travar o usuário a um único local fixo.

## Fluxo operacional

```text
Admin cadastra unidade

↓

Admin atribui unidades permitidas ao Gestor/Funcionário

↓

Gestor/Funcionário só enxerga/opera
as unidades atribuídas a ele
```

## Regras de negócio

- Hierarquia: Owner Ciclartech → Cliente → Administrador → Gestores →
  Funcionários.
- **Decisão de arquitetura**: em vez de vincular o Gestor/Funcionário
  diretamente a uma única unidade, a unidade é uma **permissão de acesso**:
  `Usuário → Perfil (Admin | Gestor | Funcionário) → Permissões → Unidades
  permitidas` (`Usuario.unidades`, M2M). Isso permite um gestor responsável
  por duas unidades, um funcionário cobrindo férias em outra unidade, e um
  administrador com acesso a todas.
- Admin sempre enxerga todas as unidades do tenant, independentemente do
  que estiver marcado no M2M — a regra "Admin vê tudo" é aplicada em
  código (`core/unidades.py::unidades_visiveis`), não depende de atribuição
  manual.
- Gestor/Funcionário só enxergam as unidades explicitamente atribuídas.
- Cadastro de unidade exige: nome (único por tenant), tipo, responsável,
  telefone, e-mail, endereço, cidade, UF, observações, status
  (ativa/inativa).

## Validações

- Nome da unidade único por tenant, validado no formulário (não apenas na
  constraint do banco, para nunca gerar erro 500).
- `usuario_pode_operar_unidade(usuario, unidade)`: uma unidade `None`
  (ativo sem unidade) sempre é permitida — não bloqueia a operação.

## Permissões por perfil

| Ação | Nível mínimo |
|---|---|
| Cadastrar/editar/ativar/desativar unidade | Admin |
| Atribuir unidades a um usuário | Admin (na criação do usuário) |
| Ver dados de uma unidade atribuída | Gestor/Funcionário (só as próprias) |
| Ver dados de todas as unidades | Admin |

## Estados possíveis

`Ativa`, `Inativa`.

## Transições permitidas

`Ativa ↔ Inativa`, alternável livremente pelo Admin (`unidades_alternar_ativo`).

## Casos de exceção

- Desativar uma unidade não desvincula automaticamente os ativos e
  usuários já associados a ela — eles continuam referenciando a unidade
  inativa até serem movidos manualmente.

## Pendências (divergências entre a regra desejada e o implementado hoje)

Registradas aqui para não se perderem — cada uma vira uma tarefa de
desenvolvimento futura:

- **"Nenhum ativo existe sem unidade" ainda não é aplicado.** Hoje
  `Ativo.unidade` é opcional no model e no formulário. A regra de negócio
  desejada é que todo ativo tenha obrigatoriamente uma unidade responsável,
  mesmo que o tenant só tenha uma unidade cadastrada.
- **`unidades_visiveis()` ainda não filtra as telas de listagem.** O motor
  de permissão existe e funciona (testado em
  `core/tests/test_unidades.py`), mas as views de listagem de ativos,
  beneficiários e o dashboard ainda consultam todos os dados do tenant,
  sem aplicar o filtro por unidade do usuário logado. Um Gestor com acesso
  restrito a uma unidade, hoje, ainda vê ativos de outras unidades nessas
  telas.
- **Transferência entre unidades não tem UI dedicada.** O campo
  `Movimentacao.unidade` existe e o tipo `transferencia` já é usado para
  recuperação de ativo extraviado, mas o fluxo "unidade origem → transferir
  → unidade destino → registrar movimentação → atualizar timeline"
  descrito na especificação ainda não tem tela própria.
- **Dashboard por unidade** (contagens de total/emprestados/manutenção/
  disponíveis agrupadas por unidade, para o Admin) ainda não existe — o
  dashboard atual é global por tenant.

## Impactos em outros módulos

- Define o escopo de visão de Ativos, Beneficiários e Relatórios para
  Gestor/Funcionário (quando as pendências acima forem resolvidas).
- Aparece no cadastro de usuário (checklist de unidades permitidas) e no
  cadastro de ativo (campo unidade responsável).

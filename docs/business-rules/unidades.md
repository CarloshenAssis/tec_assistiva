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

- **Nenhum ativo existe sem unidade**, mesmo que a organização tenha apenas
  uma. O campo é obrigatório no cadastro; se o tenant ainda não tem unidade
  nenhuma, a tela de cadastro de ativo orienta a criar a primeira em vez de
  oferecer um formulário impossível de salvar.
- Uma unidade com ativos não pode ser excluída — para tirá-la de operação,
  desative-a (`Status: Inativa`). Excluir deixaria ativos órfãos, exatamente
  o que a obrigatoriedade existe para impedir.
- Hierarquia: Owner Ciclartech → Cliente → Administrador → Gestores →
  Funcionários.
- **Gestor e Funcionário só enxergam dados das unidades atribuídas a eles** —
  em toda tela: lista de ativos, ficha, resolução de QR Code, busca por
  patrimônio, wizard de empréstimo, devolução, mapa operacional, lista de
  manutenção, agenda, dashboard, relatórios e Centro de Etiquetas. Um ativo
  de outra unidade responde "não encontrado" (404), nunca "acesso negado":
  confirmar a existência já entregaria a informação que o escopo protege.
- Gestor/Funcionário **sem nenhuma unidade atribuída não vê nada** — o
  comportamento correto (fail-closed), mas as telas dizem explicitamente que
  a causa é falta de atribuição, não falta de cadastro. Sem esse aviso, a
  tela vazia é indistinguível de "a organização não tem ativos".
- Um usuário não pode cadastrar ativo nem beneficiário numa unidade que não
  opera — deixaria de vê-lo no instante seguinte ao salvar.

### Transferência entre unidades

- Move a unidade responsável **sem alterar o estado operacional** do ativo:
  um ativo em manutenção transferido continua em manutenção.
- Permitida a partir de `Disponível`, `Reservado`, `Em Manutenção` e
  `Em Higienização` — estados em que o ativo está sob controle direto da
  organização.
- **Não** é permitida com o ativo `Emprestado`: ele está fisicamente com o
  beneficiário, e trocar a unidade responsável no meio do empréstimo
  tornaria ambíguo quem responde pela devolução. Também não se transfere
  ativo baixado, inativo ou extraviado — não há o que transferir.
- Transferir para a unidade em que o ativo já está é recusado (registraria
  uma movimentação sem mudança real, poluindo a timeline).
- **Justificativa é obrigatória.** O destino pode ser qualquer unidade ativa
  da organização, inclusive uma que o usuário não administra — remanejar
  para outra filial é operação legítima e frequente. O contrapeso é a
  justificativa: depois da transferência o ativo sai da visão de quem o
  transferiu, e o histórico precisa dizer por quê.
- A movimentação guarda **nome e id** da unidade de origem e de destino, não
  só a referência ao destino: assim, renomear ou remover a unidade de origem
  no futuro não apaga do histórico de onde o ativo saiu — que é exatamente a
  informação que a transferência existe para registrar.
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
| Transferir ativo entre unidades | Gestor |

## Estados possíveis

`Ativa`, `Inativa`.

## Transições permitidas

`Ativa ↔ Inativa`, alternável livremente pelo Admin (`unidades_alternar_ativo`).

## Casos de exceção

- Desativar uma unidade não desvincula automaticamente os ativos e
  usuários já associados a ela — eles continuam referenciando a unidade
  inativa até serem transferidos. Uma unidade desativada não aparece como
  opção em novos cadastros, mas continua na lista ao editar um ativo que
  já está nela (senão editar qualquer outro campo desse ativo ficaria
  impossível).
- **Beneficiário sem unidade é visível a toda a organização.** Diferente do
  ativo, a unidade do beneficiário é opcional: uma pessoa não "pertence" a
  uma unidade como um equipamento pertence a um depósito — pode ser atendida
  por mais de uma, ou ter sido cadastrada antes de a organização se
  organizar em unidades. Esconder esses cadastros de todos não protegeria
  dado nenhum, só faria o titular desaparecer do sistema.
- **Admin nunca é restrito por unidade**, mesmo que tenha unidades marcadas
  no cadastro dele. A regra "Admin vê tudo" é incondicional.

## Impactos em outros módulos

- Define o escopo de visão de Ativos, Beneficiários, Dashboard, Relatórios,
  Mapa Operacional e Centro de Etiquetas para Gestor/Funcionário.
- Aparece no cadastro de usuário (checklist de unidades permitidas) e no
  cadastro de ativo (unidade responsável, obrigatória).
- A transferência gera `Movimentacao`, portanto aparece na Timeline do ativo
  (`docs/business-rules/timeline.md`).

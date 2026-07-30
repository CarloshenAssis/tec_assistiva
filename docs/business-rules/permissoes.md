# Permissões

## Objetivo

Consolidar, num único lugar, o que cada perfil pode fazer — para que
qualquer funcionalidade nova seja avaliada contra esta tabela antes de ser
implementada, em vez de decidida caso a caso na view.

## Regras de negócio

- **Owner**: acesso irrestrito à plataforma. Vê todos os clientes,
  contratos, métricas e planos. Não pertence a nenhum tenant. Único
  papel autorizado a usar consultas cross-tenant (`all_tenants()`),
  reforçado por teste de arquitetura.
- **Admin**: acesso total dentro do próprio tenant. Cadastra/edita/desativa
  unidades, cadastra Gestores/Funcionários, define permissões (unidades
  atribuídas), visualiza todos os ativos/empréstimos/unidades da
  organização.
- **Gestor**: acesso operacional pleno dentro das unidades atribuídas a
  ele (hoje o filtro por unidade ainda não está aplicado nas listagens —
  ver `docs/business-rules/unidades.md`, Pendências). Pode cadastrar
  ativos, emprestar, devolver, enviar/finalizar manutenção, cadastrar
  beneficiários, emitir relatórios, dar baixa, registrar recuperação de
  ativo extraviado, editar dados de manutenção em curso, gerenciar
  usuários de nível igual ou inferior.
- **Funcionário**: acesso apenas às operações do dia a dia — localizar
  ativos, emprestar, devolver, renovar, registrar fotos, consultar
  ativos, finalizar higienização. Não altera configurações da
  organização, não cadastra/edita ativos, não gerencia usuários.

## Matriz de permissões por ação

| Ação | Funcionário | Gestor | Admin | Owner |
|---|---|---|---|---|
| Consultar ativo / QR / timeline | ✓ | ✓ | ✓ | ✓ (cross-tenant) |
| Emprestar / devolver / renovar | ✓ | ✓ | ✓ | — |
| Enviar / finalizar manutenção | ✓ | ✓ | ✓ | — |
| Editar manutenção em curso | — | ✓ | ✓ | — |
| Cadastrar / editar ativo | — | ✓ | ✓ | — |
| Dar baixa em ativo | — | ✓ | ✓ | — |
| Registrar recuperação (extravio) | — | ✓ | ✓ | — |
| Reativar ativo inativo | — | — | ✓ | — |
| Cadastrar/gerenciar usuários (nível inferior) | — | ✓ | ✓ | ✓ |
| Cadastrar/editar/desativar unidade | — | — | ✓ | — |
| Ver auditoria do tenant | — | ✓ | ✓ | ✓ (cross-tenant) |
| Ver dados de outros tenants | — | — | — | ✓ |

## Validações

- Toda ação de mutação de estado é revalidada no servidor
  (`executar_acao`), independente do que a UI mostra — um usuário não pode
  contornar a permissão manipulando a requisição.
- `owner_required` checa especificamente `is_platform_staff`, nunca
  `is_superuser` — as duas flags são independentes por decisão de projeto
  (superuser de Django Admin não implica acesso ao painel Owner).

## Casos de exceção

- Um Admin nunca é bloqueado por unidade — a regra "Admin vê tudo" é
  incondicional, independente de qualquer atribuição de unidade que
  porventura exista para ele.
- Falha de permissão em qualquer view sempre retorna `PermissionDenied`
  (403), nunca um redirecionamento silencioso que esconda o motivo.

## Impactos em outros módulos

Esta é a referência normativa usada por `ativos.md`, `emprestimos.md`,
`manutencao.md`, `unidades.md` e `usuarios.md` — qualquer alteração de
nível mínimo de uma ação deve ser refletida aqui primeiro.

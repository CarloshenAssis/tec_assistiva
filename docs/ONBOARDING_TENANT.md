# Onboarding de um Tenant Novo

Passo a passo para colocar uma instituição cliente nova (prefeitura,
fundo social, home care, locadora, hospital, ONG) em operação na
plataforma. Executado pela equipe Ciclartech (usuário Owner), não pelo
cliente.

## Pré-requisito

Um usuário Owner precisa existir e estar logado
(`docs/GUIA_OPERACOES.md` §1).

## 1. Criar o contrato (Tenant)

`/owner/tenants/novo/` (`owner/views.py::criar_tenant`).

Campos:

| Campo | Orientação |
|---|---|
| Nome | Nome da instituição, como deve aparecer na plataforma |
| Slug | Identificador único, gerado a partir do nome — confirmar que não colide com um tenant existente |
| Segmento | `fundo_social`/`home_care`/`locadora`/`hospital`/`ong` — define o vocabulário da tela (Beneficiário/Paciente/Cliente) e o padrão de módulos ativos (só a Locadora nasce com `locacao_financeiro` e `documento_pessoa_juridica` ligados) |
| Cidade / UF | |
| Ativo | Deixar marcado |

Escolher o segmento certo de início é importante: ele muda o rótulo em
toda a interface e o padrão de módulos. Trocar depois é possível (é só um
campo), mas revisar módulos manualmente se o padrão do novo segmento for
diferente do anterior.

## 2. Conferir/ajustar módulos

`/owner/tenants/<id>/` → seção de módulos. O padrão do segmento já vem
aplicado; ligar manualmente qualquer módulo que o cliente contratou fora
do padrão do segmento (ex.: uma prefeitura que também quer
`locacao_financeiro` para um programa específico). Ver
`docs/business-rules/modulos.md` para o que cada módulo muda na tela.

## 3. Criar o primeiro Administrador

`/owner/tenants/<id>/administrador/` (`criar_administrador`).

- Preencher usuário, e-mail, nome do primeiro Admin do tenant.
- O sistema gera uma **senha temporária aleatória**, mostrada **uma única
  vez** na tela de sucesso — depois disso só o hash existe, como qualquer
  senha. Copiar e repassar ao cliente **antes de sair dessa tela**; não há
  como recuperá-la depois (o fluxo correto nesse caso é gerar nova senha,
  não "recuperar" a antiga).
- Repassar a credencial por canal seguro (nunca e-mail em texto claro se
  evitável; preferir informar por telefone ou por um canal com
  criptografia ponta-a-ponta). Orientar o cliente a trocar a senha no
  primeiro acesso.

O Owner **nunca** cria usuário operacional (Gestor/Funcionário)
diretamente — só este primeiro Admin. É esse Admin quem cadastra o resto
da equipe de dentro do próprio tenant.

## 4. Handoff para o cliente — o que o Admin faz a partir daqui

Orientar o Admin do cliente (ou fazer com ele, na primeira sessão) a
completar o setup dentro do tenant:

1. **Cadastrar Unidades** (`/app/unidades/`) — pelo menos uma, mesmo que
   a instituição tenha só um endereço (regra de negócio: todo ativo
   precisa de unidade).
2. **Cadastrar Categorias/Subcategorias de Ativo** (`/app/categorias/`) —
   define também o prefixo do código patrimonial automático (ex.: `CAD`
   para Cadeira de Rodas → `CAD-000001`).
3. **Cadastrar usuários da equipe** (`/app/usuarios/`) — Gestor(es) e
   Funcionário(s), atribuindo as Unidades que cada um deve enxergar
   (Gestor/Funcionário só veem as unidades atribuídas a eles; o próprio
   Admin sempre vê todas, sem precisar de atribuição).
4. **Revisar/personalizar os templates de notificação**
   (via Django Admin — não há tela própria ainda; ver
   `docs/GUIA_DESENVOLVEDOR.md` para acesso) se o texto padrão precisar de
   ajuste.
5. **Cadastrar Fornecedores** (opcional, usado em aquisição/manutenção).
6. **Cadastrar os primeiros Ativos** — cadastro manual ou, se houver
   inventário legado em planilha, ver §5 abaixo.
7. **Imprimir etiquetas** (Centro de Etiquetas, `/app/etiquetas/`) para os
   ativos já cadastrados.

## 5. Importação de dados legados

**Não há importação em massa (CSV/planilha) implementada nesta fase.**
Cadastro de ativo e beneficiário é um-a-um pela tela. Para uma migração de
inventário grande, as opções atuais são:

- Cadastro manual pela equipe do cliente (viável para dezenas/poucas
  centenas de itens).
- Um script único de carga via Django shell/management command, escrito
  ad-hoc para o volume/formato específico do cliente (sempre dentro do
  contexto de tenant correto — usar
  `core.tenancy.set_current_tenant_id`, ver `core/management/commands/
  seed_demo.py` como referência de padrão). Não versionar dado real de
  cliente no repositório.

Se a importação em massa virar demanda recorrente, é candidata a virar
feature própria — registrar como item de roadmap, não resolver caso a
caso sem documentar.

## 6. Checklist de onboarding completo

- [ ] Tenant criado com segmento e cidade/UF corretos
- [ ] Módulos revisados (padrão do segmento + qualquer módulo extra
      contratado)
- [ ] Primeiro Admin criado e credencial repassada por canal seguro
- [ ] Admin trocou a senha temporária no primeiro acesso
- [ ] Pelo menos uma Unidade cadastrada
- [ ] Categorias de Ativo cadastradas com prefixo definido
- [ ] Equipe (Gestor/Funcionário) cadastrada com Unidades atribuídas
- [ ] Templates de notificação revisados
- [ ] Primeiro lote de ativos cadastrado e etiquetas impressas
- [ ] Cliente orientado sobre o fluxo básico (empréstimo, devolução, QR
      Code) — ver manual do papel correspondente (Admin/Gestor/
      Funcionário)

## 7. Suspender ou encerrar um contrato

Ver `docs/GUIA_OPERACOES.md` §4. Suspender não apaga dado nenhum — apenas
marca `Tenant.ativo=False`. Não há hoje um fluxo de exclusão/exportação
final de dados de um tenant inteiro ao encerrar contrato (diferente da
anonimização por titular, que já existe em `beneficiarios/lgpd.py`); se
isso for necessário, tratar como decisão de produto/jurídico antes de
executar qualquer exclusão em massa no banco.

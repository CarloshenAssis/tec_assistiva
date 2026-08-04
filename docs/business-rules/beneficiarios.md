# Beneficiários

## Objetivo

Cadastrar a pessoa/entidade para quem um ativo é destinado — beneficiário
social, paciente ou cliente locatário, conforme o segmento do tenant — e
garantir que o tratamento dos dados dela respeite a LGPD desde o cadastro
até a eventual eliminação.

`Beneficiario` é um único model para os três vocabulários (`tipo_relacao`
distingue "Beneficiário"/"Paciente"/"Cliente" só para rótulo de tela —
não há campo ou fluxo diferente por trás do nome, ver
docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §7).

## Fluxo operacional

```text
Cadastrar titular (nome, documento, contato, base legal)

↓

Anexar documentos (RG, comprovante, laudo, receita) pela ficha do titular

↓

Titular disponível para ser selecionado no wizard de empréstimo

↓

Ficha do titular acumula o histórico de empréstimos ao longo do tempo

↓

Titular pede acesso/eliminação → Admin exporta ou anonimiza
```

## Regras de negócio

- **Quem cadastra/edita**: qualquer usuário autenticado do tenant, a
  partir do nível **Funcionário** — tanto a tela de cadastro
  (`/app/beneficiarios/novo/`) quanto a de edição
  (`/app/beneficiarios/<id>/editar/`) não têm restrição de papel além de
  pertencer ao tenant e ver o titular no próprio escopo de unidade
  (`beneficiarios/views.py::criar`, `::editar`). É a mesma pessoa que faz
  o atendimento de balcão que cadastra e corrige o cadastro de quem está
  sendo atendido — corrigir um CPF digitado errado não exige mais Django
  Admin.
- **Quem anexa documento**: mesmo nível de `criar`/`editar` — Funcionário
  em diante, restrito ao escopo de unidade do titular
  (`beneficiarios/views.py::documento_novo`). Anexar cópia de RG/laudo é
  trabalho rotineiro de balcão, não uma ação sensível de gestão de LGPD
  (essa é a exportação/anonimização, que continuam Admin-only).
- **Escopo de unidade**: `Beneficiario.unidade` é **opcional**, ao
  contrário de `Ativo.unidade` (obrigatória). Um titular sem unidade
  definida fica **visível a toda a organização**, não só a quem atua numa
  unidade — decisão deliberada, porque uma pessoa não "pertence" a um
  depósito do jeito que um equipamento pertence; ela pode ser atendida
  por mais de uma unidade, ou ter sido cadastrada antes de o tenant
  organizar as próprias unidades (`core.unidades.filtrar_por_unidade(...,
  incluir_sem_unidade=True)`). Um titular **com** unidade definida só é
  visível a quem opera aquela unidade (mais Admin, que vê tudo).
- **Documento (CPF/CNPJ)**: único por tenant
  (`UniqueConstraint(tenant, documento)`). CNPJ só é oferecido como opção
  quando o tenant tem o módulo `documento_pessoa_juridica` habilitado
  (docs/business-rules/modulos.md, padrão ligado só para Locadora); sem o
  módulo, o formulário só oferece CPF.
- **Base legal obrigatória**: todo cadastro exige uma hipótese que
  autoriza o tratamento (`BaseLegal` — Consentimento, Obrigação legal,
  Política pública, Tutela da saúde, Execução de contrato). Sem escolher
  uma, o cadastro não salva. Se a base for "Consentimento", o momento do
  aceite é registrado automaticamente em `consentimento_em` no instante
  do cadastro.
- **Empréstimos simultâneos**: **não há limite** de quantos ativos um
  mesmo titular pode ter emprestados ao mesmo tempo. Cada empréstimo é
  um evento independente, amarrado ao ativo (que só pode estar
  emprestado uma vez por vez) — nada no model `Beneficiario` restringe
  quantos ativos diferentes ele pode estar com posse simultaneamente.

## Validações

- CPF/CNPJ validado por dígito verificador (`core.validadores`), não só
  por formato.
- Documento duplicado no mesmo tenant é recusado como erro de formulário
  (checado explicitamente no `clean()`, não deixado para o
  `IntegrityError` do banco).
- Upload de documento (RG, laudo, receita, comprovante) passa pela
  mesma validação tripla de qualquer upload do sistema — extensão,
  tamanho, magic number (`core.validadores.validar_upload`).

## Permissões por perfil

| Ação | Nível mínimo |
|---|---|
| Cadastrar titular | Funcionário |
| Editar cadastro do titular | Funcionário (restrito ao escopo de unidade) |
| Ver ficha / listar | Funcionário (restrito ao escopo de unidade) |
| Selecionar titular no wizard de empréstimo | Funcionário |
| Anexar documento (RG, comprovante, laudo, receita) | Funcionário (restrito ao escopo de unidade) |
| Baixar documento anexado | Funcionário (restrito ao escopo de unidade) |
| Exportar dados (Art. 18, II/V) | **Admin** |
| Anonimizar (Art. 18, VI) | **Admin** |
| Revogar consentimento | Camada de serviço (`beneficiarios.lgpd.revogar_consentimento`) — hoje sem tela própria, chamada programaticamente |

A edição (`beneficiarios/views.py::editar`, rota
`/app/beneficiarios/<id>/editar/`) e o upload de documento
(`::documento_novo`, rota `/app/beneficiarios/<id>/documentos/novo/`)
ficam indisponíveis assim que o titular é anonimizado — a ficha oculta
os dois pontos de entrada nesse estado (`esta_anonimizado=True`), porque
não há mais dado identificável para editar nem documento sensível a
anexar. Editar registra `AcaoAuditada.ALTERACAO` na trilha; anexar
documento registra `AcaoAuditada.CRIACAO`, marcando dado sensível quando
o tipo é laudo ou receita médica — mesmo critério do download.

## Estados possíveis

Do ponto de vista de dado pessoal, um titular está em um de três
estados, refletidos em campos do model, não numa máquina de estados
formal:

- **Ativo** — dado identificável, tratamento em curso.
- **Consentimento revogado** (`consentimento_revogado_em` preenchido) —
  só relevante quando a base legal é consentimento; o histórico
  operacional já constituído continua existindo.
- **Anonimizado** (`anonimizado_em` preenchido, `esta_anonimizado=True`)
  — dado identificável removido; estado terminal, a função `anonimizar`
  é idempotente (chamar de novo não faz nada).

## Transições permitidas

`Ativo → Consentimento revogado` e `Ativo → Anonimizado` são as únicas
transições — ambas de mão única, não existe "reidentificar" um titular
anonimizado nem "restaurar" um consentimento revogado (a pessoa
consentiria de novo, gerando um novo `consentimento_em`).

## Casos de exceção

- **O que acontece com o histórico de empréstimos se um titular for
  anonimizado**: o histórico **é preservado**, só deixa de identificar a
  pessoa. `DetalheEmprestimo.beneficiario` é `on_delete=PROTECT` — um
  titular com qualquer empréstimo no histórico **nunca pode ser
  excluído** do banco, só anonimizado. Isso é proposital: o registro de
  qual equipamento foi emprestado e devolvido responde a uma finalidade
  de prestação de contas patrimonial (Art. 16, I autoriza a conservação),
  distinta da identificação da pessoa — o que a LGPD protege é a
  identificabilidade, e ela é removida sem destruir a trilha.
- **O que a anonimização apaga, especificamente**: nome (substituído por
  `[anonimizado] #<id>`), documento (substituído por um valor derivado do
  id, nunca reaproveitável), data de nascimento, RG, telefone, WhatsApp,
  e-mail, endereço, bairro, cidade, CEP, contato de emergência. Os
  documentos anexados (`DocumentoBeneficiario`) são **apagados
  fisicamente do storage**, não só desvinculados — são dado sensível sem
  função patrimonial, diferente da movimentação do equipamento.
- **Retenção**: não há expurgo automático agendado para dado de
  beneficiário (diferente da auditoria, que expira em 24 meses por
  comando dedicado — docs/business-rules/auditoria.md). A eliminação só
  acontece por ação deliberada do Admin (anonimizar), a pedido do
  titular ou por política interna do tenant — não é uma rotina do
  sistema.
- **Limite de taxa**: exportação e anonimização têm limite de tentativas
  por conta (20 exportações/hora, 5 anonimizações/hora) — bem mais
  apertado que o de movimentação de ativo, porque são operações raras
  pedidas pelo titular, não tarefa de balcão. Ultrapassar o limite grava
  um evento de auditoria e bloqueia a ação temporariamente.
- **Toda leitura de dado pessoal é auditada**: abrir a ficha de um
  titular e baixar um documento anexado geram registro de auditoria
  automaticamente (`registrar_acesso_dado_pessoal`), marcando
  separadamente quando o documento é dado sensível (laudo, receita) —
  não é preciso lembrar de fazer isso manualmente.

## Impactos em outros módulos

- É selecionado no Passo 1 do wizard de empréstimo
  (docs/business-rules/emprestimos.md).
- Aparece no Mapa Operacional por bairro, só para ativos emprestados
  (docs/features — Módulo Mapa Operacional de Ativos).
- Recebe as notificações automáticas de vencimento/atraso
  (docs/business-rules/notificacoes.md) via telefone/WhatsApp cadastrado.
- Toda ação sobre o titular (criação, exportação, anonimização,
  revogação de consentimento, acesso à ficha/documento) é capturada na
  trilha de auditoria (docs/business-rules/auditoria.md).
- O rótulo de tela ("Beneficiário"/"Paciente"/"Cliente") vem do segmento
  do `Tenant` (docs/business-rules/modulos.md).

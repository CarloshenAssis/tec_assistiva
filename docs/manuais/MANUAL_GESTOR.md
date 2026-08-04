# Manual do Gestor

Este manual cobre tudo que um **Gestor** faz no Ciclartech. Um Gestor tem
as mesmas ferramentas do dia a dia que um Funcionário, **mais** um
conjunto de ações administrativas dentro das unidades que estiverem
atribuídas a ele. Se você é novo na operação (empréstimo, devolução,
cadastro básico), leia primeiro o **Manual do Funcionário** — aqui vamos
focar no que é exclusivo do Gestor.

## 1. Seu escopo

Um Gestor só vê e opera o que está dentro das **unidades atribuídas a
ele** (postos, filiais, depósitos) — igual ao Funcionário. A diferença é
o que ele pode **fazer** dentro desse escopo, não o que ele **vê**.

Se você precisa gerenciar mais de uma unidade, peça ao Admin para
atribuir todas a você em **Administração → Usuários → editar seu
cadastro**.

## 2. O que você faz além do Funcionário

### 2.1. Editar um Ativo já cadastrado

Na ficha do ativo, ação **Editar**. Dá para corrigir qualquer campo do
cadastro (categoria, modelo, fabricante, fornecedor, etc.) — diferente do
Funcionário, que só cadastra um ativo novo, não corrige um existente.

### 2.2. Transferir um Ativo entre Unidades

Na ficha do ativo (estados Disponível, Reservado, Manutenção ou
Higienização — nunca com o ativo emprestado, porque nesse caso ele está
fisicamente com o beneficiário), ação **Transferir de Unidade**.

O sistema guarda no histórico de onde o ativo saiu e para onde foi —
mesmo que a unidade de origem seja renomeada depois, esse registro não se
perde.

### 2.3. Registrar Extravio e Recuperação

- **Registrar Extravio**: quando um ativo não é encontrado (inventário,
  perda). Pode ser feito com o ativo Disponível ou Emprestado.
- **Registrar Recuperação**: quando um ativo extraviado é encontrado de
  novo — exige uma justificativa das circunstâncias.

### 2.4. Dar Baixa Patrimonial

Ação disponível para ativo Disponível ou em Manutenção. É definitivo —
**estado terminal**, sem volta. Use quando o equipamento realmente saiu
do patrimônio (quebrou de vez, foi doado, etc.). Informe o motivo.

### 2.5. Reativar um Ativo Inativo

Se um Admin inativou um ativo administrativamente, só o Admin consegue
reativá-lo — não é uma ação de Gestor.

## 3. Gerenciar Usuários (Funcionários)

Menu **Administração → Usuários**.

Como Gestor, você pode:
- **Criar** um novo usuário — mas só com papel **Funcionário** (não dá
  para criar outro Gestor nem Admin; essas contas nascem de quem está
  hierarquicamente acima).
- **Editar** o cadastro (e-mail, nome, unidades atribuídas) de
  Funcionários e de outros Gestores do mesmo nível — mas nunca pode
  promover alguém para o seu próprio nível ou acima.
- **Desativar/reativar** o acesso de um usuário.
- **Gerar nova senha** temporária, se a pessoa esqueceu a dela.

Você **não pode** editar o próprio cadastro por essa tela — para isso,
peça a outro Gestor ou ao Admin.

Ao criar um Funcionário, é obrigatório marcar **ao menos uma unidade** —
sem isso, a pessoa loga mas não vê ativo/beneficiário nenhum, o que gera
confusão desnecessária.

## 4. Auditoria

Menu **Administração → Auditoria** — mostra a trilha de eventos do seu
tenant: quem logou, quem criou/editou o quê, exportação de dados,
anonimização de titular. Dá para filtrar por ação, por usuário, e por
"só eventos com dado sensível". Também dá para exportar em CSV.

Esse histórico **não pode ser editado nem apagado por ninguém** — nem por
você, nem pelo Admin, nem pela equipe técnica. É a garantia de que, se
algo der errado, existe um registro confiável de quem fez o quê.

## 5. Módulos que você usa, igual ao Funcionário

Todos cobertos em detalhe no **Manual do Funcionário**:

- Painel (dashboard com indicadores e cores)
- Emprestar (wizard de 4 passos)
- Devolver (com checklist e destino)
- Manutenção (enviar, finalizar, editar)
- Localizar Ativo / QR Code
- Cadastros → Ativos, Beneficiários, Centro de Etiquetas
- Agenda (devoluções/atrasos, Mapa Operacional)
- Relatórios (indicadores, notificações)

## 6. O que só o Admin faz (fora do seu alcance)

- Cadastrar/editar **Categorias e Subcategorias** de ativo.
- Cadastrar/editar **Unidades**.
- Configurar o **Encarregado (LGPD)** e o **logotipo da instituição**.
- Criar ou editar outro **Admin**.
- Anonimizar dados de um beneficiário (direito de eliminação da LGPD).
- Reativar um ativo inativado administrativamente.

Se precisar de qualquer uma dessas ações, acione o Admin do seu tenant.

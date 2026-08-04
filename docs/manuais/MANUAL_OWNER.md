# Manual do Owner (Equipe Ciclartech)

O **Owner** é a equipe da Ciclartech — não pertence a nenhuma instituição
cliente (tenant), gerencia a **plataforma inteira**. A área do Owner
(`/owner/`) é completamente separada da área que os clientes usam
(`/app/`): visual diferente, menu diferente, e um Owner nunca vê a
operação do dia a dia (empréstimo, devolução) de um tenant específico —
só provisiona, configura e audita.

## 1. Acesso

Não existe tela de cadastro para criar um Owner — é deliberado, porque é
a chave mestra da plataforma. A primeira conta é criada via linha de
comando por alguém da equipe técnica. A partir daí, um Owner já criado
pode logar normalmente pela tela de login — o sistema reconhece o papel
automaticamente e te leva para `/owner/`, não para a área de cliente.

## 2. Contratos (tela inicial)

Menu **Contratos** — lista todas as instituições clientes (tenants) da
plataforma, com busca e paginação.

### 2.1. Provisionar um cliente novo

**Contratos → Novo contrato**:

1. Preencha **nome**, **slug** (identificador único, gerado
   automaticamente a partir do nome, editável), **segmento** (Fundo
   Social/Prefeitura, Home Care, Locadora, Hospital, ONG), cidade e UF.
2. O **segmento** já define o vocabulário das telas do cliente (ex.:
   "Beneficiário" para Fundo Social, "Paciente" para Home Care, "Cliente"
   para Locadora) e quais módulos vêm ligados por padrão (ex.: Locadora
   já nasce com Locação Financeira habilitada).
3. Salve. Você cai na tela de **detalhe do contrato**.

4. Em seguida, **Gerar acesso de administrador** — cria o primeiro
   usuário Admin daquele tenant. Preencha usuário, e-mail, nome. A senha
   é **gerada automaticamente** e aparece **uma única vez** na tela de
   sucesso — anote e repasse ao cliente por um canal seguro (nunca por
   e-mail em texto claro, se puder evitar). Não existe como recuperar
   essa senha depois; se perder, gere uma nova pela tela de usuários do
   próprio tenant (que o Admin dele também consegue fazer sozinho depois).

A partir daí, o cliente entra com o Admin criado e assume a operação —
cadastra unidades, categorias, usuários, ativos, tudo pela área dele.

### 2.2. Detalhe de um contrato

Ao abrir um tenant específico, você vê:

- **Dados gerais**: nome, segmento, cidade/UF, status (ativo/suspenso),
  data de criação.
- **Editar contrato**: muda nome, slug, segmento, cidade/UF, status, e
  também os dados do **Encarregado (DPO)** — normalmente quem preenche
  isso é o próprio Admin do tenant (`/app/encarregado/`), mas você pode
  ajustar por aqui como canal de suporte, se precisar.
- **Suspender/Reativar contrato**: marca `ativo=False`/`True`. Hoje isso
  afeta o job diário de notificações (tenant suspenso não recebe
  notificações automáticas), mas **não bloqueia login** dos usuários
  dele automaticamente — se usar isso como controle de inadimplência,
  trate como algo a reforçar, não como bloqueio garantido.
- **Módulos**: lista o catálogo inteiro com toggle Ligar/Desligar por
  contrato — sobrepõe o padrão do segmento só para aquele cliente.
- **Encarregado (DPO)**: mostra se já foi configurado; aviso visível se
  ainda não foi.
- **Usuários do contrato**: lista quem tem acesso, papel, status, com
  atalho para a auditoria filtrada por aquela pessoa.

## 3. Auditoria geral

Menu **Auditoria geral** — trilha de eventos de **todos os tenants**,
numa visão só. Filtre por tenant, ação, usuário, ou "só dado sensível".
Dá para exportar em CSV.

Esse é o único lugar da plataforma onde alguém enxerga eventos de mais de
um tenant ao mesmo tempo — é uma exceção deliberada e monitorada; nenhuma
outra tela do sistema faz isso.

## 4. O que o Owner NÃO faz

- Não opera o dia a dia de nenhum tenant: não empresta, não devolve, não
  cadastra ativo/beneficiário de cliente nenhum. Essa é a área
  `/app/`, exclusiva de quem pertence ao tenant.
- Não gera cobrança nem processa pagamento — o sistema hoje não integra
  com nenhum meio de pagamento; controle de contrato/faturamento é feito
  fora da plataforma.
- Não vê a ficha detalhada de um beneficiário de um cliente — a
  auditoria mostra que uma ação aconteceu, não o conteúdo do dado pessoal
  em si.

## 5. Boas práticas de provisionamento

- **Sempre confira o segmento certo** antes de criar o contrato — muda
  vocabulário e módulos padrão, e trocar depois não é automático (dá
  para editar, mas vale acertar de primeira).
- **Repasse a senha temporária do primeiro Admin por canal seguro** —
  ela só aparece uma vez.
- **Confirme com o cliente que o Encarregado (LGPD) foi preenchido**
  logo após o onboarding — é responsabilidade do tenant, mas vale
  cobrar, porque afeta a conformidade dele com a LGPD, não a sua.
- Para o passo a passo completo de onboarding com todos os detalhes
  técnicos, consulte `docs/ONBOARDING_TENANT.md`.

# Manual do Funcionário

Guia de uso do dia a dia do sistema Ciclartech para quem opera o balcão:
empresta, devolve, cadastra ativo/beneficiário e cuida da rotina de
equipamentos. Não cobre telas de administração (usuários, unidades) — só o
Admin e o Gestor têm acesso a elas.

## 1. Primeiro acesso

Você recebe um usuário e uma **senha temporária** de quem te cadastrou
(Admin ou Gestor). Essa senha só aparece uma vez na tela dele — se perder,
peça para gerarem outra, não tem como recuperar a antiga.

No primeiro login, é recomendável trocar a senha em **seu nome (canto
inferior esquerdo) → Alterar senha**.

Se errar a senha várias vezes seguidas, o sistema bloqueia
temporariamente o acesso por alguns minutos — é proteção contra tentativa
de invasão, não um erro do sistema. Espere e tente de novo.

## 2. A tela principal (Painel)

Ao entrar, você cai no **Painel** — um resumo do que está acontecendo:

- Quantos ativos estão **disponíveis**, **emprestados**, **em manutenção**.
- **Taxa de utilização**: quantos dos ativos emprestáveis estão em uso.
- **Últimas movimentações**: as ações mais recentes no sistema.
- **Resumo colorido**: a mesma cor que aparece em toda a plataforma para
  indicar a situação de um ativo, sem precisar ler texto:

| Cor | Situação |
|---|---|
| 🔵 Azul | Disponível |
| 🟢 Verde | Emprestado, dentro do prazo |
| 🟢 Verde claro | Emprestado, vence em até 7 dias |
| 🟡 Amarelo | Em manutenção |
| 🔴 Vermelho (claro/médio/escuro) | Atrasado — quanto mais escuro, mais atrasado |
| ⚫ Cinza | Fora de operação (baixado, extraviado, reservado, em higienização) |

Você só vê os ativos das **unidades que estão atribuídas a você**. Se a
tela parecer vazia e você acha que deveria ter ativo, confirme com seu
Gestor/Admin se você está associado à unidade certa.

## 3. Cadastros

### 3.1. Cadastrar um Ativo

Menu **Cadastros → Ativos → Novo Ativo**.

Campos principais:
- **Categoria** (obrigatório): ex. Cadeira de Rodas, Muletas.
- **Subcategoria** (opcional).
- **Modelo, Fabricante, Nº de série** (opcionais, mas ajudam a identificar).
- **Unidade** (obrigatório): o ativo sempre precisa pertencer a uma
  unidade — não existe ativo "solto".
- **Fornecedor** (opcional): quem vendeu/forneceu o equipamento. Se não
  estiver na lista, dá para cadastrar um novo ali mesmo, sem sair da tela.
- **Data de aquisição, Vida útil (meses), Observações** (opcionais).
- **Código patrimonial**: se você deixar em branco, o sistema **gera
  automaticamente** um código a partir da categoria (ex.: `CAD-000001`
  para Cadeira de Rodas). Só preencha na mão se o equipamento já tiver um
  número de patrimônio próprio da sua instituição.
- **Fotos**: dá para enviar até 4 fotos (principal, lateral, traseira,
  etiqueta) já no cadastro.

Assim que salvo, o ativo já entra automaticamente na **fila de impressão
de etiqueta** — não precisa fazer nada a mais para isso acontecer.

### 3.2. Cadastrar um Beneficiário

Menu **Cadastros → Beneficiários** (o nome no menu muda conforme o
segmento da sua instituição: "Beneficiários", "Pacientes" ou "Clientes").

Campos principais:
- **Nome, CPF (ou CNPJ, se habilitado), RG, data de nascimento**.
- **Telefone, WhatsApp, e-mail**.
- **Endereço, cidade, bairro, CEP** — o bairro é usado no Mapa Operacional
  para mostrar onde os empréstimos estão concentrados.
- **Contato de emergência** (nome, telefone, parentesco).
- **Unidade**: normalmente deixe em branco ("Toda a organização") a
  não ser que essa pessoa deva ser vista só por quem atua numa unidade
  específica.
- **Base legal** (obrigatório): a justificativa que autoriza guardar os
  dados dessa pessoa (ex.: "Consentimento do titular"). É exigência da
  LGPD — sem escolher uma opção, o cadastro não salva. Se for
  "Consentimento", confirme verbalmente com a pessoa antes de marcar.

**Atenção com dados sensíveis**: se for anexar laudo médico ou receita,
esses documentos são tratados como dado sensível — só Admin consegue
exportar ou anonimizar os dados do titular depois, mas qualquer um com
acesso ao cadastro pode ver.

**Corrigir um dado depois de salvo**: na ficha do titular
(**Cadastros → Beneficiários → abrir o titular**), use **Editar
cadastro** para corrigir um campo (CPF digitado errado, telefone, etc.) —
não precisa de Django Admin nem de Gestor para isso. Some da ficha se o
titular já tiver sido anonimizado (não há mais o que editar nesse caso).

**Anexar documento (RG, comprovante, laudo, receita)**: se a sua
instituição tiver esse recurso habilitado, a ficha do titular mostra uma
seção **Documentos** para anexar e baixar os arquivos direto por ali. É
um recurso opcional, ligado por instituição (não por você) — se não
aparecer na ficha, sua instituição optou por não usar; fale com o Admin
se precisar dele.

## 4. Fluxo de Empréstimo

Menu **Operações → Emprestar**. É um assistente de 4 passos — o sistema
guarda o que você já preencheu, então se precisar voltar uma etapa, os
dados não se perdem.

**Passo 1 — Escolher o Beneficiário**
Busque por nome ou CPF. Se a pessoa não existir ainda, cadastre-a primeiro
(seção 3.2) e depois volte aqui.

**Passo 2 — Escolher o Ativo**
Só aparecem ativos **Disponíveis** dentro do seu escopo. Busque por
patrimônio ou categoria.

**Passo 3 — Definir o prazo**
Quantos dias o empréstimo vai durar. Se sua instituição usa o módulo de
**Locação Financeira** (comum em locadoras), aparecem também os campos de
valor da diária, caução e multa por atraso.

**Passo 4 — Checklist, assinatura e confirmação**
Marque o checklist de condição do equipamento (rodas, freios, apoio de
braço, apoio de pé, ferrugem, higienização) e confirme se o termo foi
impresso e assinado fisicamente pelo beneficiário. Anexe a foto do termo
assinado (ou uma foto do equipamento, se preferir) e confirme.

Ao confirmar, o ativo muda automaticamente para **Emprestado**, e o
beneficiário recebe uma notificação de confirmação (WhatsApp/e-mail,
quando configurado).

### Renovar um empréstimo

Na ficha do ativo emprestado, ação **Renovar Empréstimo** — informe o
novo prazo. Não precisa devolver e emprestar de novo.

## 5. Fluxo de Devolução

Menu **Operações → Devolver**.

1. Busque o ativo por patrimônio, QR Code ou pelo nome/CPF do
   beneficiário que está com ele.
2. Marque o checklist de condição na devolução (estado igual à retirada,
   limpa, funcionando).
3. Escolha o **destino**:
   - **Disponível** — volta direto para o acervo, pronto para novo
     empréstimo.
   - **Higienização** — precisa passar por limpeza antes de voltar a
     circular.
   - **Manutenção** — tem algum problema, vai para conserto.
4. Anexe uma foto de comparação (opcional, mas recomendado — ajuda a
   provar o estado de devolução se houver dúvida depois).

Se a devolução estiver atrasada e sua instituição usa o módulo
financeiro, o sistema já calcula uma **multa estimada** — é só
informativo, você (ou seu Gestor) decide o valor final cobrado.

## 6. Manutenção

Menu **Operações → Manutenção** lista os ativos que estão nesse status
agora.

- **Enviar para Manutenção**: disponível na ficha de um ativo
  Disponível — informe o motivo e, se souber, o fornecedor/oficina e o
  valor estimado.
- **Finalizar Manutenção**: volta o ativo para Disponível.
- **Editar dados da manutenção**: se errou o motivo ou o valor
  enquanto o equipamento ainda está no conserto, dá para corrigir sem
  precisar cancelar e recomeçar.

## 7. Localizar um Ativo / QR Code

Menu **Operações → Localizar Ativo** — busca por texto, categoria, ou
escaneando o QR Code impresso na etiqueta do equipamento.

Ao escanear ou localizar, abre um **painel rápido** com as ações
disponíveis para aquele ativo, já filtradas pelo estado dele e pelo que
você tem permissão de fazer — você nunca vê uma ação que não pode
executar.

## 8. Outras telas que você acessa

- **Agenda → Devoluções e atrasos**: separa em "hoje", "próximos 7 dias"
  e "atrasados" — útil para priorizar cobranças de devolução.
- **Agenda → Mapa Operacional**: mostra os ativos agrupados por unidade e
  por bairro do beneficiário (só para os emprestados) — não é
  geolocalização em tempo real, é o endereço já cadastrado.
- **Cadastros → Centro de Etiquetas**: filtra o acervo, seleciona os
  ativos e gera a folha de etiquetas para imprimir — várias etiquetas
  numa folha só, alinhadas do canto superior esquerdo. Uma única
  etiqueta também sai numa folha padrão, não precisa de papel especial.
- **Relatórios → Relatórios / Notificações**: números gerais do acervo e
  histórico do que já foi enviado a beneficiários.

## 9. Coisas que você NÃO consegue fazer (e é normal)

- Editar um ativo já cadastrado (precisa de Gestor).
- Transferir um ativo entre unidades (precisa de Gestor).
- Dar baixa ou registrar extravio (precisa de Gestor).
- Criar ou editar outro usuário (precisa de Gestor).
- Ver a tela de Unidades, Encarregado (LGPD) ou Instituição (só Admin).

Se uma tela pedir permissão que você não tem, isso é o sistema
funcionando corretamente — fale com seu Gestor/Admin se acha que deveria
ter acesso.

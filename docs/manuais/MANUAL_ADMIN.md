# Manual do Administrador

Este manual cobre tudo que um **Admin** faz no Ciclartech. O Admin é o
nível mais alto dentro do seu tenant (instituição) — enxerga **todas as
unidades**, sempre, e é o único papel que mexe em configurações que
afetam a organização inteira. Se você ainda não conhece o dia a dia do
sistema (empréstimo, devolução, cadastro), leia primeiro o **Manual do
Funcionário** e o **Manual do Gestor** — aqui tratamos só do que é
exclusivo do Admin.

## 1. Seu escopo

Diferente de Gestor e Funcionário, o Admin **não depende de atribuição de
unidade** — vê e opera tudo do tenant, sempre, mesmo sem nenhuma unidade
marcada no seu próprio cadastro.

## 2. Tudo que Gestor e Funcionário fazem, você também faz

- Painel, Emprestar, Devolver, Manutenção, Localizar Ativo/QR Code
  (Manual do Funcionário).
- Editar Ativo, Transferir entre Unidades, Registrar Extravio/
  Recuperação, Dar Baixa, Gerenciar Usuários, ver Auditoria
  (Manual do Gestor).

O que segue é o que **só o Admin** faz.

## 3. Categorias e Subcategorias de Ativo

Menu **Cadastros → Categorias**.

- Cria as categorias do acervo (ex.: "Cadeira de Rodas", "Muletas",
  "Camas Hospitalares") e, dentro de cada uma, subcategorias mais
  específicas (ex.: "Cadeira de Rodas" → "Motorizada", "Manual").
- Cada categoria tem um **prefixo** de código patrimonial (ex.: `CAD`) —
  usado para gerar automaticamente o número do ativo (`CAD-000001`) na
  hora do cadastro. Se deixar em branco, o sistema deriva as 3 primeiras
  letras do nome da categoria.

Gestor e Funcionário só **usam** a categoria já cadastrada (no formulário
de Ativo); só o Admin cria/edita o catálogo em si.

## 4. Unidades

Menu **Administração → Unidades**.

Cadastre cada unidade física da sua instituição — posto, filial, CRAS,
depósito. Cada uma tem nome, tipo (texto livre — "Matriz", "Filial",
etc.), responsável, telefone, e-mail, endereço.

**Desativar** uma unidade (em vez de excluir) é a forma correta de tirá-la
de operação — o sistema não permite apagar uma unidade que já tem ativo
vinculado, então desativar é o caminho.

Depois de cadastrar uma unidade, atribua Gestores/Funcionários a ela em
**Administração → Usuários → editar o cadastro da pessoa**.

## 5. Reativar um Ativo Inativo

Se um ativo foi inativado administrativamente (ação separada do fluxo
operacional normal — não é a mesma coisa que "dar baixa"), só o Admin
consegue trazê-lo de volta para Disponível.

## 6. Direitos do titular (LGPD) sobre um Beneficiário

Na ficha do beneficiário, exclusivo do Admin:

- **Exportar dados**: gera um arquivo com tudo que o sistema tem sobre
  aquela pessoa — atende ao direito de acesso/portabilidade (LGPD Art.
  18). Essa ação fica registrada na auditoria.
- **Anonimizar**: remove nome, CPF, contato e demais dados
  identificáveis, e apaga fisicamente documentos anexados (laudo, RG) do
  armazenamento. **Não apaga o histórico de empréstimos** — o registro de
  qual equipamento foi emprestado e devolvido continua existindo, mas sem
  identificar mais ninguém. Use quando o titular pedir para ter os dados
  eliminados. É uma ação que exige confirmação (POST) e não tem volta.
- **Revogar consentimento**: registra que o titular retirou o
  consentimento — não apaga o histórico já constituído, só marca que o
  tratamento baseado nele parou.

## 7. Encarregado (LGPD/DPO)

Menu **Administração → Encarregado (LGPD)**.

Cadastre o nome, e-mail e telefone da pessoa responsável por atender
solicitações dos titulares de dados (beneficiários) da sua instituição —
exigência da LGPD (Art. 41). Não precisa ser um profissional dedicado,
pode ser alguém que já acumula essa função (jurídico, RH, TI), mas
precisa ser uma pessoa identificável, com contato ativo.

Sua instituição é **controladora** dos dados dos seus próprios
beneficiários — a Ciclartech é só a operadora da plataforma. É por isso
que cada tenant configura o próprio Encarregado, em vez de ter um único
contato central.

## 8. Logotipo da Instituição

Menu **Administração → Instituição (logo)**.

Envie o logotipo da sua instituição — ele aparece automaticamente nas
etiquetas patrimoniais impressas, ao lado do nome. Recomendado: imagem
quadrada, fundo branco ou transparente (a etiqueta é impressa em preto e
branco). Formatos aceitos: JPG, PNG ou WebP, até 10 MB.

## 9. Gerenciar Usuários — o que muda para você

Você pode criar/editar/desativar usuários de **qualquer papel abaixo do
seu** (Gestor e Funcionário) — o Gestor só consegue criar Funcionário.
Contas de **outro Admin** não são criadas por aqui: quem cria o primeiro
Admin de um contrato é a equipe Ciclartech (Owner), no momento da
contratação.

## 10. Módulos por contrato

Alguns recursos do sistema (ex.: **Locação Financeira** — valor de
diária, caução, multa por atraso; **Documento Pessoa Jurídica** — permite
cadastrar beneficiário com CNPJ) são **módulos opcionais**, ligados ou
desligados por contrato. Você não liga/desliga isso sozinho — quem
controla é a equipe Ciclartech (Owner), pela área deles. Se sua
instituição precisa de um módulo que não está ativo, entre em contato com
a Ciclartech.

## 11. Suporte a usuário final

- **Esqueceu a senha**: se o e-mail de recuperação não estiver
  configurado no sistema, o link de redefinição não chega ao usuário. A
  alternativa é você (ou um Gestor) gerar uma **nova senha temporária**
  pela tela de usuários — não depende de e-mail.
- **Usuário bloqueado por tentativas erradas**: é proteção automática
  contra ataque, expira sozinha em minutos. Não existe um botão para
  desbloquear na hora — se for engano de digitação, é só esperar.

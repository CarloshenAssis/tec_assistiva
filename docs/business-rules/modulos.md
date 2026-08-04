# Módulos e Diferenciação por Segmento

## Objetivo

Permitir que funcionalidades específicas de um segmento (ex.: dados
financeiros de locação, cliente pessoa jurídica) sejam ligadas apenas para
quem precisa delas, sem transformar isso em código condicional espalhado
pelo produto nem em uma tela diferente por segmento.

## Fluxo operacional

```text
Tenant nasce com um segmento (Fundo Social, Home Care, Locadora, Hospital, ONG)

↓

Cada módulo do catálogo tem um padrão de ativação por segmento

↓

Owner pode ligar/desligar um módulo específico para um tenant,
sobrepondo o padrão do segmento

↓

O restante do sistema consulta "este tenant tem este módulo?"
— nunca "qual é o segmento deste tenant?"
```

## Regras de negócio

- O catálogo de módulos é fixo, populado por migration de dados (mesmo
  padrão de `contas.Papel`) — criar um módulo novo é decisão de produto,
  não uma tela de cadastro.
- Cada módulo tem um **padrão de ativação por segmento**
  (`core.features._MODULOS_PADRAO_POR_SEGMENTO`). Hoje:
  - `locacao_financeiro` (valor diário, caução, multa por atraso no
    empréstimo) — ligado por padrão para **Locadora**.
  - `documento_pessoa_juridica` (CNPJ como tipo de documento do titular,
    além de CPF) — ligado por padrão para **Locadora**.
  - `documentos_beneficiario` (upload de RG/comprovante/laudo/receita na
    ficha do titular) — **desligado por padrão para todo segmento**, sem
    exceção. Diferente dos dois módulos acima (que já nascem ligados para
    Locadora), este é opt-in puro: mesmo Home Care e Hospital, onde laudo e
    receita têm função clínica direta, só ganham a função se o Owner ligar
    explicitamente para aquele tenant. Decisão deliberada — upload de
    documento é opcional, não presumido pelo segmento.
  - Os demais segmentos nascem sem nenhum módulo ligado.
- O Owner pode **sobrepor o padrão** para um tenant específico
  (`TenantModulo`) — ligar um módulo para quem normalmente não teria, ou
  desligar um que o segmento ligaria por padrão. A sobreposição é só
  daquele tenant; nunca vaza para outro tenant do mesmo segmento.
- O restante do código nunca pergunta "qual o segmento deste tenant" para
  decidir comportamento — sempre pergunta "este módulo está habilitado
  para este tenant" (`core.features.modulo_habilitado`). Isso é o que
  permite ativar `locacao_financeiro` para uma prefeitura que
  ocasionalmente faz locação avulsa, sem mudar o segmento dela para
  Locadora (o que mudaria também o vocabulário da tela, que é outra
  decisão).

## Validações

- Um formulário que só oferece uma opção quando o módulo está desligado
  (ex.: `tipo_documento` só CPF) recusa a outra opção mesmo que o POST seja
  forjado — a validação de `ChoiceField` do Django rejeita qualquer valor
  fora das opções construídas no `__init__`, não depende de o usuário nunca
  tentar.

## Permissões por perfil

| Ação | Nível mínimo |
|---|---|
| Ligar/desligar módulo de um tenant | Owner (plataforma) |
| Usar uma funcionalidade de um módulo já ligado | conforme a permissão normal daquela ação |

Nenhum papel dentro do tenant (nem Admin) liga ou desliga módulo — é
decisão comercial da plataforma, não operacional do cliente.

## Estados possíveis

Por módulo e por tenant: `ligado` ou `desligado` — nunca "parcialmente".

## Casos de exceção

- Um titular já cadastrado com CNPJ continua com CNPJ mesmo que o módulo
  `documento_pessoa_juridica` seja desligado depois — o dado gravado não
  muda quando o módulo muda, só a **opção de cadastrar um novo** com CNPJ
  desaparece do formulário.
- Dados financeiros (`valor_diaria`, `caucao`, `percentual_multa_atraso_
  dia`) já gravados num empréstimo continuam existindo e sendo mostrados
  na devolução mesmo que o módulo `locacao_financeiro` seja desligado
  depois — desligar o módulo esconde o **formulário de entrada** desses
  dados em novos empréstimos, não apaga histórico.
- Um documento já anexado ao titular (`documentos_beneficiario`) continua
  existindo e **continua baixável** mesmo que o módulo seja desligado
  depois — desligar esconde só a seção/rota de **upload novo**, não o
  acesso a documento já gravado. Mesmo princípio dos dois módulos acima:
  desligar módulo nunca apaga nem esconde retroativamente.
- **Ligar/desligar um módulo agora gera evento de auditoria**
  (`AcaoAuditada.ALTERACAO`, objeto o `Tenant` afetado) — antes desta
  revisão isso não era registrado para nenhum módulo do catálogo; era um
  gap silencioso, fechado junto com a adição de `documentos_beneficiario`.

## Impactos em outros módulos (de documentação)

- `docs/business-rules/unidades.md`: nenhum — módulos e unidades são
  eixos independentes de permissão (um por funcionalidade ligada, outro
  por dado visível).
- `docs/business-rules/emprestimos.md`: o wizard de empréstimo só pergunta
  valor diário/caução/multa quando `locacao_financeiro` está habilitado; a
  tela de devolução só mostra a multa estimada nesse caso.
- Cadastro de titular (`beneficiarios`): `tipo_documento` só oferece CNPJ
  quando `documento_pessoa_juridica` está habilitado.

## Módulos do catálogo hoje

### `locacao_financeiro`

- Adiciona três campos opcionais a `DetalheEmprestimo`: `valor_diaria`,
  `caucao`, `percentual_multa_atraso_dia`.
- `valor_total_periodo` é `valor_diaria × prazo_dias` — `None` se não há
  diária definida (nunca `0`, que pareceria "gratuito").
- `valor_multa_atraso(hoje=None)` estima a multa se a devolução ocorresse
  hoje: `(valor_total_periodo × percentual / 100) × dias_de_atraso`. É só
  uma estimativa informativa mostrada na tela de devolução — o sistema não
  desconta nada automaticamente, quem decide o valor final cobrado é o
  operador.
- Não é um model `ContratoLocacao` separado de propósito: são três campos
  opcionais do mesmo empréstimo, não um conceito de negócio com ciclo de
  vida próprio.

### `documento_pessoa_juridica`

- `Beneficiario.tipo_documento` (CPF ou CNPJ) e `Beneficiario.documento`
  (renomeado de `cpf`, agora genérico, `max_length=18` para caber a
  máscara de CNPJ).
- Validação despachada por `core.validadores.validar_documento(valor,
  tipo_documento)` — CPF e CNPJ têm dígito verificador calculado por
  módulo 11, cada um com sua própria tabela de pesos; nenhum é aceito como
  fallback do outro.
- Sem o módulo, o formulário de cadastro só oferece CPF como opção.

### `documentos_beneficiario`

- Controla se a ficha do titular (`beneficiarios/ficha.html`) mostra a
  seção **Documentos** — lista de anexos (RG, comprovante de residência,
  laudo, receita médica) e o formulário de upload
  (`beneficiarios/views.py::documento_novo`).
- **Ligado**: Funcionário+ (restrito ao escopo de unidade do titular) pode
  anexar e baixar documento pela própria ficha, sem precisar do Django
  Admin (docs/business-rules/beneficiarios.md).
- **Desligado**: a seção some da ficha; a rota de upload recusa mesmo um
  POST forjado — a checagem é recalculada no servidor
  (`core.features.modulo_habilitado`), não só uma questão de esconder o
  botão na tela, mesmo padrão de `executar_acao` em `ativos`.
- **Download de documento já anexado não depende deste módulo** — só o
  upload de documento novo é bloqueado quando desligado. Um documento
  anexado enquanto o módulo estava ligado continua baixável mesmo depois
  de desligado (mesmo princípio de "desligar não apaga retroativamente"
  dos outros módulos).
- Nasce **desligado para todo segmento** (sem entrada em
  `_MODULOS_PADRAO_POR_SEGMENTO`) — diferente dos outros dois módulos do
  catálogo, que já nascem ligados para Locadora. Ver "Regras de negócio"
  acima para o porquê.
- Não afeta anonimização: a seção de Documentos já some da ficha quando o
  titular está anonimizado, independentemente deste módulo estar ligado
  ou não (regra do próprio `beneficiarios`, não deste módulo).

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

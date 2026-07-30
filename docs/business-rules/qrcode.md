# QR Code e Identificação Patrimonial

## Objetivo

Identificar individualmente cada ativo, permitindo localização e operação
rápida via leitura de QR Code, sem nunca tornar o QR obrigatório para o
funcionamento do sistema.

## Fluxo operacional

```text
Escanear QR Code (ou digitar patrimônio)

↓

Abre a ficha do ativo

↓

Sistema mostra somente as ações válidas
para o status atual e o perfil do usuário
```

## Regras de negócio

- Todo ativo possui QR Code, gerado automaticamente ao salvar
  (`gerar_qr_token()`), nunca manualmente.
- O QR Code é um acelerador — nunca obrigatório. A mesma tela pode ser
  alcançada digitando o código patrimonial ou pesquisando pelo nome do
  beneficiário associado.
- Todo ativo possui código patrimonial único por tenant:
  - **Geração automática**: formato `PREFIXO-NNNNNN` (6 dígitos), por
    categoria. O prefixo vem do campo `CategoriaAtivo.prefixo` quando
    cadastrado (ex.: `CAD` para Cadeira de Rodas); senão é derivado das
    três primeiras letras do nome da categoria.
  - **Código personalizado**: o operador pode digitar um código próprio
    (ex.: de um patrimônio herdado de sistema antigo, `PMSJC-2548`) — a
    unicidade é validada no formulário.
- O sistema nunca mostra ações incompatíveis com o status atual do ativo:
  a tela de QR Code recalcula, a cada acesso, quais ações fazem sentido
  para aquele status e para o nível hierárquico de quem está logado.

## Validações

- Código digitado manualmente deve ser único no tenant (case-insensitive).
- QR Code de ativo inexistente ou de outro tenant sempre responde com a
  mesma página de erro — o sistema nunca revela que o ativo existe em
  outra organização.

## Permissões por perfil

| Ação | Nível mínimo |
|---|---|
| Escanear/localizar ativo | Funcionário |
| Ações disponíveis na tela | dependem do status do ativo — ver
  `docs/business-rules/emprestimos.md` e `manutencao.md` |

## Estados possíveis

Não aplicável diretamente — o QR Code aponta sempre para o estado atual do
ativo (ver `docs/business-rules/ativos.md`).

## Ações por status (resumo)

| Status | Ações mostradas |
|---|---|
| Disponível | Emprestar, Editar, Histórico |
| Reservado | Confirmar empréstimo, Histórico |
| Emprestado | Devolver, Renovar, Histórico |
| Em Manutenção | Finalizar manutenção, Histórico |
| Baixado | Somente visualizar |

## Casos de exceção

- Leitura de um QR Code impresso de um ativo já baixado é permitida —
  mostra a ficha em modo somente-consulta, nunca gera erro.
- Busca manual (`scan`) aceita tanto o token do QR quanto o código
  patrimonial, no mesmo campo.

## Impactos em outros módulos

- A ficha aberta pelo QR Code é a mesma ficha do ativo usada em qualquer
  outro ponto do sistema — histórico completo, timeline, movimentações,
  fotos e manutenções aparecem de forma idêntica, independente da porta de
  entrada (busca por nome, patrimônio ou QR).

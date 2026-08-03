# Fluxos de Negócio

Diagramas dos principais fluxos operacionais da plataforma. Fonte de
verdade do comportamento é sempre o código citado junto a cada diagrama —
estes fluxos são uma representação visual para orientação rápida, não uma
especificação normativa por si mesmos.

## 1. Máquina de estados do Ativo

Fonte: `ativos/domain/state_machine.py` (`_TRANSICOES_SIMPLES` +
`_TRANSICOES_COM_DESTINO`), detalhada em `docs/PLANO_DOMINIO_ATIVOS.md §5.2`.

```mermaid
stateDiagram-v2
    [*] --> Disponivel: cadastro

    Disponivel --> Emprestado: emprestimo
    Disponivel --> Reservado: reserva
    Disponivel --> Manutencao: manutencao
    Disponivel --> Baixado: baixa
    Disponivel --> Extraviado: extravio

    Reservado --> Emprestado: emprestimo
    Reservado --> Disponivel: reserva (cancelamento)

    Emprestado --> Emprestado: renovacao
    Emprestado --> Extraviado: extravio
    Emprestado --> Disponivel: devolucao (destino disponível)
    Emprestado --> Higienizacao: devolucao (destino higienização)
    Emprestado --> Manutencao: devolucao (destino manutenção)

    Higienizacao --> Disponivel: higienizacao (conclusão)

    Manutencao --> Disponivel: retorno_manutencao
    Manutencao --> Baixado: baixa

    Extraviado --> Disponivel: recuperacao

    Baixado --> [*]

    note right of Baixado
        Estado terminal — sem
        transição de volta
    end note

    note right of Emprestado
        Não pode ser TRANSFERIDO
        entre unidades enquanto
        emprestado — precisa
        devolver primeiro
    end note
```

**Transferência entre unidades** não muda o estado operacional — é
permitida a partir de `Disponivel`, `Reservado`, `Manutencao` e
`Higienizacao` (não a partir de `Emprestado`, `Baixado`, `Extraviado` ou
`Inativo`), e o estado se mantém igual (só muda `unidade` responsável).

**Inativação administrativa** (`Disponivel`/`Manutencao`/`Reservado` →
`Inativo`) não é disparada por um tipo de `Movimentacao` do fluxo
operacional — é uma ação administrativa separada (`pode_inativar` em
`state_machine.py`).

## 2. Fluxo de Empréstimo (wizard de 4 passos)

Fonte: `ativos/services.py`, `docs/business-rules/emprestimos.md`.

```mermaid
flowchart TD
    A[Ativo em estado Disponível/Reservado] --> B["Passo 1: escolher Beneficiário"]
    B --> C["Passo 2: definir prazo e data prevista de devolução"]
    C --> D{"Módulo locacao_financeiro\nhabilitado?"}
    D -- Sim --> E["Passo 3: valor diária, caução,\n% multa por atraso"]
    D -- Não --> F["Passo 3 pulado"]
    E --> G["Passo 4: assinatura do termo\n(física por padrão / digital se módulo ativo)"]
    F --> G
    G --> H["Cria Movimentacao (tipo=emprestimo)\n+ DetalheEmprestimo (1:1)"]
    H --> I["Ativo.status = emprestado"]
    I --> J["Dispara notificação\n'confirmacao_emprestimo'"]
    J --> K[Fim]
```

## 3. Fluxo de Devolução

```mermaid
flowchart TD
    A[Ativo em estado Emprestado] --> B["Operador escolhe destino"]
    B --> C{Destino}
    C -- Disponível --> D["status = disponivel"]
    C -- Higienização --> E["status = higienizacao"]
    C -- Manutenção --> F["status = manutencao\n+ pode registrar DetalheManutencao"]
    D --> G["Cria Movimentacao (tipo=devolucao)\ncom fotos de comparação entrega×devolução"]
    E --> G
    F --> G
    G --> H{"Módulo locacao_financeiro:\natraso na devolução?"}
    H -- Sim --> I["Calcula multa estimada\n(informativa — operador decide valor final)"]
    H -- Não --> J[Fim]
    I --> J
```

## 4. Job diário de notificações (vencimento/atraso)

Fonte: `notificacoes/jobs.py::executar_verificacao_diaria`.

```mermaid
flowchart TD
    A["Disparo: manage.py enviar_notificacoes_diarias\nOU cron da Vercel (CRON_SECRET)"] --> B["Para cada Tenant com ativo=True"]
    B --> C["Para cada DetalheEmprestimo\ncom Ativo.status = emprestado"]
    C --> D{"dias até data_prevista_devolucao"}
    D -- "= 7" --> E[aviso_7_dias]
    D -- "= 0" --> F[vencimento]
    D -- "< 0" --> G[atraso]
    D -- outro --> H[ignora]
    E --> I{"Já notificado hoje\ndeste tipo?"}
    F --> I
    G --> I
    I -- Não --> J["Renderiza template do tenant\n+ cria NotificacaoEnviada\n(status inicial: pendente)"]
    J --> K["_despachar (hoje: log estruturado —\nsem integração real WhatsApp/SMTP)"]
    K --> L["status = enviado/falhou"]
    I -- Sim --> H
```

## 5. Ciclo de vida de um titular sob a LGPD

Fonte: `beneficiarios/lgpd.py`, `README.md §"Direitos do titular"`.

```mermaid
flowchart TD
    A["Cadastro do Beneficiário/Paciente/Cliente"] --> B["base_legal obrigatória\n(sem hipótese declarada, não salva)"]
    B --> C{"base_legal = consentimento?"}
    C -- Sim --> D["consentimento_em registrado"]
    C -- Não --> E["Tratamento não depende\nde consentimento (Art. 7º/11)"]
    D --> F["Operação normal:\nempréstimos, documentos,\nnotificações"]
    E --> F
    F --> G{"Titular exerce direito (Art. 18)"}
    G -- "Acesso/Portabilidade" --> H["Admin exporta JSON\n(exportar_dados) — auditado"]
    G -- "Revogação de consentimento" --> I["revogar_consentimento\n(não apaga histórico já constituído)"]
    G -- "Eliminação" --> J["Admin aciona anonimizar\n(exige POST)"]
    J --> K["Remove nome/CPF/contatos\nApaga documentos do storage\nPreserva histórico de Movimentacao\n(Art. 16, I autoriza)"]
    K --> L["Registrado em RegistroAuditoria\n(ANONIMIZACAO, envolve_dado_sensivel=True)"]
    H --> M["Registrado em RegistroAuditoria\n(EXPORTACAO_DADOS)"]
    I --> N["Registrado em RegistroAuditoria\n(CONSENTIMENTO_REVOGADO)"]
```

## 6. Hierarquia de papéis e escopo de visibilidade

Fonte: `contas/models.py`, `core/unidades.py`, `ativos/domain/acoes.py`.

```mermaid
flowchart TD
    Owner["Owner (is_platform_staff)\nnível: acima de tudo, sem tenant"] --> Admin
    Admin["Admin (nível 30)\nvê TODAS as unidades do tenant"] --> Gestor
    Gestor["Gestor (nível 20)\nvê só as Unidades atribuídas (M2M)"] --> Funcionario
    Funcionario["Funcionário (nível 10)\nvê só as Unidades atribuídas (M2M)"]

    Owner -.->|"gerencia toda a plataforma\n(cross-tenant, all_tenants())"| TodosOsTenants["Todos os Tenants"]
    Admin -.->|"pode_gerenciar: Gestor/Funcionário\ndo MESMO tenant"| GestorFunc["Gestor, Funcionário"]
    Gestor -.->|"NÃO gerencia Admin\nnem Gestor de nível igual/maior"| X["✗"]
```

Regra de gestão de usuário: `Usuario.pode_gerenciar(outro)` exige mesmo
`tenant` e `nivel_hierarquico` de quem gerencia ≥ nível de quem é
gerenciado. Owner ignora tudo isso (gerencia a plataforma inteira).

## 7. Isolamento multi-tenant — onde a decisão acontece

```mermaid
flowchart TD
    A["Requisição HTTP chega"] --> B["AuthenticationMiddleware\n(popula request.user)"]
    B --> C["TenantMiddleware\n(contas/middleware.py)"]
    C --> D{"request.user tem tenant?"}
    D -- Sim --> E["set_current_tenant_id(user.tenant_id)\n— ContextVar"]
    D -- "Não (Owner/anônimo)" --> F["ContextVar permanece None"]
    E --> G["View chama Model.objects.all()"]
    F --> G
    G --> H["TenantManager.get_queryset()"]
    H --> I{"ContextVar tem tenant_id?"}
    I -- Sim --> J["Filtra automaticamente\npor esse tenant_id"]
    I -- "Não" --> K["Devolve queryset VAZIO\n(fail-closed)"]
    J --> L["View aplica ALÉM DISSO\no escopo de Unidade se aplicável\n(core.unidades)"]
    K --> M["Owner usa Model.objects.all_tenants()\nexplicitamente (exceção auditada)"]
```

## Onde encontrar as fontes destes diagramas

| Diagrama | Fonte de verdade no código |
|---|---|
| Máquina de estados | `ativos/domain/state_machine.py`, testado em `ativos/tests/test_state_machine.py` |
| Empréstimo/Devolução | `ativos/services.py`, `ativos/views.py` (wizard) |
| Notificações diárias | `notificacoes/jobs.py`, `notificacoes/services.py` |
| Direitos LGPD | `beneficiarios/lgpd.py`, testado em `beneficiarios/tests/test_lgpd.py` |
| Hierarquia/RBAC | `contas/models.py::Usuario.pode_gerenciar`, `ativos/domain/acoes.py` |
| Isolamento multi-tenant | `core/tenancy.py`, `core/models.py::TenantManager`, `contas/middleware.py` |

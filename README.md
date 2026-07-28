# Ciclartech

Plataforma de Gestão de Ativos Assistivos (multi-tenant).

Este repositório contém:

- `docs/ESPECIFICACAO_TECNICA.md` — especificação técnica e arquitetural (domínio, RF/RNF, stack).
- `docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md` — plano de evolução para plataforma SaaS (Owner/Admin/Gestor/Funcionário, segmentos, planos, `/owner`).
- `docs/PLANO_DOMINIO_ATIVOS.md` — modelagem de domínio do Ativo (máquina de estados, `Movimentacao`, `AcoesDisponiveis`, QR Code).
- O código do backend (Django): **Fase 0** (fundação técnica multi-tenant) e **Fase 1** (MVP operacional) do roadmap acima já implementadas.

## Setup de desenvolvimento

Requisitos: Python 3.11+, PostgreSQL 16 (local ou via Docker).

```bash
pip install -r requirements/dev.txt
cp .env.example .env   # ajuste DATABASE_URL se necessário

# banco local (sem Docker): crie o usuário/banco no Postgres antes de migrar
#   createuser ciclartech --pwprompt --createdb
#   createdb -O ciclartech ciclartech

python manage.py migrate
python manage.py seed_demo       # cria tenant "Prefeitura Demo" com usuários de teste
python manage.py runserver
```

Usuários de teste criados pelo `seed_demo` (senha `demo12345`): `admin_demo`, `gestor_demo`, `func_demo`.

Para simular o job diário de vencimentos (aviso 7 dias / vencimento / atraso):

```bash
python manage.py enviar_notificacoes_diarias
```

Ou via Docker Compose (`db` + `redis` + `web`):

```bash
docker compose up
```

> Banco de dados gerenciado (Supabase ou equivalente) fica para uma fase
> posterior — decisão explícita para a Fase 0, que usa PostgreSQL "puro"
> local/Docker.

### Rodando os testes

```bash
python manage.py test
```

O critério de saída da Fase 0 (docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §12)
é que a suíte de isolamento multi-tenant (`core/tests/test_tenancy.py`,
`core/tests/test_architecture.py`) e a suíte da máquina de estados do
Ativo (`ativos/tests/test_state_machine.py`, `test_services.py`,
`test_acoes_disponiveis.py`) passem integralmente.

### Estrutura de apps

| App | Responsabilidade |
|---|---|
| `core` | `Tenant`, isolamento multi-tenant (`TenantModel`/`TenantManager`), `Unidade`, `Fornecedor`, dashboard, relatórios |
| `contas` | Usuário customizado, hierarquia Owner/Admin/Gestor/Funcionário, `TenantMiddleware` |
| `ativos` | Aggregate `Ativo`, máquina de estados, `Movimentacao`, `AcoesDisponiveis`, views/telas (lista, ficha, QR Code, wizard de empréstimo, devolução, manutenção, agenda) |
| `beneficiarios` | Beneficiário/Paciente/Cliente (generalizado via `tipo_relacao`) |
| `notificacoes` | Templates e envio de notificações (WhatsApp/Email) — backend de log nesta fase; job diário via `enviar_notificacoes_diarias` |
| `owner` | Reservado (Fase 4) — área exclusiva da plataforma |

### O que já funciona (Fase 1)

- Cadastro de ativos (com upload de fotos) e beneficiários.
- Wizard de empréstimo (4 passos, assinatura física por padrão), devolução (com destino disponível/manutenção/higienização) e manutenção.
- Modo "Operação por QR Code": leitura (fallback manual + QR real gerado por ativo), painel contextual com ações filtradas por estado e por papel (RBAC).
- Timeline, movimentações, fotos (comparação entrega × devolução) na ficha do ativo.
- Agenda (devoluções hoje / próximos 7 dias / atrasados), Relatórios básicos e notificações automáticas (WhatsApp/Email) no empréstimo e no job diário de vencimento/atraso.

### Pendente para uma próxima fase

- Integração real de envio (WhatsApp Business API / SMTP) — hoje o backend registra e "envia" via log estruturado, ponto de extensão isolado em `notificacoes/services.py::_despachar`.
- Agendamento do job diário via Celery Beat (hoje é um management command, chamável por cron).
- Edição de templates de notificação pela UI (hoje só via Django Admin).

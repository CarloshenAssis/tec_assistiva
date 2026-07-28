# Ciclartech

Plataforma de Gestão de Ativos Assistivos (multi-tenant).

Este repositório contém:

- `docs/ESPECIFICACAO_TECNICA.md` — especificação técnica e arquitetural (domínio, RF/RNF, stack).
- `docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md` — plano de evolução para plataforma SaaS (Owner/Admin/Gestor/Funcionário, segmentos, planos, `/owner`).
- `docs/PLANO_DOMINIO_ATIVOS.md` — modelagem de domínio do Ativo (máquina de estados, `Movimentacao`, `AcoesDisponiveis`, QR Code).
- O código do backend (Django), iniciado na **Fase 0** do roadmap acima: fundação técnica multi-tenant.

## Setup de desenvolvimento

Requisitos: Python 3.11+, PostgreSQL 16 (local ou via Docker).

```bash
pip install -r requirements/dev.txt
cp .env.example .env   # ajuste DATABASE_URL se necessário

# banco local (sem Docker): crie o usuário/banco no Postgres antes de migrar
#   createuser ciclartech --pwprompt --createdb
#   createdb -O ciclartech ciclartech

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
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
| `core` | `Tenant`, isolamento multi-tenant (`TenantModel`/`TenantManager`), `Unidade`, `Fornecedor` |
| `contas` | Usuário customizado, hierarquia Owner/Admin/Gestor/Funcionário, `TenantMiddleware` |
| `ativos` | Aggregate `Ativo`, máquina de estados, `Movimentacao`, `AcoesDisponiveis` |
| `beneficiarios` | Beneficiário/Paciente/Cliente (generalizado via `tipo_relacao`) |
| `notificacoes` | Reservado (Fase 1) |
| `owner` | Reservado (Fase 4) — área exclusiva da plataforma |

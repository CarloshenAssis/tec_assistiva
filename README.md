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

> O banco de produção já está provisionado no Supabase (projeto
> `ciclartech`, schema aplicado via migration). Ver seção "Deploy na
> Vercel" abaixo para as variáveis de ambiente necessárias.

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

### Módulo: Mapa Operacional de Ativos

Página `/app/ativos/mapa/` — não é geolocalização em tempo real, é "onde
cada ativo está" a partir de dados já cadastrados: agrupamento por
**Unidade** e por **Bairro do beneficiário** (só para ativos emprestados),
com filtros (categoria, status, unidade, bairro) e busca por patrimônio.

A mesma **cor operacional** (`ativos/domain/cores.py::cor_operacional`) é
usada em toda a plataforma (dashboard, lista, ficha, painel de QR Code e
mapa), não só no mapa:

| Cor | Situação |
|---|---|
| 🔵 Azul | Disponível |
| 🟢 Verde | Emprestado, dentro do prazo |
| 🟢 Verde claro | Emprestado, vence em até 7 dias |
| 🟡 Amarelo | Em manutenção |
| 🔴 Vermelho (claro/médio/escuro) | Atrasado — intensidade cresce com os dias de atraso |
| ⚫ Cinza | Baixado, extraviado, inativo (fora de operação) |

### Pendente para uma próxima fase

- Integração real de envio (WhatsApp Business API / SMTP) — hoje o backend registra e "envia" via log estruturado, ponto de extensão isolado em `notificacoes/services.py::_despachar`.
- Agendamento do job diário via Celery Beat (hoje é um management command, chamável por cron).
- Edição de templates de notificação pela UI (hoje só via Django Admin).
- Filtro de "cidade" no Mapa (não modelado — só há um campo de cidade no Tenant, não por ativo/unidade).

## Deploy na Vercel

O repositório já inclui `vercel.json` + `vercel_app.py` (adaptador WSGI
para o runtime Python da Vercel) e WhiteNoise para servir os arquivos
estáticos. **Importante**: Django não é o ambiente nativo da Vercel
(pensada para serverless/Next.js) — funciona, mas com uma limitação séria:
**a Vercel não tem disco persistente entre execuções**, então uploads de
mídia (fotos de ativos/movimentações, documentos, foto do termo assinado)
gravados localmente **não sobrevivem**. Para produção real, troque
`MEDIA_ROOT` por um storage externo (Supabase Storage ou S3) antes de
depender de upload de fotos — fora do escopo desta entrega.

### Variáveis de ambiente a configurar no painel da Vercel

| Variável | Valor |
|---|---|
| `DJANGO_SECRET_KEY` | uma chave longa e aleatória (ex.: `python -c "import secrets; print(secrets.token_urlsafe(50))"`) — **nunca** a chave de desenvolvimento do `.env.example` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `ciclartech.vercel.app` |
| `DATABASE_URL` | `postgres://postgres:<SENHA_DO_BANCO>@db.tuqecavtmbkriwhnqzfu.supabase.co:5432/postgres` — pegue `<SENHA_DO_BANCO>` em Supabase → projeto **ciclartech** → Project Settings → Database (se não souber a senha, tem a opção "Reset database password" na mesma tela) |

O projeto Supabase **ciclartech** (`tuqecavtmbkriwhnqzfu`, região
`sa-east-1`) já foi criado e o schema completo (todas as tabelas,
constraints, índices e o histórico de migrations do Django) já foi
aplicado — não é necessário rodar `migrate` antes do primeiro deploy.

**Passo único pendente após o primeiro deploy funcionando**: rode
`python manage.py migrate` uma vez apontando para essa mesma
`DATABASE_URL` (da sua máquina, com a senha em mãos) — isso não altera
nenhuma tabela (já existem), mas dispara a criação dos `ContentType`/
`Permission` do Django (necessários para o Django Admin funcionar
corretamente com usuários não-superusuário) e cria o primeiro
superusuário com `python manage.py createsuperuser`.

**Segurança do Supabase**: o Supabase reportou que Row Level Security
(RLS) está desabilitado em todas as tabelas do projeto. Como o Django
conecta diretamente via Postgres (não pela API REST/`anon key` do
Supabase), isso não afeta o funcionamento do app — mas deixa os dados
acessíveis via a API REST automática do Supabase para quem tiver a
`anon key`. Se esse projeto Supabase for usado **apenas** como banco do
Django (sem PostgREST/client-side Supabase), considere desabilitar a API
REST do projeto nas configurações do Supabase, em vez de habilitar RLS
sem políticas (o que bloquearia qualquer acesso via REST, inclusive o que
você eventualmente queira usar).

# Ciclartech

Plataforma de Gestão de Ativos Assistivos (multi-tenant).

Este repositório contém:

- `docs/ESPECIFICACAO_TECNICA.md` — especificação técnica e arquitetural (domínio, RF/RNF, stack).
- `docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md` — plano de evolução para plataforma SaaS (Owner/Admin/Gestor/Funcionário, segmentos, planos, `/owner`).
- `docs/PLANO_DOMINIO_ATIVOS.md` — modelagem de domínio do Ativo (máquina de estados, `Movimentacao`, `AcoesDisponiveis`, QR Code).
- `docs/GUIA_DESENVOLVEDOR.md` — estrutura do projeto, convenções de código e fluxo de contribuição.
- `docs/REFERENCIA_BANCO_DE_DADOS.md` — dicionário de tabelas e diagrama de entidades.
- `docs/GUIA_OPERACOES.md` — operação do dia a dia da plataforma (área Owner, jobs, auditoria, banco).
- `docs/ONBOARDING_TENANT.md` — passo a passo para provisionar um cliente novo.
- `docs/TROUBLESHOOTING.md` — erros comuns e como diagnosticar.
- `docs/FLUXOS_DE_NEGOCIO.md` — diagramas dos principais fluxos operacionais.
- `docs/POLITICA_PRIVACIDADE.md` — modelo de política de privacidade (LGPD Art. 9º/41), pendente de preenchimento institucional.
- `docs/manuais/` — manuais de uso por papel (Funcionário, Gestor, Admin, Owner): cadastros, fluxo de empréstimo/devolução e como usar cada módulo da tela.
- `docs/business-rules/` — regra de negócio por assunto; `docs/features/` — documentação de feature específica.
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

## Segurança e LGPD

A plataforma armazena **dados pessoais sensíveis**: laudos e receitas
médicas são dados sobre saúde (LGPD Art. 5º, II), categoria em que um
vazamento não tem correção possível depois do fato. As decisões abaixo
partem daí.

### Controles implementados

| Camada | Controle |
|---|---|
| Configuração | A aplicação recusa subir em produção com `SECRET_KEY` de desenvolvimento, curta ou ausente (`ciclartech/seguranca.py`). `check --deploy` roda no CI com `--fail-level WARNING` |
| Transporte | HSTS (1 ano), redirecionamento HTTPS, `SECURE_PROXY_SSL_HEADER` para a borda da Vercel, cookies `Secure`/`HttpOnly`/`SameSite=Lax` |
| Navegador | CSP sem `unsafe-inline` em `script-src`, `frame-ancestors 'none'`, `form-action 'self'`, `base-uri 'self'`, `Permissions-Policy` restritiva (`core/middleware.py`) |
| Autenticação | Argon2id como hasher primário, senha mínima de 12 caracteres, bloqueio por tentativas (5 por identificação / 20 por IP, janela de 15 min), mensagens que não permitem enumerar contas |
| Sessão | Expira em 8 h de inatividade e ao fechar o navegador; páginas autenticadas com `Cache-Control: no-store` (cenário de terminal compartilhado) |
| Arquivos | Allowlist de extensão + limite de tamanho + conferência de *magic number* (bloqueia SVG com script renomeado para `.png`); entrega sempre como anexo com tipo neutro |
| Banco | RLS ativo nas 26 tabelas e `anon`/`authenticated` sem privilégio algum (ver seção do Supabase adiante) |
| Multi-tenant | Isolamento *fail-closed* no manager, já existente, agora coberto também nos novos caminhos (download de documento, exportação) |

### Direitos do titular (Art. 18)

- **Base legal obrigatória** no cadastro (`Beneficiario.base_legal`) — sem
  hipótese declarada não há tratamento lícito.
- **Acesso e portabilidade** (Art. 18, II e V): exportação em JSON pela
  ficha do titular, restrita a Admin.
- **Eliminação** (Art. 18, VI): anonimização que remove nome, CPF, contatos
  e **apaga os documentos do storage**, preservando o histórico patrimonial.
  Não é `DELETE` de propósito — o registro de movimentação de equipamento
  responde a outra finalidade e o Art. 16, I autoriza a conservação; o que
  a lei protege é a identificabilidade, e ela é removida.
- **Revogação de consentimento** (Art. 8º, §5º) registrada com data.

### Trilha de auditoria (Art. 37)

`auditoria.RegistroAuditoria` é *append-only* — `save()` de registro
existente e `delete()` são bloqueados no model, e o Django Admin é
somente-leitura. Uma trilha que o próprio sistema auditado pode editar não
serve como evidência.

Registra login (sucesso/falha/bloqueio), acesso a dado pessoal — marcando
separadamente o acesso a **dado sensível** —, exportação e anonimização.
O expurgo por retenção (padrão 24 meses) é comando deliberado:
`python manage.py expurgar_auditoria` (simula por padrão; `--confirmar` executa).

O log de aplicação **não** recebe dado pessoal: nome, telefone e conteúdo
de notificação foram removidos dele, porque a saída padrão na Vercel é
coletada e retida fora do nosso controle, sem prazo nem controle de acesso.

### Pendente para uma próxima fase

- Integração real de envio (WhatsApp Business API / SMTP) — hoje o backend registra e "envia" via log estruturado, ponto de extensão isolado em `notificacoes/services.py::_despachar`.
- Edição de templates de notificação pela UI (hoje só via Django Admin).
- Filtro de "cidade" no Mapa (não modelado — só há um campo de cidade no Tenant, não por ativo/unidade).

### Pendências de segurança que dependem de decisão ou serviço externo

Itens conhecidos e deliberadamente **não** resolvidos nesta entrega, em
ordem de risco:

1. ~~**Storage externo para mídia.**~~ Resolvido — ver seção "Storage de
   mídia (Supabase Storage / S3)" logo abaixo.
2. **Monitoramento de erro** (Sentry ou equivalente). Hoje a única forma de
   descobrir uma exceção em produção é abrir o painel da Vercel manualmente.
   Requer conta e DSN.
3. **Envio de e-mail.** A recuperação de senha está implementada e testada,
   mas sem SMTP configurado o link só vai para o log. Requer provedor.
4. **Segundo fator (2FA)** para contas Admin — dado sensível justifica, mas
   muda o fluxo de acesso de todos os administradores e é decisão de produto.
5. **`style-src 'unsafe-inline'` na CSP.** Necessário porque há ~215
   atributos `style="..."` nos templates, e atributo de estilo não aceita
   nonce nem hash. Risco baixo (CSS injetado não executa código, mas permite
   exfiltração por seletor). Eliminar exige migrar os estilos inline para
   classes no CSS.
6. **Encarregado (DPO) e política de privacidade.** O Art. 41 exige indicar
   um encarregado e o Art. 9º, transparência ao titular. Decisão
   institucional adotada: cada tenant é controlador dos dados dos seus
   próprios beneficiários (a Ciclartech é operadora da plataforma, não
   controladora), então o Encarregado é configurado por tenant —
   `Tenant.dpo_nome`/`dpo_email`/`dpo_telefone`. Quem preenche é o
   **Admin do próprio tenant**, em `/app/encarregado/`
   (`core/views_encarregado.py`) — só o próprio tenant sabe quem, na
   organização dele, deve responder por isso; o Owner também pode editar
   em `/owner/contratos/<id>/editar/` como canal de suporte, mas não é o
   fluxo esperado. O modelo do texto da política está em
   `docs/POLITICA_PRIVACIDADE.md`. Falta ainda: publicar o documento em
   local acessível ao titular dentro do próprio app (hoje só existe como
   arquivo no repositório) e, idealmente, gerar o texto por tenant a
   partir do `dpo_nome` cadastrado em vez de preenchimento manual do
   `.md`.

## Deploy na Vercel

O repositório já inclui `vercel.json` + `vercel_app.py` (adaptador WSGI
para o runtime Python da Vercel) e WhiteNoise para servir os arquivos
estáticos. **Importante**: Django não é o ambiente nativo da Vercel
(pensada para serverless/Next.js) — funciona, mas com uma limitação séria:
**a Vercel não tem disco persistente entre execuções**, então um upload
gravado em disco local não sobrevive de uma invocação para a próxima. Por
isso a mídia (fotos de ativos, documentos de beneficiário, assinatura do
termo) usa o Supabase Storage — ver a seção logo abaixo.

### Storage de mídia (Supabase Storage / S3)

`STORAGES["default"]` (`ciclartech/settings.py`) troca automaticamente de
backend conforme as variáveis de ambiente presentes:

- **Sem** `DJANGO_STORAGE_S3_ACCESS_KEY_ID`/`DJANGO_STORAGE_S3_SECRET_ACCESS_KEY`
  → disco local (`FileSystemStorage`) — o padrão em desenvolvimento.
- **Com** as duas → Supabase Storage via protocolo S3-compatível
  (`storages.backends.s3.S3Storage`).

O bucket `ciclartech-media` já foi criado no projeto Supabase, **privado**
(`public=false`): nenhum arquivo é exposto por URL direta ao storage — nem
documento de beneficiário (RG, laudo, receita médica) nem foto de
equipamento, apesar desta última não ser dado pessoal. Toda entrega passa
por view autenticada: `core.arquivos.resposta_de_download` (documentos,
sempre como anexo) e `core.arquivos.resposta_de_imagem` (fotos de
ativo/movimentação e logotipo do tenant, renderizável inline, com
`Cache-Control` de 1 ano — ver `ativos.views.foto_ativo_imagem`).

Isso corrige um problema real de custo: antes, foto de equipamento usava
`.url` (link assinado) direto no `<img src>` dos templates. Cada render
gerava uma assinatura nova (embute o timestamp da requisição), então a URL
nunca se repetia e o navegador nunca conseguia cachear — cada visita à
ficha do ativo rebaixava as fotos inteiras do Supabase Storage de novo, o
mesmo padrão que já causou estouro de egress em outro projeto. A CSP
(`img-src`, `core/middleware.py`) fica sempre restrita a `'self'` agora —
nenhum template deveria apontar para o storage diretamente; se alguém
reintroduzir isso, a imagem simplesmente não carrega (bug visível), em vez
de a CSP liberar a origem silenciosamente.

**Variáveis de ambiente para ativar** (gere as chaves em Supabase → projeto
**ciclartech** → **Project Settings** → **Storage** → aba **S3 Connection**
→ *New access key* — o valor só é mostrado uma vez):

| Variável | Valor |
|---|---|
| `DJANGO_STORAGE_S3_ACCESS_KEY_ID` | Access Key ID gerado no painel |
| `DJANGO_STORAGE_S3_SECRET_ACCESS_KEY` | Secret Access Key gerado no painel |
| `DJANGO_STORAGE_S3_BUCKET_NAME` | opcional, padrão `ciclartech-media` |
| `DJANGO_STORAGE_S3_ENDPOINT_URL` | opcional, padrão `https://tuqecavtmbkriwhnqzfu.storage.supabase.co/storage/v1/s3` |
| `DJANGO_STORAGE_S3_REGION_NAME` | opcional, padrão `sa-east-1` |

As chaves são S3 access keys (não a `anon`/`service_role` key da API) —
elas **ignoram RLS por completo** e são feitas exclusivamente para uso de
servidor confiável (documentado pelo próprio Supabase); nunca devem ir para
código versionado ou para o navegador.

### Variáveis de ambiente a configurar no painel da Vercel

**Obrigatórias** — a aplicação **se recusa a subir** em produção sem elas
(ver `ciclartech/seguranca.py`); é deliberado: melhor não subir do que
servir dado de paciente com chave pública de desenvolvimento.

| Variável | Valor |
|---|---|
| `DJANGO_SECRET_KEY` | chave longa e aleatória: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`. Mínimo de 32 caracteres, **nunca** a do `.env.example` |
| `DJANGO_DEBUG` | `False` |
| `DATABASE_URL` | `postgresql://postgres.tuqecavtmbkriwhnqzfu:<SENHA>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres` — use o **pooler**, não a conexão direta: `db.<ref>.supabase.co` só resolve em IPv6, que a Vercel não tem na saída |

**Recomendadas**:

| Variável | Valor | Por quê |
|---|---|---|
| `DJANGO_ALLOWED_HOSTS` | `ciclartech.vercel.app` | Se ausente, os domínios vêm de `VERCEL_URL`/`VERCEL_PROJECT_PRODUCTION_URL`. Um `*` aqui é descartado automaticamente com aviso — `Host` arbitrário permite envenenar o link de recuperação de senha |
| `DJANGO_PROXIES_CONFIAVEIS` | `1` | Número de proxies reversos à frente da app. Sem isso o IP registrado na auditoria é o da borda da Vercel, não o do cliente, e o bloqueio por tentativas perde precisão |
| `DJANGO_ADMIN_URL` | algo não óbvio, ex. `gestao-interna/` | Reduz o ruído de varredura automatizada em `/admin/`, que consome o limite de bloqueio de contas legítimas |
| `CRON_SECRET` | valor aleatório longo (ex.: `python -c "import secrets; print(secrets.token_urlsafe(32))"`) | Protege `/cron/notificacoes-diarias/` — a Vercel envia esse valor automaticamente como `Authorization: Bearer <CRON_SECRET>` nas chamadas de cron (`vercel.json` já declara o job, `0 12 * * *`). Sem essa variável configurada, o endpoint recusa qualquer chamada e o job diário de vencimento/atraso não roda sozinho |

**Para a recuperação de senha funcionar** (sem elas o link é apenas
registrado no log, não enviado):

| Variável | Valor |
|---|---|
| `DJANGO_EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `DJANGO_EMAIL_HOST` / `DJANGO_EMAIL_PORT` | do provedor SMTP (Resend, SendGrid, Amazon SES…) |
| `DJANGO_EMAIL_HOST_USER` / `DJANGO_EMAIL_HOST_PASSWORD` | credenciais do provedor |
| `DJANGO_DEFAULT_FROM_EMAIL` | remetente, ex. `nao-responda@seudominio.com.br` |

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

### Segurança do Supabase — exposição corrigida

Uma versão anterior deste README classificava o RLS desabilitado como
"inofensivo, porque o Django conecta direto no Postgres". **Essa avaliação
estava errada** e foi corrigida.

O que a análise anterior não considerou: o Supabase expõe automaticamente
todo o schema `public` por uma API REST (PostgREST), e concede privilégios
padrão aos papéis `anon` e `authenticated`. A chave `anon` é **pública por
design** — ela é feita para ser embutida em código de front-end. Com RLS
desligado e os grants padrão, qualquer pessoa de posse dessa chave (que é
recuperável pelo painel/API do projeto) conseguia ler as tabelas do Django
pela internet, sem autenticar no sistema.

Isso foi verificado na prática: uma requisição REST com a chave `anon`
retornou o hash de senha do usuário `admin` da tabela `contas_usuario`.
Com pacientes cadastrados, `beneficiarios_beneficiario` (nome, CPF,
endereço, telefone) estaria igualmente exposta.

Correção aplicada no banco — hoje versionada em
[`scripts/supabase_hardening.sql`](scripts/supabase_hardening.sql), depois
de ter sido aplicada manualmente uma vez direto no SQL Editor do Supabase e
**não** ter ficado registrada em lugar nenhum do repositório (ou seja:
qualquer projeto Supabase novo — staging, uma cópia de teste, um restore de
backup — nascia exposto até alguém lembrar de repetir os comandos na mão):

1. `REVOKE` de todos os privilégios de `anon` e `authenticated` sobre
   tabelas, sequences e funções do schema `public`, além do `USAGE` do
   próprio schema.
2. `ALTER DEFAULT PRIVILEGES` para que a **próxima migration do Django não
   recrie o problema** — sem isso, cada tabela nova nasceria exposta de novo.
3. `ENABLE ROW LEVEL SECURITY` em toda tabela do schema `public`, sem
   nenhuma policy. RLS sem policy nega tudo para quem não é dono da tabela;
   é a segunda barreira, caso um `GRANT` seja reconcedido por engano no
   futuro.

O Django não é afetado: ele conecta como `postgres`, que é dono das tabelas
e tem `BYPASSRLS`. Isso foi confirmado com login real na aplicação em
produção depois da mudança.

**Rode `scripts/supabase_hardening.sql` uma vez em qualquer projeto
Supabase novo desta aplicação**, logo após o primeiro `manage.py migrate`:

```bash
psql "$DATABASE_URL" -f scripts/supabase_hardening.sql
```

É idempotente (pode rodar de novo num projeto já protegido sem efeito
colateral) e cobre tabela criada depois do script (percorre `pg_tables` em
vez de listar tabela por tabela) — mas não substitui rodá-lo de novo após
uma migration que cria tabela nova, porque o passo 3 (RLS) só alcança o que
existe no banco no momento da execução.

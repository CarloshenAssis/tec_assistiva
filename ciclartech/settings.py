"""
Configurações do projeto Ciclartech (Fase 0 — fundação técnica).

Referência: docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md e docs/PLANO_DOMINIO_ATIVOS.md.
Banco de dados: PostgreSQL local (Supabase fica para uma fase posterior,
por decisão explícita — ver docs).
"""

import warnings
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from ciclartech.seguranca import (
    CHAVE_INSEGURA_PADRAO,
    avisos_de_configuracao,
    problemas_de_configuracao,
    sanear_allowed_hosts,
)

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default=CHAVE_INSEGURA_PADRAO)
DEBUG = env("DJANGO_DEBUG", default=True)

# Em desenvolvimento "*" é conveniente; em produção é recusado pela validação
# no fim deste arquivo — Host arbitrário viabiliza envenenamento de cache e
# link de recuperação de senha apontando para domínio do atacante.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"] if DEBUG else [])

# A Vercel expõe dois domínios por variável de ambiente:
#   VERCEL_URL                      -> URL específica deste deploy (muda a cada build)
#   VERCEL_PROJECT_PRODUCTION_URL   -> domínio estável de produção
# Registrar os dois evita o "Bad Request (400)" que aparece quando só o
# primeiro é conhecido e o usuário acessa pelo endereço fixo.
_dominios_vercel = [
    dominio
    for dominio in (
        env("VERCEL_URL", default=None),
        env("VERCEL_PROJECT_PRODUCTION_URL", default=None),
    )
    if dominio
]
for _dominio in _dominios_vercel:
    if _dominio not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_dominio)

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
CSRF_TRUSTED_ORIGINS += [f"https://{dominio}" for dominio in _dominios_vercel]

# Descarta o curinga '*' em produção (mantém a aplicação no ar, sem o risco
# de Host arbitrário) — ver ciclartech/seguranca.py.
ALLOWED_HOSTS, _avisos_hosts = sanear_allowed_hosts(ALLOWED_HOSTS, debug=DEBUG)
for _aviso in _avisos_hosts:
    warnings.warn(_aviso, stacklevel=2)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # Apps de domínio (monólito modular — ver docs/ESPECIFICACAO_TECNICA.md §3.2)
    "core",
    "contas",
    "ativos",
    "beneficiarios",
    "notificacoes",
    "auditoria",
    "owner",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Precisa vir depois do AuthenticationMiddleware: depende de request.user
    "contas.middleware.TenantMiddleware",
    # Expõe a requisição corrente para os sinais de auditoria (quem fez a
    # alteração) — precisa vir depois de Auth/Tenant, que é de onde vêm
    # request.user e request.tenant. Ver auditoria/rastreamento.py.
    "auditoria.middleware.CapturaRequisicaoMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Por último: enxerga a resposta pronta de todos os anteriores e só
    # acrescenta cabeçalhos, sem interferir no processamento.
    "core.middleware.CabecalhosDeSegurancaMiddleware",
]

ROOT_URLCONF = "ciclartech.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "contas.context_processors.hierarquia",
            ],
        },
    },
]

WSGI_APPLICATION = "ciclartech.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://ciclartech:ciclartech@localhost:5432/ciclartech",
    )
}

AUTH_USER_MODEL = "contas.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        # 12 em vez dos 8 padrão: o sistema guarda dado de saúde, e com
        # PBKDF2 a diferença entre 8 e 12 caracteres é a diferença entre
        # quebrável e inviável num ataque offline após vazamento do banco.
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2id como algoritmo primário. O PBKDF2 padrão do Django é aceitável,
# mas é apenas CPU-intensivo: quem obtém o dump do banco quebra senhas em
# GPU com ótimo custo-benefício. Argon2 é memory-hard, o que torna o ataque
# paralelo em GPU/ASIC caro em memória, não só em ciclo.
#
# O PBKDF2 permanece na lista para que os hashes já existentes continuem
# validando — o Django os regrava em Argon2 de forma transparente no próximo
# login de cada usuário, sem necessidade de reset de senha em massa.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    # ATENÇÃO: definir STORAGES substitui o dicionário inteiro do Django —
    # não há mesclagem com o padrão. Omitir "default" aqui faz qualquer
    # gravação de FileField/ImageField (foto de ativo, documento do
    # beneficiário, assinatura do termo) estourar InvalidStorageError.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    # Sem o sufixo "Manifest": evita depender de `collectstatic` já ter
    # rodado (a Vercel não roda comandos de build do Django
    # automaticamente) — ainda comprime (gzip/brotli) o que o WhiteNoise
    # serve.
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ATENÇÃO — Vercel (serverless) não tem disco persistente entre execuções:
# uploads de mídia (fotos de ativos/movimentações, documentos, assinatura do
# termo) gravados em MEDIA_ROOT NÃO sobrevivem entre invocações na Vercel.
# Para produção real nesse ambiente, MEDIA_ROOT precisa ser trocado por um
# storage externo (Supabase Storage/S3) antes de habilitar upload de fotos
# de verdade — ver docs/README.md, seção "Deploy na Vercel".

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "app:dashboard"
LOGOUT_REDIRECT_URL = "login"

# Caminho do Django Admin. Trocar por um valor não óbvio em produção não é
# segurança por obscuridade no lugar de controle de acesso — o login continua
# sendo a barreira real —, é redução de ruído: varredura automatizada em
# /admin/ gera tentativas que consomem o bloqueio de contas legítimas.
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/").lstrip("/")

# ===================================================================
# E-mail
# ===================================================================
# Necessário para a recuperação de senha. Sem SMTP configurado o backend cai
# para console: em desenvolvimento a mensagem aparece no terminal (fluxo
# testável), e em produção a ausência fica evidente no log em vez de falhar
# silenciosamente para o usuário que pediu a redefinição.
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("DJANGO_EMAIL_HOST", default="")
EMAIL_PORT = env.int("DJANGO_EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("DJANGO_EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("DJANGO_EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("DJANGO_EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="nao-responda@ciclartech.com.br")

# Validade do link de redefinição de senha. O padrão do Django é 3 dias;
# 1 hora é o suficiente para o usuário abrir o e-mail e reduz bastante a
# janela em que um link vazado (caixa compartilhada, encaminhamento) serve
# para tomar a conta.
PASSWORD_RESET_TIMEOUT = env.int("DJANGO_PASSWORD_RESET_TIMEOUT", default=3600)

# ===================================================================
# Segurança
# ===================================================================

# --- Sessão -------------------------------------------------------
# Terminal compartilhado (balcão de posto de saúde, recepção) é o cenário
# real de uso: a sessão precisa expirar sozinha, e fechar o navegador tem
# que encerrar o acesso.
SESSION_COOKIE_AGE = env.int("DJANGO_SESSION_COOKIE_AGE", default=8 * 60 * 60)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True  # inatividade real, não tempo desde o login
SESSION_COOKIE_HTTPONLY = True  # JavaScript não lê o cookie de sessão
SESSION_COOKIE_SAMESITE = "Lax"  # bloqueia envio em requisição cross-site

CSRF_COOKIE_HTTPONLY = False  # o template lê o token via {% csrf_token %}
CSRF_COOKIE_SAMESITE = "Lax"

# --- Cabeçalhos gerenciados pelo Django ---------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"  # a URL interna não vaza para terceiros
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Quantos proxies reversos confiáveis existem à frente da aplicação. Na
# Vercel é 1. Usado para extrair o IP real do cliente sem aceitar o
# `X-Forwarded-For` que o próprio cliente escreveu — ver auditoria/services.py.
SEGURANCA_PROXIES_CONFIAVEIS = env.int("DJANGO_PROXIES_CONFIAVEIS", default=0)

# --- Bloqueio por tentativas de login -----------------------------
SEGURANCA_LOGIN_JANELA_MINUTOS = env.int("DJANGO_LOGIN_JANELA_MINUTOS", default=15)
SEGURANCA_LOGIN_MAX_TENTATIVAS_IDENTIFICACAO = env.int(
    "DJANGO_LOGIN_MAX_TENTATIVAS", default=5
)
# Limiar por IP bem mais alto: dezenas de funcionários legítimos compartilham
# um IP atrás de NAT institucional. Serve contra password spraying, não
# contra erro de digitação. Ver contas/bloqueio.py.
SEGURANCA_LOGIN_MAX_TENTATIVAS_IP = env.int("DJANGO_LOGIN_MAX_TENTATIVAS_IP", default=20)

# --- Retenção da trilha de auditoria ------------------------------
# LGPD Art. 16: o dado não deve ser conservado além do necessário. A trilha
# também é dado pessoal (IP, usuário), então tem prazo — 24 meses cobre o
# ciclo de fiscalização sem virar arquivo permanente.
AUDITORIA_RETENCAO_DIAS = env.int("DJANGO_AUDITORIA_RETENCAO_DIAS", default=730)

# --- Upload -------------------------------------------------------
# Recusa o corpo da requisição antes de materializá-lo em memória/disco.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
# Limita a quantidade de campos por POST: sem isso, um formulário forjado com
# centenas de milhares de campos consome CPU no parsing (DoS por hash flooding).
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
# Arquivo enviado nasce legível apenas pelo dono do processo.
FILE_UPLOAD_PERMISSIONS = 0o600

if not DEBUG:
    # A Vercel encerra o TLS na borda e repassa a requisição em texto claro
    # para o runtime. Sem este cabeçalho o Django acha que a conexão é
    # insegura e — com SECURE_SSL_REDIRECT ligado — entra em laço infinito
    # de redirecionamento.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HSTS: o navegador passa a recusar HTTP para este domínio, o que fecha
    # a janela de downgrade na primeira requisição. Começa em 1 ano; o
    # preload fica desligado por padrão porque é de reversão lenta e deve
    # ser uma decisão explícita de quem opera o domínio.
    SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_HSTS_SUBDOMINIOS", default=True)
    SECURE_HSTS_PRELOAD = env.bool("DJANGO_HSTS_PRELOAD", default=False)

# O único alerta de `check --deploy` aceito conscientemente. O preload de HSTS
# inscreve o domínio numa lista embutida nos navegadores e sair dela leva
# meses — é decisão de quem opera o domínio, não padrão de biblioteca. Na
# prática o ponto é discutível hoje: `vercel.app` já consta inteiro na lista
# de preload. Quando houver domínio próprio, reavaliar e ligar via
# DJANGO_HSTS_PRELOAD=True.
#
# A lista é mantida propositalmente curta: o CI roda `check --deploy` com
# `--fail-level WARNING`, então qualquer alerta novo quebra o build.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Recusa subir com configuração insegura em produção, em vez de servir dado
# de paciente com chave pública de desenvolvimento. Ver ciclartech/seguranca.py.
_problemas = problemas_de_configuracao(
    secret_key=SECRET_KEY, allowed_hosts=ALLOWED_HOSTS, debug=DEBUG
)
if _problemas:
    raise ImproperlyConfigured(
        "Configuração de produção insegura:\n  - " + "\n  - ".join(_problemas)
    )

for _aviso in avisos_de_configuracao(secret_key=SECRET_KEY, debug=DEBUG):
    warnings.warn(_aviso, stacklevel=2)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# ===================================================================
# Logging
# ===================================================================
# Saída para stdout porque é o que a Vercel coleta. O cuidado central aqui é
# **não transformar o log em um segundo banco de dados pessoais**: mensagem de
# aplicação não deve conter nome, CPF ou conteúdo de laudo. Quem precisa saber
# "quem acessou o quê" consulta a trilha de auditoria, que tem prazo de
# retenção e controle de acesso — o log de aplicação não tem nem um nem outro.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "padrao": {
            "format": "[{levelname}] {asctime} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "padrao",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django.security": {
            # Host inválido, CSRF rejeitado, tentativa de path traversal.
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "auditoria": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Silencia o log de cada consulta em DEBUG: além de ruído, as
        # consultas carregam valores de CPF e nome nos parâmetros.
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

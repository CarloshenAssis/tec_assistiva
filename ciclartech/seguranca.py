"""
Validação da configuração de segurança do deploy.

Vive fora de `settings.py` por dois motivos: manter o settings legível e,
principalmente, permitir que estas regras sejam testadas diretamente
(`ciclartech/tests/test_seguranca_config.py`) sem precisar reimportar o
módulo de settings com o ambiente adulterado.

Princípio: em produção o sistema deve *recusar-se a subir* com uma
configuração insegura, em vez de subir silenciosamente e expor dados
pessoais sensíveis de pacientes (LGPD Art. 46 — obrigação de adotar
medidas de segurança aptas a proteger os dados).
"""

from __future__ import annotations

# Valor de desenvolvimento que jamais pode ser usado em produção — está no
# repositório e, portanto, é público para qualquer pessoa com acesso ao código.
CHAVE_INSEGURA_PADRAO = "dev-insecure-secret-key-troque-em-producao"

#: Tamanho mínimo aceitável para a SECRET_KEY. O `get_random_secret_key()`
#: do Django gera 50 caracteres; abaixo de 32 a entropia é baixa demais para
#: proteger assinatura de sessão e tokens de recuperação de senha.
TAMANHO_MINIMO_SECRET_KEY = 32


def sanear_allowed_hosts(allowed_hosts: list[str], *, debug: bool) -> tuple[list[str], list[str]]:
    """
    Remove o curinga `*` de ALLOWED_HOSTS em produção.

    Devolve `(hosts_saneados, avisos)`.

    Por que remover em vez de recusar a subir: aceitar qualquer `Host` permite
    envenenar o link de recuperação de senha (o Django monta a URL do e-mail a
    partir do cabeçalho `Host`), então o curinga precisa sair. Mas derrubar a
    aplicação por causa dele deixaria um sistema de atendimento fora do ar,
    quando a correção segura — descartar o curinga — já resolve o problema.
    Os domínios reais continuam vindo das variáveis da Vercel.

    Já a SECRET_KEY não tem equivalente: não existe "valor saneado" de uma
    chave pública, e por isso ela é tratada como erro fatal.
    """
    if debug or "*" not in allowed_hosts:
        return allowed_hosts, []

    saneados = [host for host in allowed_hosts if host != "*"]
    aviso = (
        "DJANGO_ALLOWED_HOSTS continha '*', que foi DESCARTADO por aceitar "
        "qualquer cabeçalho Host (viabiliza envenenamento do link de "
        "recuperação de senha). Defina explicitamente os domínios da aplicação."
    )
    return saneados, [aviso]


def problemas_de_configuracao(
    *,
    secret_key: str,
    allowed_hosts: list[str],
    debug: bool,
) -> list[str]:
    """
    Lista os problemas de segurança bloqueantes da configuração recebida.

    Devolve uma lista vazia quando a configuração é aceitável. Não levanta
    exceção: quem chama decide o que fazer (o settings levanta
    `ImproperlyConfigured`; um health check pode apenas reportar).
    """
    problemas: list[str] = []

    if debug:
        # Em desenvolvimento nada disso é bloqueante — o objetivo aqui é
        # proteger o ambiente de produção, não atrapalhar quem roda local.
        return problemas

    if not secret_key or secret_key == CHAVE_INSEGURA_PADRAO:
        problemas.append(
            "DJANGO_SECRET_KEY não foi definida (ou está usando o valor de "
            "desenvolvimento, que é público no repositório). Gere uma nova com "
            "`python -c \"from django.core.management.utils import "
            'get_random_secret_key; print(get_random_secret_key())"`.'
        )
    elif len(secret_key) < TAMANHO_MINIMO_SECRET_KEY:
        problemas.append(
            f"DJANGO_SECRET_KEY tem apenas {len(secret_key)} caracteres; "
            f"o mínimo aceitável é {TAMANHO_MINIMO_SECRET_KEY}."
        )

    if "*" in allowed_hosts:
        problemas.append(
            "DJANGO_ALLOWED_HOSTS contém '*', o que aceita qualquer cabeçalho "
            "Host e viabiliza envenenamento de cache e links de recuperação de "
            "senha apontando para domínio de terceiros. Liste os domínios "
            "explicitamente."
        )

    if not allowed_hosts:
        problemas.append(
            "DJANGO_ALLOWED_HOSTS está vazia em produção — defina ao menos o "
            "domínio oficial da aplicação."
        )

    return problemas

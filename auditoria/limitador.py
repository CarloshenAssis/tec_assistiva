"""
Limite de taxa para ações autenticadas sensíveis (movimentar ativo,
exportar dados de um titular, anonimizar).

Mesmo raciocínio de `contas/bloqueio.py` (bloqueio de login), reaproveitado
aqui: o estado é *derivado da trilha de auditoria* (Postgres), nunca de
`django.core.cache`. Um `LocMemCache` seria inofensivo na prática em
produção — a Vercel é serverless, cada invocação é um processo novo sem
memória compartilhada, então o contador nasceria zerado a cada requisição e
o limite nunca travaria nada.

O que isto resolve: login já tem bloqueio por tentativa (contas/bloqueio.py),
mas uma conta legítima (ou comprometida) não tinha *nenhuma* barreira depois
de autenticada — um script podia chamar `executar_acao` (emprestar, devolver,
transferir, dar baixa) milhares de vezes por minuto, e a única forma de
descobrir seria alguém ler a trilha de auditoria depois do estrago feito.
Isto não impede um usuário autorizado de operar normalmente (os limiares são
generosos para uso humano de balcão) — impede que a mesma conta vire uma
metralhadora de requisições.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from auditoria.models import AcaoAuditada, RegistroAuditoria


def _config(nome: str, padrao: int) -> int:
    """Lê uma configuração de limite em `settings`, com valor padrão.

    Args:
        nome: Nome do atributo em `django.conf.settings`.
        padrao: Valor a usar se `settings` não definir `nome`.

    Returns:
        O valor configurado, ou `padrao`.
    """
    return getattr(settings, nome, padrao)


def limite_atingido(
    *,
    usuario,
    objeto_tipo: str,
    limite: int,
    janela_minutos: int,
    acao: str = AcaoAuditada.CRIACAO,
) -> bool:
    """Verifica se `usuario` estourou o limite de `acao` sobre `objeto_tipo`.

    Semântica da janela: é uma janela deslizante (sliding window), não uma
    janela fixa por relógio — conta todos os eventos `acao`/`objeto_tipo` de
    `usuario` com `criado_em >= agora - janela_minutos`, recalculado a cada
    chamada. Não há reset em horário fixo; o contador "esfria" evento a
    evento, à medida que cada um sai da janela.

    `objeto_tipo` é `f"{app_label}.{NomeDaClasse}"` — **preserva a
    capitalização do model** (ex.: `Movimentacao._meta.label`, que vale
    `"ativos.Movimentacao"`, não `"ativos.movimentacao"`). É o mesmo formato
    que `auditoria.services._rotulo_do_objeto` grava (usa `_meta.object_name`,
    não `_meta.model_name`). Sempre passe `Model._meta.label` no lugar de
    escrever a string à mão — foi exatamente esse descasamento de maiúscula
    que fez a primeira versão deste limitador nunca contar nada.

    Conta pela trilha automática (`auditoria/rastreamento.py`) ou pelos
    eventos explícitos de LGPD (`EXPORTACAO_DADOS`/`ANONIMIZACAO`) — não é
    preciso instrumentar um contador novo por fora: a auditoria já grava, o
    limitador só consulta o que já existe.

    Usuário anônimo nunca é limitado por aqui — toda view protegida por
    este limitador já exige login antes (`@tenant_required`); quem não
    autenticou é outro problema (bloqueio de login, `contas/bloqueio.py`).

    Args:
        usuario: Usuário autenticado a checar. Anônimo/`None` nunca atinge
            o limite (devolve `False` direto).
        objeto_tipo: Rótulo `"app_label.NomeDaClasse"` do model-alvo,
            obtido via `Model._meta.label`.
        limite: Quantidade de eventos que, atingida ou ultrapassada dentro
            da janela, caracteriza o limite como atingido.
        janela_minutos: Tamanho da janela deslizante, em minutos, contada
            a partir do instante da chamada.
        acao: Ação auditada a contar (`AcaoAuditada.CRIACAO` por padrão).

    Returns:
        `True` se `usuario` já produziu `limite` ou mais eventos `acao`
        sobre `objeto_tipo` nos últimos `janela_minutos`; `False` caso
        contrário (inclusive para usuário anônimo).
    """
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False

    desde = timezone.now() - timezone.timedelta(minutes=janela_minutos)
    total = RegistroAuditoria.objects.filter(
        usuario=usuario, acao=acao, objeto_tipo=objeto_tipo, criado_em__gte=desde
    ).count()
    return total >= limite


def registrar_limite_atingido(
    *, request, objeto_tipo: str, limite: int, janela_minutos: int, descricao: str
) -> None:
    """Grava, no máximo uma vez por janela, que o limite foi atingido.

    Semântica da janela: mesma janela deslizante de `limite_atingido` —
    "recente" aqui significa `criado_em >= agora - janela_minutos`. Mesmo
    motivo do `bloqueio_tentativas` de login: quem está abusando controla o
    volume de tentativas bloqueadas, então logar cada uma seria o próprio
    vetor de inundação da trilha que a auditoria deveria detectar, não
    alimentar.

    A deduplicação usa a mesma `descricao` (ela já identifica objeto_tipo +
    limiar, ver chamadores) dentro da janela corrente — se já existe um
    registro de bloqueio igual e recente, não grava de novo.

    Args:
        request: A requisição corrente, de onde saem usuário/IP/user agent
            gravados no registro.
        objeto_tipo: Rótulo do model-alvo, só para compor `descricao` nos
            chamadores (não usado diretamente aqui além da deduplicação).
        limite: Limiar que foi atingido, só para compor `descricao` nos
            chamadores.
        janela_minutos: Tamanho da janela deslizante usada tanto para
            checar o limite quanto para deduplicar este registro.
        descricao: Texto que identifica objeto_tipo + limiar; é a chave de
            deduplicação dentro da janela.
    """
    from auditoria.services import registrar  # import tardio: evita ciclo

    desde = timezone.now() - timezone.timedelta(minutes=janela_minutos)
    ja_registrado = RegistroAuditoria.objects.filter(
        usuario=request.user,
        acao=AcaoAuditada.ACESSO_NEGADO,
        descricao=descricao,
        criado_em__gte=desde,
    ).exists()
    if ja_registrado:
        return

    registrar(AcaoAuditada.ACESSO_NEGADO, request=request, descricao=descricao)

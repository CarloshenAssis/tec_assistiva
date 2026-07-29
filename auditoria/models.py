"""
Trilha de auditoria da plataforma.

Atende dois requisitos que andam juntos:

1. LGPD Art. 37 — o controlador deve manter registro das operações de
   tratamento de dados pessoais que realizar. Como a plataforma trata dados
   de saúde (laudos, receitas médicas), que são *dados pessoais sensíveis*
   (Art. 5º, II), esse registro deixa de ser boa prática e vira obrigação.
2. Forense de segurança — sem trilha não há como responder "quem viu o
   prontuário de quem, e quando" depois de um incidente, nem cumprir o
   dever de comunicação de incidente do Art. 48.

O registro é *append-only*: `save()` de instância já persistida e `delete()`
são bloqueados no nível do model, pelo mesmo raciocínio de
`ativos.Movimentacao` — uma trilha de auditoria que pode ser editada pelo
próprio sistema auditado não serve como evidência.
"""

from __future__ import annotations

from django.db import models


class AcaoAuditada(models.TextChoices):
    """
    Catálogo fechado de eventos auditáveis.

    Deliberadamente enxuto: registrar *tudo* produz um volume que ninguém lê
    e que por si só vira um novo repositório de dados pessoais. O critério de
    inclusão é "esse evento seria pedido numa investigação de incidente ou
    numa fiscalização da ANPD".
    """

    # Autenticação e controle de acesso
    LOGIN_SUCESSO = "login_sucesso", "Login realizado"
    LOGIN_FALHA = "login_falha", "Tentativa de login malsucedida"
    LOGOUT = "logout", "Logout"
    BLOQUEIO_TENTATIVAS = "bloqueio_tentativas", "Conta bloqueada por tentativas"
    ACESSO_NEGADO = "acesso_negado", "Acesso negado a recurso protegido"
    SENHA_ALTERADA = "senha_alterada", "Senha alterada"
    SENHA_RESET_SOLICITADO = "senha_reset_solicitado", "Recuperação de senha solicitada"

    # Tratamento de dados pessoais
    ACESSO_DADO_PESSOAL = "acesso_dado_pessoal", "Acesso a dado pessoal"
    CRIACAO = "criacao", "Registro criado"
    ALTERACAO = "alteracao", "Registro alterado"
    EXCLUSAO = "exclusao", "Registro excluído"

    # Direitos do titular (LGPD Art. 18)
    EXPORTACAO_DADOS = "exportacao_dados", "Dados do titular exportados"
    ANONIMIZACAO = "anonimizacao", "Dados do titular anonimizados"
    CONSENTIMENTO_REGISTRADO = "consentimento_registrado", "Consentimento registrado"
    CONSENTIMENTO_REVOGADO = "consentimento_revogado", "Consentimento revogado"


class RegistroAuditoria(models.Model):
    """
    Um evento auditável. Nunca alterado, nunca apagado pelo sistema.

    Não herda de `TenantModel` de propósito: parte dos eventos mais
    importantes acontece justamente quando ainda não há tenant no contexto
    (uma tentativa de login que falhou antes de identificar o usuário, por
    exemplo). O `tenant` fica como FK opcional e o filtro por tenant é
    explícito em quem consulta.
    """

    tenant = models.ForeignKey(
        "core.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    usuario = models.ForeignKey(
        "contas.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    #: Cópia textual de quem agiu, preservada mesmo que o usuário seja
    #: removido depois (`usuario` vira NULL, este campo permanece). Sem isso,
    #: apagar o usuário apagaria a autoria de toda a trilha.
    usuario_identificacao = models.CharField(max_length=254, blank=True)

    acao = models.CharField(max_length=40, choices=AcaoAuditada.choices)

    #: Rótulo do model afetado no formato "app_label.ModelName". String em vez
    #: de FK para ContentType para que a trilha sobreviva à remoção de um app.
    objeto_tipo = models.CharField(max_length=100, blank=True)
    objeto_id = models.CharField(max_length=64, blank=True)

    descricao = models.CharField(max_length=255, blank=True)

    #: Marca eventos que envolvem dados pessoais *sensíveis* (saúde, no caso
    #: deste produto). Permite responder rapidamente "que acessos a dado
    #: sensível houve no período X" sem varrer a trilha inteira.
    envolve_dado_sensivel = models.BooleanField(default=False)

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Registro de Auditoria"
        verbose_name_plural = "Registros de Auditoria"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["-criado_em"]),
            models.Index(fields=["acao", "-criado_em"]),
            models.Index(fields=["tenant", "-criado_em"]),
            models.Index(fields=["objeto_tipo", "objeto_id"]),
            # Suporta o relatório de acessos a dado sensível sem varredura completa.
            models.Index(fields=["envolve_dado_sensivel", "-criado_em"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError(
                "RegistroAuditoria é append-only: um registro já gravado não "
                "pode ser alterado. Ver auditoria/models.py."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError(
            "RegistroAuditoria é append-only: registros não podem ser "
            "excluídos individualmente. O expurgo por prazo de retenção é "
            "feito pelo comando `expurgar_auditoria`."
        )

    def __str__(self) -> str:
        quem = self.usuario_identificacao or "anônimo"
        return f"{self.criado_em:%d/%m/%Y %H:%M} · {quem} · {self.get_acao_display()}"

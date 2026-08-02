"""
Formulários de autenticação com bloqueio por tentativas.
"""

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db import models

from auditoria.services import ip_do_cliente
from contas.bloqueio import esta_bloqueado
from contas.models import Papel, Usuario
from core.models import Unidade

#: Mensagem deliberadamente genérica e idêntica para todos os casos de
#: bloqueio. Dizer "restam N tentativas" ou "esta conta está bloqueada"
#: confirmaria a existência do usuário para quem está enumerando contas.
MENSAGEM_BLOQUEIO = (
    "Muitas tentativas de acesso a partir deste ponto. "
    "Aguarde alguns minutos antes de tentar novamente."
)


class FormularioLoginSeguro(AuthenticationForm):
    """
    `AuthenticationForm` com verificação de bloqueio antes da autenticação.

    A checagem acontece em `clean()` **antes** de `super().clean()` para que
    uma tentativa barrada nunca chegue a executar o hash da senha: além de
    poupar CPU (o PBKDF2 é caro por definição), isso impede que o tempo de
    resposta diferencie "bloqueado" de "senha errada".
    """

    #: Substitui a mensagem padrão do Django por uma que não revela nada
    #: sobre a existência da conta — e em português, já que é a que o
    #: usuário final lê.
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuário ou senha inválidos.",
        "inactive": "Usuário ou senha inválidos.",
    }

    def clean(self):
        identificacao = (self.data.get("username") or "").strip()
        ip = ip_do_cliente(self.request) if self.request is not None else None

        resultado = esta_bloqueado(identificacao=identificacao, ip=ip)
        if resultado.bloqueado:
            raise forms.ValidationError(MENSAGEM_BLOQUEIO, code="bloqueado_por_tentativas")

        return super().clean()


class CriarUsuarioForm(forms.Form):
    """
    Cria Gestor/Funcionário dentro do próprio tenant de quem está criando.

    Sem campo de senha — mesmo motivo do Owner ao gerar o primeiro acesso do
    Admin (ver `owner.forms.CriarAdministradorForm` e `contas.senhas`):
    ninguém escolhe a senha de outra pessoa.

    As opções de papel oferecidas dependem de `nivel_criador`, estritamente
    ABAIXO do nível de quem cria (Admin=30 oferece Gestor/Funcionário;
    Gestor=20 oferece só Funcionário). Isso é mais restritivo que
    `Usuario.pode_gerenciar` (que usa `>=` e permite gerenciar um par de
    mesmo nível já existente) de propósito: criar uma conta nova do mesmo
    nível hierárquico do criador não é o fluxo que este formulário atende —
    contas de Admin nascem só pelo Owner (ver owner/views.py::criar_administrador).
    """

    username = forms.CharField(max_length=150, label="Usuário (login)")
    email = forms.EmailField(label="E-mail")
    first_name = forms.CharField(max_length=150, required=False, label="Nome")
    last_name = forms.CharField(max_length=150, required=False, label="Sobrenome")
    papel = forms.ModelChoiceField(queryset=Papel.objects.none(), label="Papel")
    #: Unidades que a pessoa poderá operar (docs/business-rules/unidades.md
    #: — unidade é permissão, não atributo fixo). **Obrigatório**: este
    #: formulário só cria Gestor ou Funcionário (nunca Admin — ver docstring
    #: da classe), e ambos os papéis são restritos por unidade
    #: (`core.unidades.unidades_visiveis`). Sem ao menos uma unidade
    #: marcada, a pessoa recém-criada não enxergaria nenhum ativo/
    #: beneficiário até alguém editar o cadastro dela depois — melhor
    #: barrar isso na criação do que deixar o usuário logar num sistema
    #: vazio sem saber por quê.
    unidades = forms.ModelMultipleChoiceField(
        queryset=Unidade.objects.none(),
        required=True,
        label="Unidades permitidas",
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Selecione ao menos uma unidade."},
    )

    def __init__(self, *args, nivel_criador: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["papel"].queryset = Papel.objects.filter(
            nivel_hierarquico__lt=nivel_criador
        ).order_by("-nivel_hierarquico")
        # `Unidade.objects` (TenantManager) já vem escopado ao tenant
        # corrente — o form só é instanciado dentro de uma view protegida
        # por `tenant_required`, então o ContextVar já está setado.
        self.fields["unidades"].queryset = Unidade.objects.filter(ativo=True).order_by("nome")

    def clean_username(self):
        # `Usuario.objects` já é cross-tenant por padrão (herda o
        # `UserManager` do Django, não o `TenantManager` fail-closed dos
        # demais models — ver contas/models.py). O username é único na
        # plataforma inteira, não só no tenant.
        username = self.cleaned_data["username"].strip()
        if Usuario.objects.filter(username=username).exists():
            raise forms.ValidationError("Já existe um usuário com este nome de login.")
        return username


class EditarUsuarioForm(forms.Form):
    """
    Edita e-mail, nome, papel e unidades de um usuário já existente do
    próprio tenant — login (`username`) não é editável aqui de propósito,
    é o identificador usado em toda a trilha de auditoria e em logins já
    feitos; renomear afetaria histórico e é operação rara o bastante para
    não precisar de tela (recriar a conta cobre esse caso excepcional).

    Sem campo de senha, mesmo motivo de `CriarUsuarioForm` — trocar senha
    de terceiro é a tela "Gerar nova senha", não esta.

    `papel`: quem edita nunca pode PROMOVER alguém a um nível igual ou
    acima do próprio (mesmo teto de `CriarUsuarioForm`), mas precisa poder
    salvar o formulário sem mudar o papel de um usuário que já gerencia
    (ex.: Gestor editando o e-mail de outro Gestor, permitido por
    `Usuario.pode_gerenciar` que usa `>=`) — por isso o papel atual do
    usuário editado sempre entra na lista de opções, mesmo quando está no
    nível do próprio editor ou acima.
    """

    email = forms.EmailField(label="E-mail")
    first_name = forms.CharField(max_length=150, required=False, label="Nome")
    last_name = forms.CharField(max_length=150, required=False, label="Sobrenome")
    papel = forms.ModelChoiceField(queryset=Papel.objects.none(), label="Papel")
    unidades = forms.ModelMultipleChoiceField(
        queryset=Unidade.objects.none(),
        required=True,
        label="Unidades permitidas",
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Selecione ao menos uma unidade."},
    )

    def __init__(self, *args, nivel_editor: int, papel_atual_id: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["papel"].queryset = Papel.objects.filter(
            models.Q(nivel_hierarquico__lt=nivel_editor) | models.Q(pk=papel_atual_id)
        ).order_by("-nivel_hierarquico")
        self.fields["unidades"].queryset = Unidade.objects.filter(ativo=True).order_by("nome")

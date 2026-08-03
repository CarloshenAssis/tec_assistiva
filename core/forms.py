"""Formulários do app `core`: Encarregado, logotipo, Unidade e Fornecedor."""

from django import forms

from core.models import Fornecedor, Tenant, Unidade


class EncarregadoForm(forms.ModelForm):
    """Formulário do Encarregado (DPO) do próprio tenant (LGPD Art. 41).

    Editado pelo Admin do tenant, não pelo Owner: cada tenant é
    controlador dos dados dos seus próprios beneficiários (a Ciclartech
    é operadora da plataforma), então só o próprio tenant sabe quem, na
    organização dele, responde por isso. Ver docs/POLITICA_PRIVACIDADE.md.
    """

    class Meta:
        model = Tenant
        fields = ["dpo_nome", "dpo_email", "dpo_telefone"]


class LogoForm(forms.ModelForm):
    """Formulário do logotipo da instituição.

    Editado pelo Admin do próprio tenant — mesmo raciocínio do
    `EncarregadoForm`: identidade visual da etiqueta é decisão do
    tenant, não da Ciclartech.
    """

    class Meta:
        model = Tenant
        fields = ["logo"]


class UnidadeForm(forms.ModelForm):
    """Formulário de cadastro/edição de `Unidade`.

    Precisa de `tenant` explícito no `__init__` porque a instância só
    recebe `tenant` DEPOIS de `form.is_valid()` (a view faz
    `commit=False` e atribui o tenant do usuário logado antes de salvar)
    — nesse momento a validação automática de unicidade do Django (que
    olha `UniqueConstraint` na instância) ainda não tem o tenant
    preenchido e não pega o conflito. Sem `clean_nome`, criar uma unidade
    com nome já usado no mesmo tenant não vira erro de formulário: vira
    `IntegrityError` (HTTP 500) direto do banco na hora do `save()`.
    """

    class Meta:
        model = Unidade
        fields = [
            "nome",
            "tipo",
            "responsavel",
            "telefone",
            "email",
            "endereco",
            "cidade",
            "uf",
            "observacoes",
            "ativo",
        ]
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 3}),
            "uf": forms.TextInput(attrs={"maxlength": 2, "style": "text-transform:uppercase;"}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        """Inicializa o formulário, guardando o tenant para validação de unicidade.

        Args:
            *args: Argumentos posicionais repassados a `forms.ModelForm`.
            tenant: O `Tenant` do usuário logado. Se omitido, tenta obter
                de `self.instance.tenant` (edição de registro existente).
            **kwargs: Argumentos nomeados repassados a `forms.ModelForm`.
        """
        super().__init__(*args, **kwargs)
        self._tenant = tenant or getattr(self.instance, "tenant", None)

    def clean_nome(self):
        """Valida que o nome da unidade é único dentro do tenant.

        Nota de implementação: `Unidade.objects` (TenantManager,
        fail-closed) basta aqui, porque este form só é usado dentro de
        views protegidas por `tenant_required`, onde o ContextVar do
        tenant corrente já está setado e corresponde a `self._tenant` —
        não precisa de `all_tenants()`.

        Returns:
            O nome, sem espaços nas pontas.

        Raises:
            django.forms.ValidationError: Se já existir outra unidade com
                o mesmo nome (case-insensitive) no tenant.
        """
        nome = self.cleaned_data["nome"].strip()
        conflito = Unidade.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if self._tenant and conflito.exists():
            raise forms.ValidationError("Já existe uma unidade com este nome.")
        return nome


class FornecedorForm(forms.ModelForm):
    """Formulário de cadastro/edição de `Fornecedor`.

    Mesmo motivo do `clean_nome` de `UnidadeForm` acima.
    """

    class Meta:
        model = Fornecedor
        fields = ["nome", "contato", "telefone"]

    def __init__(self, *args, tenant=None, **kwargs):
        """Inicializa o formulário, guardando o tenant para validação de unicidade.

        Args:
            *args: Argumentos posicionais repassados a `forms.ModelForm`.
            tenant: O `Tenant` do usuário logado. Se omitido, tenta obter
                de `self.instance.tenant`.
            **kwargs: Argumentos nomeados repassados a `forms.ModelForm`.
        """
        super().__init__(*args, **kwargs)
        self._tenant = tenant or getattr(self.instance, "tenant", None)

    def clean_nome(self):
        """Valida que o nome do fornecedor é único dentro do tenant.

        Returns:
            O nome, sem espaços nas pontas.

        Raises:
            django.forms.ValidationError: Se já existir outro fornecedor
                com o mesmo nome (case-insensitive) no tenant.
        """
        nome = self.cleaned_data["nome"].strip()
        conflito = Fornecedor.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if self._tenant and conflito.exists():
            raise forms.ValidationError("Já existe um fornecedor com este nome.")
        return nome

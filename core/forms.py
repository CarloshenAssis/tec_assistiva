from django import forms

from core.models import Unidade


class UnidadeForm(forms.ModelForm):
    """
    Precisa de `tenant` explícito no `__init__` porque a instância só recebe
    `tenant` DEPOIS de `form.is_valid()` (a view faz `commit=False` e atribui
    o tenant do usuário logado antes de salvar) — nesse momento a validação
    automática de unicidade do Django (que olha `UniqueConstraint` na
    instância) ainda não tem o tenant preenchido e não pega o conflito. Sem
    este `clean_nome`, criar uma unidade com nome já usado no mesmo tenant
    não vira erro de formulário: vira `IntegrityError` (HTTP 500) direto do
    banco na hora do `save()`.
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
        super().__init__(*args, **kwargs)
        self._tenant = tenant or getattr(self.instance, "tenant", None)

    def clean_nome(self):
        # `Unidade.objects` (TenantManager, fail-closed) basta aqui: este
        # form só é usado dentro de views protegidas por `tenant_required`,
        # onde o ContextVar do tenant corrente já está setado e corresponde
        # a `self._tenant` — não precisa de `all_tenants()`.
        nome = self.cleaned_data["nome"].strip()
        conflito = Unidade.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if self._tenant and conflito.exists():
            raise forms.ValidationError("Já existe uma unidade com este nome.")
        return nome

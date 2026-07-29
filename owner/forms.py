from django import forms

from contas.models import Usuario
from core.models import Tenant


class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ["nome", "slug", "segmento", "cidade", "uf", "ativo"]
        widgets = {
            "uf": forms.TextInput(attrs={"maxlength": 2, "style": "text-transform:uppercase;"}),
        }


class CriarAdministradorForm(forms.Form):
    """
    Gera o primeiro acesso do administrador de um contrato B2G/B2B.

    Sem campo de senha de propósito: quem cria a conta (o Owner) nunca
    escolhe a senha de outra pessoa — ela é gerada aleatoriamente em
    `contas.senhas.gerar_senha_temporaria()` e mostrada uma única vez.
    """

    username = forms.CharField(max_length=150, label="Usuário (login)")
    email = forms.EmailField(label="E-mail")
    first_name = forms.CharField(max_length=150, required=False, label="Nome")
    last_name = forms.CharField(max_length=150, required=False, label="Sobrenome")

    def clean_username(self):
        # `Usuario.objects` já é cross-tenant por padrão (herda o
        # `UserManager` do Django via `AbstractUser`, não o `TenantManager`
        # fail-closed dos demais models de domínio — ver contas/models.py).
        # O username precisa ser único na plataforma inteira, não só no
        # tenant, então essa ausência de filtro é o comportamento certo aqui.
        username = self.cleaned_data["username"].strip()
        if Usuario.objects.filter(username=username).exists():
            raise forms.ValidationError("Já existe um usuário com este nome de login.")
        return username

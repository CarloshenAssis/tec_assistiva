from django import forms

from beneficiarios.models import Beneficiario


class BeneficiarioForm(forms.ModelForm):
    class Meta:
        model = Beneficiario
        fields = [
            "tipo_relacao",
            "nome",
            "cpf",
            "rg",
            "data_nascimento",
            "telefone",
            "whatsapp",
            "email",
            "endereco",
            "cidade",
            "bairro",
            "cep",
            "contato_emergencia_nome",
            "contato_emergencia_telefone",
            "contato_emergencia_parentesco",
        ]
        widgets = {
            "data_nascimento": forms.DateInput(attrs={"type": "date"}),
        }

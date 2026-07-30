from django import forms

from beneficiarios.models import Beneficiario
from core.unidades import unidades_visiveis
from core.validadores import validar_cpf


class BeneficiarioForm(forms.ModelForm):
    class Meta:
        model = Beneficiario
        fields = [
            "unidade",
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
            "base_legal",
        ]
        widgets = {
            "data_nascimento": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unidade"].required = False
        self.fields["unidade"].empty_label = "Toda a organização"
        if usuario is not None:
            # Um Gestor não pode cadastrar um titular dentro de uma unidade que
            # ele não opera — deixaria de vê-lo no instante seguinte ao salvar.
            self.fields["unidade"].queryset = unidades_visiveis(usuario).filter(
                ativo=True
            ).order_by("nome")

    def clean_cpf(self):
        cpf = self.cleaned_data["cpf"]
        validar_cpf(cpf)
        return cpf

    def clean(self):
        dados = super().clean()
        # Base legal "consentimento" sem o consentimento registrado é
        # tratamento sem amparo. Marcamos o momento aqui, no cadastro, que é
        # quando o funcionário confirma que colheu o aceite do titular.
        if dados.get("base_legal") == Beneficiario.BaseLegal.CONSENTIMENTO:
            if self.instance.consentimento_em is None:
                from django.utils import timezone

                self.instance.consentimento_em = timezone.now()
        return dados

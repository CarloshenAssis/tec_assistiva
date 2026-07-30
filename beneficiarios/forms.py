from django import forms

from beneficiarios.models import Beneficiario
from core import features
from core.models import Tenant
from core.unidades import unidades_visiveis
from core.validadores import validar_documento

#: `tipo_relacao` que já vem pré-selecionado no cadastro, conforme o
#: segmento do tenant — mesma ideia de vocabulário de
#: `core.models.Tenant.rotulo_beneficiario_singular`, mas aplicada ao
#: valor salvo, não só ao rótulo da tela. Continua editável: uma
#: prefeitura pode ocasionalmente cadastrar alguém como "Cliente" (ex.:
#: locação avulsa dentro de um fundo social), então isto é só o padrão
#: sugerido, nunca uma trava.
_TIPO_RELACAO_PADRAO_POR_SEGMENTO = {
    Tenant.Segmento.LOCADORA: Beneficiario.TipoRelacao.CLIENTE,
    Tenant.Segmento.HOME_CARE: Beneficiario.TipoRelacao.PACIENTE,
    Tenant.Segmento.HOSPITAL: Beneficiario.TipoRelacao.PACIENTE,
}


class BeneficiarioForm(forms.ModelForm):
    class Meta:
        model = Beneficiario
        fields = [
            "unidade",
            "tipo_relacao",
            "nome",
            "tipo_documento",
            "documento",
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
        self.fields["documento"].label = "CPF"
        # CNPJ só aparece como opção para tenant com o módulo habilitado
        # (docs/business-rules/modulos.md) — sem isto, um titular cadastrado
        # como CNPJ num tenant que depois perde o módulo ficaria com um valor
        # que o form nem oferece mais; a opção some, o dado gravado não muda.
        if usuario is not None and not features.modulo_habilitado(
            usuario.tenant, features.DOCUMENTO_PESSOA_JURIDICA
        ):
            self.fields["tipo_documento"].choices = [
                (Beneficiario.TipoDocumento.CPF.value, Beneficiario.TipoDocumento.CPF.label)
            ]
            self.fields["tipo_documento"].initial = Beneficiario.TipoDocumento.CPF
        else:
            self.fields["documento"].label = "CPF/CNPJ"
        if usuario is not None:
            # Um Gestor não pode cadastrar um titular dentro de uma unidade que
            # ele não opera — deixaria de vê-lo no instante seguinte ao salvar.
            self.fields["unidade"].queryset = unidades_visiveis(usuario).filter(
                ativo=True
            ).order_by("nome")
            # Só no cadastro (nunca sobrescreve o que já foi salvo na edição).
            if not self.instance.pk and usuario.tenant_id:
                padrao = _TIPO_RELACAO_PADRAO_POR_SEGMENTO.get(usuario.tenant.segmento)
                if padrao:
                    self.fields["tipo_relacao"].initial = padrao

    def clean(self):
        dados = super().clean()

        # A validação do documento depende do tipo escolhido no mesmo POST —
        # não dá pra fazer em clean_documento isolado (roda antes de garantir
        # que tipo_documento já foi limpo com sucesso).
        documento = dados.get("documento")
        tipo_documento = dados.get("tipo_documento") or Beneficiario.TipoDocumento.CPF
        if documento:
            try:
                validar_documento(documento, tipo_documento)
            except forms.ValidationError as exc:
                self.add_error("documento", exc)

        # Base legal "consentimento" sem o consentimento registrado é
        # tratamento sem amparo. Marcamos o momento aqui, no cadastro, que é
        # quando o funcionário confirma que colheu o aceite do titular.
        if dados.get("base_legal") == Beneficiario.BaseLegal.CONSENTIMENTO:
            if self.instance.consentimento_em is None:
                from django.utils import timezone

                self.instance.consentimento_em = timezone.now()
        return dados

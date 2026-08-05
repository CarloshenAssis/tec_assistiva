"""
Formulários do cadastro de titulares (`Beneficiario`) e de seus documentos
anexados.

`BeneficiarioForm` adapta o formulário ao tenant logado (segmento, unidades
visíveis, disponibilidade de CNPJ) e cuida das validações que dependem de
mais de um campo do POST — algo que o `Model` sozinho não valida.
"""

from django import forms

from beneficiarios.models import Beneficiario, DocumentoBeneficiario
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
    """Formulário de cadastro/edição de um titular, adaptado ao tenant do usuário logado."""

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
        """Monta o formulário, restringindo campos conforme o tenant do usuário.

        Sem `usuario` (ex.: uso fora de uma requisição autenticada), o
        formulário fica com o comportamento genérico do `ModelForm` — sem
        segmento padrão, sem restrição de unidades visíveis, oferecendo
        CPF/CNPJ por padrão.

        Args:
            usuario: O `contas.Usuario` logado, usado para descobrir o
                tenant, o segmento (padrão de `tipo_relacao`) e as unidades
                que ele pode ver. `None` desliga essas adaptações.
        """
        super().__init__(*args, **kwargs)
        self._tenant = usuario.tenant if usuario is not None else getattr(self.instance, "tenant", None)
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
        """Valida o documento conforme o tipo escolhido e marca o consentimento, se aplicável.

        Cobre duas validações que dependem de mais de um campo do mesmo
        POST, e por isso não cabem num `clean_<campo>` isolado: o formato
        do documento (que depende de `tipo_documento`) e a unicidade por
        tenant (que o `UniqueConstraint` do model só acusaria tarde, como
        `IntegrityError` na hora do `save()`).

        Returns:
            O dicionário de dados limpos, como o `clean()` padrão do
            Django.
        """
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
            else:
                # `UniqueConstraint(tenant, documento)` do model só aparece na hora
                # do `save()`, como `IntegrityError` (500) — sem isto, cadastrar um
                # documento já usado no tenant nunca vira erro de formulário.
                if self._tenant:
                    conflito = Beneficiario.objects.filter(tenant=self._tenant, documento=documento)
                    if self.instance.pk:
                        conflito = conflito.exclude(pk=self.instance.pk)
                    if conflito.exists():
                        rotulo = self._tenant.rotulo_beneficiario_singular.lower()
                        self.add_error(
                            "documento", f"Já existe um {rotulo} cadastrado com este documento."
                        )

        # Base legal "consentimento" sem o consentimento registrado é
        # tratamento sem amparo. Marcamos o momento aqui, no cadastro, que é
        # quando o funcionário confirma que colheu o aceite do titular.
        if dados.get("base_legal") == Beneficiario.BaseLegal.CONSENTIMENTO:
            if self.instance.consentimento_em is None:
                from django.utils import timezone

                self.instance.consentimento_em = timezone.now()
        return dados


class DocumentoBeneficiarioForm(forms.ModelForm):
    """Formulário de upload de um documento (RG, comprovante, laudo, receita) do titular."""

    class Meta:
        model = DocumentoBeneficiario
        fields = ["tipo", "arquivo"]

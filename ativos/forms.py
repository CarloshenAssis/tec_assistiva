from django import forms

from ativos.models import Ativo, CategoriaAtivo, FotoAtivo, SubcategoriaAtivo
from core.models import Fornecedor, Unidade

CHECKLIST_ITENS_EMPRESTIMO = [
    ("rodas", "Rodas boas"),
    ("freios", "Freios funcionando"),
    ("apoio_braco", "Apoio de braço"),
    ("apoio_pe", "Apoio de pé"),
    ("ferrugem", "Sem ferrugem"),
    ("higienizado", "Higienizado"),
    ("termo_impresso", "Termo impresso"),
    ("termo_assinado", "Termo assinado fisicamente pelo beneficiário"),
]

CHECKLIST_ITENS_DEVOLUCAO = [
    ("estado", "Estado igual à retirada"),
    ("limpa", "Limpa"),
    ("funcionando", "Funcionando"),
]


class AtivoForm(forms.ModelForm):
    """
    `patrimonio` fica opcional no formulário (o model exige, mas o form
    relaxa): em branco, a view gera o código automaticamente
    (`ativos.patrimonio.gerar_codigo_patrimonial`) — o usuário só digita
    quando já tem um patrimônio próprio (docs/features/identificacao-
    patrimonial-e-unidades.md). A validação de unicidade do código digitado
    manualmente é feita aqui, não deixada para o `IntegrityError` do banco.
    """

    class Meta:
        model = Ativo
        fields = [
            "patrimonio",
            "categoria",
            "subcategoria",
            "modelo",
            "fabricante",
            "numero_serie",
            "unidade",
            "fornecedor",
            "data_aquisicao",
            "vida_util_meses",
            "observacoes",
        ]
        widgets = {
            "data_aquisicao": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Os querysets já vêm filtrados pelo tenant corrente via TenantManager
        # (contas.middleware.TenantMiddleware) — não precisamos filtrar aqui.
        self.fields["categoria"].queryset = CategoriaAtivo.objects.all()
        self.fields["subcategoria"].queryset = SubcategoriaAtivo.objects.all()
        self.fields["unidade"].queryset = Unidade.objects.all()
        self.fields["fornecedor"].queryset = Fornecedor.objects.all()
        self.fields["subcategoria"].required = False
        self.fields["unidade"].required = False
        self.fields["fornecedor"].required = False
        self.fields["patrimonio"].required = False
        self.fields["patrimonio"].help_text = "Deixe em branco para gerar automaticamente."

    def clean_patrimonio(self):
        patrimonio = self.cleaned_data.get("patrimonio", "").strip()
        if not patrimonio:
            return patrimonio
        conflito = Ativo.objects.filter(patrimonio__iexact=patrimonio)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise forms.ValidationError("Já existe um ativo com este código patrimonial.")
        return patrimonio


class FotoAtivoForm(forms.ModelForm):
    class Meta:
        model = FotoAtivo
        fields = ["tipo", "arquivo"]


class EnviarManutencaoForm(forms.Form):
    motivo = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 2}))
    fornecedor = forms.ModelChoiceField(queryset=Fornecedor.objects.none(), required=False, label="Fornecedor")
    valor = forms.DecimalField(required=False, label="Valor (R$)", max_digits=10, decimal_places=2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fornecedor"].queryset = Fornecedor.objects.all()


class DarBaixaForm(forms.Form):
    motivo = forms.CharField(label="Motivo da baixa", widget=forms.Textarea(attrs={"rows": 2}))


class RenovarForm(forms.Form):
    novo_prazo_dias = forms.IntegerField(label="Novo prazo (dias)", min_value=1, initial=30)


class ObservacaoForm(forms.Form):
    observacoes = forms.CharField(
        label="Observações", widget=forms.Textarea(attrs={"rows": 2}), required=False
    )

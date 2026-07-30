from django import forms
from django.db.models import Q

from ativos.models import Ativo, CategoriaAtivo, FotoAtivo, LayoutEtiqueta, SubcategoriaAtivo
from core.models import Fornecedor, Unidade
from core.unidades import filtrar_por_unidade, unidades_visiveis

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

    def __init__(self, *args, tenant=None, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Os querysets já vêm filtrados pelo tenant corrente via TenantManager
        # (contas.middleware.TenantMiddleware) — não precisamos filtrar aqui.
        self.fields["categoria"].queryset = CategoriaAtivo.objects.all()
        self.fields["subcategoria"].queryset = SubcategoriaAtivo.objects.all()
        self.fields["fornecedor"].queryset = Fornecedor.objects.all()
        self.fields["subcategoria"].required = False
        self.fields["fornecedor"].required = False
        self.fields["patrimonio"].required = False
        self.fields["patrimonio"].help_text = "Deixe em branco para gerar automaticamente."

        # Unidade é obrigatória (docs/business-rules/unidades.md) e restrita
        # às unidades que o usuário pode operar: um Gestor não deve conseguir
        # cadastrar um ativo dentro de uma unidade que ele nem enxerga na
        # listagem depois. Unidades desativadas não aparecem — mas a unidade
        # já gravada no ativo continua na lista, senão editar qualquer outro
        # campo de um ativo de unidade desativada ficaria impossível.
        unidades = Unidade.objects.filter(ativo=True)
        if usuario is not None:
            unidades = filtrar_por_unidade(unidades, usuario, campo="pk")
        if self.instance.pk and self.instance.unidade_id:
            unidades = Unidade.objects.filter(
                Q(pk__in=unidades.values("pk")) | Q(pk=self.instance.unidade_id)
            )
        self.fields["unidade"].queryset = unidades.order_by("nome")
        self.fields["unidade"].required = True
        self.fields["unidade"].empty_label = "Selecione a unidade responsável"

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


class JustificativaForm(forms.Form):
    """
    Como `ObservacaoForm`, mas com a justificativa OBRIGATÓRIA.

    Usado em ações que tiram o ativo de circulação sem que ninguém o tenha
    devolvido (extravio): "por que este ativo desapareceu" é a única
    informação que o registro tem para oferecer depois, então deixá-la
    opcional esvazia o registro.
    """

    observacoes = forms.CharField(
        label="Justificativa",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Descreva o que se sabe sobre o ocorrido — é o que o histórico vai guardar.",
    )


class EditarManutencaoForm(forms.Form):
    """Correção dos dados da manutenção em curso (ver ativos.services.editar_manutencao)."""

    motivo = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 2}))
    fornecedor = forms.ModelChoiceField(
        queryset=Fornecedor.objects.none(), required=False, label="Fornecedor"
    )
    valor = forms.DecimalField(required=False, label="Valor (R$)", max_digits=10, decimal_places=2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fornecedor"].queryset = Fornecedor.objects.all()


class TransferirUnidadeForm(forms.Form):
    """
    Transferência do ativo para outra unidade (docs/business-rules/unidades.md).

    O destino lista TODAS as unidades ativas do tenant, não só as que o
    usuário enxerga: enviar equipamento para uma unidade que você não
    administra é uma operação legítima e frequente (a matriz remaneja para
    uma filial). O contrapeso é a justificativa obrigatória — depois da
    transferência o ativo sai da visão de quem o transferiu, e o histórico
    precisa dizer por quê.
    """

    unidade_destino = forms.ModelChoiceField(
        queryset=Unidade.objects.none(),
        label="Unidade de destino",
        empty_label="Selecione a unidade de destino",
    )
    observacoes = forms.CharField(
        label="Motivo da transferência",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Obrigatório: o ativo sai da visão da unidade de origem após a transferência.",
    )

    def __init__(self, *args, ativo=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Unidade.objects.filter(ativo=True)
        if ativo is not None and ativo.unidade_id:
            queryset = queryset.exclude(pk=ativo.unidade_id)
        self.fields["unidade_destino"].queryset = queryset.order_by("nome")


class FiltroEtiquetasForm(forms.Form):
    """
    Filtros do Centro de Etiquetas. Todos opcionais — sem filtro nenhum, a
    tela lista os ativos do escopo do usuário.
    """

    categoria = forms.ModelChoiceField(
        queryset=CategoriaAtivo.objects.none(), required=False, label="Categoria", empty_label="Todas"
    )
    unidade = forms.ModelChoiceField(
        queryset=Unidade.objects.none(), required=False, label="Unidade", empty_label="Todas"
    )
    status = forms.ChoiceField(required=False, label="Status", choices=[])
    somente_sem_etiqueta = forms.BooleanField(
        required=False,
        label="Somente ativos sem etiqueta impressa",
        help_text="É a fila de impressão: todo ativo recém-cadastrado aparece aqui até ter a primeira etiqueta emitida.",
    )
    #: `layout` não é filtro: é parâmetro do POST que gera a folha. Está neste
    #: form só para a tela renderizar o `<select>` com as opções certas sem
    #: repetir a lista no template. Por isso `required=False` — o campo é
    #: enviado no POST de impressão, não no GET dos filtros, e exigi-lo aqui
    #: invalidaria silenciosamente TODO filtro aplicado (foi o que aconteceu:
    #: o form ficava inválido e a tela ignorava categoria/status/unidade).
    #: A validação do valor acontece na view que gera a folha.
    layout = forms.ChoiceField(
        choices=LayoutEtiqueta.choices,
        initial=LayoutEtiqueta.MEDIO,
        required=False,
        label="Tamanho da etiqueta",
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        from ativos.domain.enums import StatusAtivo

        self.fields["categoria"].queryset = CategoriaAtivo.objects.order_by("nome")
        unidades = unidades_visiveis(usuario) if usuario is not None else Unidade.objects.all()
        self.fields["unidade"].queryset = unidades.order_by("nome")
        self.fields["status"].choices = [("", "Todos")] + [
            (status.value, status.rotulo) for status in StatusAtivo
        ]


class CategoriaAtivoForm(forms.ModelForm):
    """
    Mesmo motivo do `clean_nome` de `core.forms.UnidadeForm`: a instância só
    recebe `tenant` depois de `is_valid()` (a view faz `commit=False`), então
    a validação automática de `UniqueConstraint(tenant, nome)` do Django
    ainda não vê o tenant e não pega o conflito — sem isto, cadastrar uma
    categoria com nome já usado no tenant vira `IntegrityError` (500) em vez
    de erro de formulário.
    """

    class Meta:
        model = CategoriaAtivo
        fields = ["nome", "prefixo"]

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant or getattr(self.instance, "tenant", None)

    def clean_nome(self):
        nome = self.cleaned_data["nome"].strip()
        conflito = CategoriaAtivo.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if self._tenant and conflito.exists():
            raise forms.ValidationError("Já existe uma categoria com este nome.")
        return nome


class SubcategoriaAtivoForm(forms.ModelForm):
    """
    Mesmo motivo do `clean_nome` de `CategoriaAtivoForm` acima, mas a
    unicidade de `SubcategoriaAtivo` é por categoria (`UniqueConstraint
    (categoria, nome)`), não por tenant — daí `categoria` explícito no
    `__init__` em vez de `tenant`.
    """

    class Meta:
        model = SubcategoriaAtivo
        fields = ["nome"]

    def __init__(self, *args, categoria=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._categoria = categoria or getattr(self.instance, "categoria", None)

    def clean_nome(self):
        nome = self.cleaned_data["nome"].strip()
        conflito = SubcategoriaAtivo.objects.filter(nome__iexact=nome, categoria=self._categoria)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if self._categoria and conflito.exists():
            raise forms.ValidationError("Já existe uma subcategoria com este nome nesta categoria.")
        return nome

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from beneficiarios.forms import BeneficiarioForm
from beneficiarios.models import Beneficiario
from core.decorators import tenant_required


@tenant_required
def lista(request):
    busca = request.GET.get("q", "").strip()
    qs = Beneficiario.objects.all()
    if busca:
        qs = qs.filter(Q(nome__icontains=busca) | Q(cpf__icontains=busca) | Q(telefone__icontains=busca))
    return render(
        request,
        "beneficiarios/lista.html",
        {"nav_atual": "beneficiarios", "beneficiarios": qs[:200], "busca": busca},
    )


@tenant_required
def criar(request):
    if request.method == "POST":
        form = BeneficiarioForm(request.POST)
        if form.is_valid():
            beneficiario = form.save(commit=False)
            beneficiario.tenant = request.tenant
            beneficiario.save()
            messages.success(request, f"Beneficiário {beneficiario.nome} cadastrado com sucesso.")
            return redirect("app:beneficiarios:ficha", pk=beneficiario.pk)
    else:
        form = BeneficiarioForm()
    return render(
        request, "beneficiarios/form.html", {"nav_atual": "beneficiarios", "form": form, "titulo": "Novo Beneficiário"}
    )


@tenant_required
def ficha(request, pk):
    beneficiario = get_object_or_404(Beneficiario, pk=pk)
    emprestimos = beneficiario.emprestimos.select_related("movimentacao", "movimentacao__ativo").order_by(
        "-movimentacao__data_hora"
    )
    return render(
        request,
        "beneficiarios/ficha.html",
        {"nav_atual": "beneficiarios", "beneficiario": beneficiario, "emprestimos": emprestimos},
    )

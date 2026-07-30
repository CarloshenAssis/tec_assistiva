"""
Popula o catálogo fixo de Módulos/feature flags (docs/business-rules/modulos.md).

Mesmo padrão de `contas/migrations/0002_seed_papeis.py`: o catálogo em si
(quais módulos existem) é decisão de produto, não dado de cliente — migration
de dados, não tela de cadastro. A ativação por tenant (`TenantModulo`) essa
sim é operação do Owner, feita pela tela.
"""

from django.db import migrations

MODULOS = [
    {
        "codigo": "locacao_financeiro",
        "nome": "Locação financeira",
        "descricao": (
            "Valor diário, caução e multa por atraso no empréstimo/locação de "
            "um ativo. Ligado por padrão para o segmento Locadora."
        ),
    },
    {
        "codigo": "documento_pessoa_juridica",
        "nome": "Cliente pessoa jurídica",
        "descricao": (
            "Permite cadastrar o titular com CNPJ, além de CPF. Ligado por "
            "padrão para o segmento Locadora."
        ),
    },
]


def criar_modulos(apps, schema_editor):
    Modulo = apps.get_model("core", "Modulo")
    for dados in MODULOS:
        Modulo.objects.get_or_create(codigo=dados["codigo"], defaults=dados)


def remover_modulos(apps, schema_editor):
    Modulo = apps.get_model("core", "Modulo")
    Modulo.objects.filter(codigo__in=[m["codigo"] for m in MODULOS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_modulos_por_tenant"),
    ]

    operations = [
        migrations.RunPython(criar_modulos, remover_modulos),
    ]

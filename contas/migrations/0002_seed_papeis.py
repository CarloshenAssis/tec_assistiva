"""
Popula o catálogo fixo de Papéis (Admin/Gestor/Funcionário).

Ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3.2 — a hierarquia é a mesma
para todos os tenants nesta fase (não é customizável por cliente), por
isso é uma migration de dados, não uma tela de cadastro.
"""

from django.db import migrations

PAPEIS = [
    {"codigo": "admin", "nome": "Administrador", "nivel_hierarquico": 30},
    {"codigo": "gestor", "nome": "Gestor", "nivel_hierarquico": 20},
    {"codigo": "funcionario", "nome": "Funcionário", "nivel_hierarquico": 10},
]


def criar_papeis(apps, schema_editor):
    Papel = apps.get_model("contas", "Papel")
    for dados in PAPEIS:
        Papel.objects.get_or_create(codigo=dados["codigo"], defaults=dados)


def remover_papeis(apps, schema_editor):
    Papel = apps.get_model("contas", "Papel")
    Papel.objects.filter(codigo__in=[p["codigo"] for p in PAPEIS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_papeis, remover_papeis),
    ]

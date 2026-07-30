"""
Generaliza `cpf` para `documento` (CPF ou CNPJ) — docs/business-rules/modulos.md.

Escrita à mão (em vez de `makemigrations`) para preservar os dados via
`RenameField` em vez de remover+recriar a coluna, que apagaria todo CPF já
cadastrado.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("beneficiarios", "0004_beneficiario_unidade"),
    ]

    operations = [
        migrations.RenameField(
            model_name="beneficiario",
            old_name="cpf",
            new_name="documento",
        ),
        migrations.RemoveConstraint(
            model_name="beneficiario",
            name="beneficiario_cpf_unico_por_tenant",
        ),
        migrations.AlterField(
            model_name="beneficiario",
            name="documento",
            field=models.CharField(max_length=18),
        ),
        migrations.AddField(
            model_name="beneficiario",
            name="tipo_documento",
            field=models.CharField(
                choices=[("cpf", "CPF"), ("cnpj", "CNPJ")], default="cpf", max_length=4
            ),
        ),
        migrations.AddConstraint(
            model_name="beneficiario",
            constraint=models.UniqueConstraint(
                fields=["tenant", "documento"], name="beneficiario_documento_unico_por_tenant"
            ),
        ),
    ]

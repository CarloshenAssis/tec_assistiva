"""
Popula o módulo `documentos_beneficiario` no catálogo (docs/business-rules/modulos.md).

Mesmo padrão de `0004_seed_modulos.py`: nasce desligado para todo tenant
(nenhum segmento entra em `_MODULOS_PADRAO_POR_SEGMENTO` para este código)
— o Owner liga por tenant sob pedido.
"""

from django.db import migrations

MODULO = {
    "codigo": "documentos_beneficiario",
    "nome": "Upload de documento do titular",
    "descricao": (
        "Permite anexar documentos (RG, comprovante de residência, laudo, "
        "receita médica) à ficha do titular. Opcional — desligado por "
        "padrão para todo segmento até o Owner ligar para um tenant."
    ),
}


def criar_modulo(apps, schema_editor):
    Modulo = apps.get_model("core", "Modulo")
    Modulo.objects.get_or_create(codigo=MODULO["codigo"], defaults=MODULO)


def remover_modulo(apps, schema_editor):
    Modulo = apps.get_model("core", "Modulo")
    Modulo.objects.filter(codigo=MODULO["codigo"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_tenant_logo"),
    ]

    operations = [
        migrations.RunPython(criar_modulo, remover_modulo),
    ]

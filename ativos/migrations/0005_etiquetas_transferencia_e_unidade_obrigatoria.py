"""
Centro de Etiquetas, separação do tipo `recuperacao` e unidade obrigatória
no Ativo (docs/business-rules/etiquetas.md e unidades.md).

Escrita à mão porque a passagem de `Ativo.unidade` para NOT NULL exige um
backfill entre a criação da estrutura e a restrição: rodar o `AlterField`
antes de preencher os nulos derrubaria a migration em qualquer base que já
tenha ativo sem unidade — o que inclui a produção.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models


def criar_unidade_padrao_e_vincular(apps, schema_editor):
    """
    Garante uma unidade para todo ativo que estiver sem.

    Cria "Unidade Principal" apenas nos tenants que precisam (têm ativo com
    `unidade` nula) e reaproveita a única unidade existente quando o tenant já
    tem exatamente uma — nesse caso não há ambiguidade sobre onde o ativo
    está, e criar uma segunda unidade só para o backfill deixaria lixo no
    cadastro do cliente.
    """
    Ativo = apps.get_model("ativos", "Ativo")
    Unidade = apps.get_model("core", "Unidade")

    tenants_com_orfaos = (
        Ativo.objects.filter(unidade__isnull=True)
        .values_list("tenant_id", flat=True)
        .distinct()
    )

    for tenant_id in tenants_com_orfaos:
        unidades = list(Unidade.objects.filter(tenant_id=tenant_id)[:2])
        if len(unidades) == 1:
            destino = unidades[0]
        else:
            destino, _ = Unidade.objects.get_or_create(
                tenant_id=tenant_id,
                nome="Unidade Principal",
                defaults={
                    "tipo": "Matriz",
                    "observacoes": (
                        "Criada automaticamente na migração que tornou a unidade "
                        "obrigatória nos ativos. Renomeie ou redistribua os ativos "
                        "conforme a operação real."
                    ),
                },
            )
        Ativo.objects.filter(tenant_id=tenant_id, unidade__isnull=True).update(unidade=destino)


def reverter_vinculo(apps, schema_editor):
    """
    Nada a desfazer: as unidades criadas ficam (apagá-las exigiria decidir para
    onde mandar os ativos, o oposto do que esta migration garante), e o vínculo
    volta a ser opcional pela reversão do AlterField.
    """


def reclassificar_recuperacoes(apps, schema_editor):
    """
    `transferencia` significava duas coisas: recuperação de ativo extraviado e
    (na intenção) mudança de unidade. Os registros de recuperação são
    identificáveis sem ambiguidade — saíram de `extraviado` para `disponivel` —
    e passam para o tipo próprio, liberando `transferencia` para o significado
    do nome.
    """
    Movimentacao = apps.get_model("ativos", "Movimentacao")
    Movimentacao.objects.filter(
        tipo="transferencia", status_anterior="extraviado", status_novo="disponivel"
    ).update(tipo="recuperacao")


def desfazer_reclassificacao(apps, schema_editor):
    Movimentacao = apps.get_model("ativos", "Movimentacao")
    Movimentacao.objects.filter(tipo="recuperacao").update(tipo="transferencia")


class Migration(migrations.Migration):
    dependencies = [
        ("ativos", "0004_categoriaativo_prefixo"),
        ("contas", "0003_usuario_unidades"),
        ("core", "0002_unidade_cidade_unidade_email_unidade_observacoes_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImpressaoEtiqueta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "layout",
                    models.CharField(
                        choices=[
                            ("pequeno", "Pequeno — 33×22 mm (só QR + patrimônio)"),
                            ("medio", "Médio — 50×30 mm (QR + patrimônio + categoria)"),
                            ("grande", "Grande — 80×50 mm (QR + patrimônio + categoria + instituição)"),
                        ],
                        max_length=10,
                    ),
                ),
                ("impresso_em", models.DateTimeField(auto_now_add=True)),
                ("lote", models.UUIDField(default=uuid.uuid4, editable=False)),
                (
                    "ativo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="impressoes",
                        to="ativos.ativo",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="core.tenant",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="impressoes_etiqueta",
                        to="contas.usuario",
                    ),
                ),
            ],
            options={
                "verbose_name": "Impressão de Etiqueta",
                "verbose_name_plural": "Impressões de Etiqueta",
                "ordering": ["-impresso_em"],
            },
        ),
        migrations.AddIndex(
            model_name="impressaoetiqueta",
            index=models.Index(fields=["tenant", "lote"], name="ativos_impr_tenant__69a77f_idx"),
        ),
        migrations.AlterField(
            model_name="movimentacao",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("emprestimo", "Empréstimo"),
                    ("devolucao", "Devolução"),
                    ("renovacao", "Renovação"),
                    ("transferencia", "Transferência entre Unidades"),
                    ("reserva", "Reserva"),
                    ("manutencao", "Manutenção"),
                    ("retorno_manutencao", "Retorno de Manutenção"),
                    ("higienizacao", "Higienização"),
                    ("baixa", "Baixa Patrimonial"),
                    ("extravio", "Extravio"),
                    ("recuperacao", "Recuperação de Extravio"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(reclassificar_recuperacoes, desfazer_reclassificacao),
        # Preenche os nulos ANTES de restringir o campo.
        migrations.RunPython(criar_unidade_padrao_e_vincular, reverter_vinculo),
        migrations.AlterField(
            model_name="ativo",
            name="unidade",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ativos",
                to="core.unidade",
            ),
        ),
    ]

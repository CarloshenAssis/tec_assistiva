"""
Popula um tenant de demonstração para testes manuais e smoke tests do
frontend (Fase 1). Idempotente: pode ser rodado várias vezes.

    python manage.py seed_demo
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from ativos.models import Ativo, CategoriaAtivo
from beneficiarios.models import Beneficiario
from contas.models import Papel, Usuario
from core.models import Tenant, Unidade
from core.tenancy import reset_current_tenant_id, set_current_tenant_id
from notificacoes.models import NotificacaoTemplate

TEMPLATES_PADRAO = [
    (
        NotificacaoTemplate.Tipo.CONFIRMACAO_EMPRESTIMO,
        "Empréstimo realizado",
        "Olá {beneficiario}!\n\nSeu empréstimo foi registrado.\n\nAtivo: {ativo}\nCódigo: {codigo}\n\n"
        "Devolução prevista: {data_prevista}",
    ),
    (
        NotificacaoTemplate.Tipo.AVISO_7_DIAS,
        "7 dias antes do vencimento",
        "Olá {beneficiario}!\n\nFaltam 7 dias para o vencimento do empréstimo de {ativo} ({codigo}).\n\n"
        "Se ainda precisar do item, entre em contato para solicitar renovação.",
    ),
    (
        NotificacaoTemplate.Tipo.VENCIMENTO,
        "No vencimento",
        "Olá {beneficiario}!\n\nHoje vence o empréstimo de {ativo} ({codigo}).\n\n"
        "Se já devolveu, desconsidere esta mensagem.",
    ),
    (
        NotificacaoTemplate.Tipo.ATRASO,
        "Em atraso",
        "Olá {beneficiario}!\n\nSeu empréstimo de {ativo} ({codigo}) está em atraso há {dias} dia(s).\n\n"
        "Entre em contato para regularização.",
    ),
]


class Command(BaseCommand):
    help = "Cria um tenant de demonstração com usuários, categorias, ativos e beneficiários."

    @transaction.atomic
    def handle(self, *args, **options):
        tenant, criado = Tenant.objects.get_or_create(
            slug="demo",
            defaults={
                "nome": "Prefeitura Demo",
                "segmento": Tenant.Segmento.FUNDO_SOCIAL,
                "cidade": "São José dos Campos",
                "uf": "SP",
            },
        )

        token = set_current_tenant_id(tenant.pk)
        try:
            unidade, _ = Unidade.objects.get_or_create(tenant=tenant, nome="Centro")

            admin_papel = Papel.objects.get(codigo="admin")
            gestor_papel = Papel.objects.get(codigo="gestor")
            funcionario_papel = Papel.objects.get(codigo="funcionario")

            self._criar_usuario("admin_demo", tenant, admin_papel, is_superuser=False)
            self._criar_usuario("gestor_demo", tenant, gestor_papel)
            self._criar_usuario("func_demo", tenant, funcionario_papel)

            categorias = {}
            for nome in ["Cadeira de Rodas", "Muletas", "Andador", "Cadeira de Banho"]:
                categorias[nome], _ = CategoriaAtivo.objects.get_or_create(tenant=tenant, nome=nome)

            ativos_seed = [
                ("CAD-0001", "Cadeira de Rodas", "Ortobras", "Confort 12x"),
                ("CAD-0002", "Cadeira de Rodas", "Jaguaribe", "Standard"),
                ("MUL-0011", "Muletas", "Ortopé", "Axilar Alumínio"),
                ("AND-0021", "Andador", "Mobilator", "4 Rodas"),
                ("CB-0031", "Cadeira de Banho", "Dellamed", "Standard"),
            ]
            for patrimonio, categoria_nome, fabricante, modelo in ativos_seed:
                Ativo.objects.get_or_create(
                    tenant=tenant,
                    patrimonio=patrimonio,
                    defaults={
                        "categoria": categorias[categoria_nome],
                        "fabricante": fabricante,
                        "modelo": modelo,
                        "unidade": unidade,
                    },
                )

            beneficiarios_seed = [
                ("Maria Silva", "123.456.789-00", "São José dos Campos", "Jardim Satélite", "(12) 99811-2233"),
                ("João Pedro", "234.567.891-00", "São José dos Campos", "Jardim Aquarius", "(12) 99722-3344"),
            ]
            for nome, cpf, cidade, bairro, whatsapp in beneficiarios_seed:
                Beneficiario.objects.get_or_create(
                    tenant=tenant,
                    cpf=cpf,
                    defaults={"nome": nome, "cidade": cidade, "bairro": bairro, "whatsapp": whatsapp},
                )

            for tipo, titulo, corpo in TEMPLATES_PADRAO:
                NotificacaoTemplate.objects.get_or_create(
                    tenant=tenant, tipo=tipo, defaults={"titulo": titulo, "corpo_texto": corpo}
                )
        finally:
            reset_current_tenant_id(token)

        self.stdout.write(self.style.SUCCESS(
            f"Tenant '{tenant.nome}' (slug={tenant.slug}) pronto. "
            f"Usuários: admin_demo / gestor_demo / func_demo (senha: demo12345)."
        ))

    def _criar_usuario(self, username, tenant, papel, is_superuser=False):
        if Usuario.objects.filter(username=username).exists():
            return
        Usuario.objects.create_user(
            username=username, password="demo12345", tenant=tenant, papel=papel
        )

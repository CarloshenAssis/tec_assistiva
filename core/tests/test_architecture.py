"""
Teste de arquitetura: garante que o acesso cross-tenant (`all_tenants()`)
só aparece nos lugares explicitamente auditados como exceção.

Ver docs/PLANO_EVOLUCAO_SAAS_CICLARTECH.md §3.1 — essa é a barreira técnica
que impede um bug "de boa vontade" de vazar dado entre tenants: o uso de
`all_tenants()` fora do app `owner` (ou do mixin de admin que o
implementa de forma controlada) deve falhar o CI, não passar em code review
por descuido.
"""

from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Arquivos onde `all_tenants()` é uso intencional e já revisado:
# - core/admin.py: implementa o TenantScopedAdmin (mixin usado por todo
#   Django Admin do produto), que precisa enxergar todos os tenants para
#   depois filtrar explicitamente pelo tenant do usuário logado.
# - qualquer arquivo dentro do app `owner`: é a área de plataforma,
#   cross-tenant por definição.
ARQUIVOS_PERMITIDOS = {
    BASE_DIR / "core" / "admin.py",
    # Apenas menciona o método em docstring/comentário explicativo, não o chama.
    BASE_DIR / "core" / "tenancy.py",
    BASE_DIR / "core" / "models.py",
}
DIRETORIOS_PERMITIDOS = {
    BASE_DIR / "owner",
}

APPS_DE_DOMINIO = [
    "core",
    "contas",
    "ativos",
    "beneficiarios",
    "notificacoes",
    "auditoria",
    "owner",
]


class UsoDeAllTenantsRestritoTest(SimpleTestCase):
    def test_all_tenants_so_aparece_em_locais_auditados(self):
        ocorrencias_nao_autorizadas = []

        for app_nome in APPS_DE_DOMINIO:
            app_dir = BASE_DIR / app_nome
            if not app_dir.exists():
                continue
            for py_file in app_dir.rglob("*.py"):
                if py_file in ARQUIVOS_PERMITIDOS:
                    continue
                if any(
                    permitido in py_file.parents or permitido == py_file
                    for permitido in DIRETORIOS_PERMITIDOS
                ):
                    continue
                if "test" in py_file.name:
                    # Os próprios testes de isolamento chamam all_tenants()
                    # deliberadamente para montar o cenário de verificação.
                    continue
                conteudo = py_file.read_text(encoding="utf-8")
                if ".all_tenants(" in conteudo:
                    ocorrencias_nao_autorizadas.append(str(py_file))

        self.assertEqual(
            [],
            ocorrencias_nao_autorizadas,
            "Uso de `.all_tenants()` encontrado fora dos locais auditados. "
            "Esse método existe apenas para o app `owner` e para o "
            "TenantScopedAdmin (core/admin.py). Se este uso é intencional, "
            "adicione o arquivo à lista ARQUIVOS_PERMITIDOS acima após revisão.",
        )

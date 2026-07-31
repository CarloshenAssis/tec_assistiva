"""
Backend de mídia: Supabase Storage (S3) quando configurado, disco local
como fallback de desenvolvimento.

Testado via subprocess porque STORAGES é resolvido na primeira importação
de settings — mudar env vars depois do processo já ter carregado Django
não teria efeito nenhum aqui.
"""

import subprocess
import sys

from django.test import SimpleTestCase

_SCRIPT_S3 = """
import django, os
os.environ["DJANGO_SETTINGS_MODULE"] = "ciclartech.settings"
os.environ["DJANGO_STORAGE_S3_ACCESS_KEY_ID"] = "chave-de-teste"
os.environ["DJANGO_STORAGE_S3_SECRET_ACCESS_KEY"] = "segredo-de-teste"
os.environ["DJANGO_STORAGE_S3_ENDPOINT_URL"] = "https://projeto-de-teste.storage.supabase.co/storage/v1/s3"
os.environ["DJANGO_STORAGE_S3_BUCKET_NAME"] = "bucket-de-teste"
django.setup()
from django.core.files.storage import storages
from django.conf import settings
s = storages["default"]
print(type(s).__name__)
print(s.bucket_name)
print(settings.MEDIA_STORAGE_HOST)
"""

_SCRIPT_SEM_S3 = """
import django, os
os.environ["DJANGO_SETTINGS_MODULE"] = "ciclartech.settings"
os.environ.pop("DJANGO_STORAGE_S3_ACCESS_KEY_ID", None)
os.environ.pop("DJANGO_STORAGE_S3_SECRET_ACCESS_KEY", None)
django.setup()
from django.core.files.storage import storages
from django.conf import settings
s = storages["default"]
print(type(s).__name__)
print(settings.MEDIA_STORAGE_HOST)
"""

#: Chaves S3 presentes mas SEM endpoint/bucket — antes desta correção, o
#: settings.py caía silenciosamente para o endpoint/bucket de produção
#: (`tuqecavtmbkriwhnqzfu`) em vez de recusar subir. Ver README, seção
#: "Storage de mídia".
_SCRIPT_S3_SEM_ENDPOINT = """
import django, os
os.environ["DJANGO_SETTINGS_MODULE"] = "ciclartech.settings"
os.environ["DJANGO_STORAGE_S3_ACCESS_KEY_ID"] = "chave-de-teste"
os.environ["DJANGO_STORAGE_S3_SECRET_ACCESS_KEY"] = "segredo-de-teste"
os.environ.pop("DJANGO_STORAGE_S3_ENDPOINT_URL", None)
os.environ.pop("DJANGO_STORAGE_S3_BUCKET_NAME", None)
django.setup()
"""


class BackendDeMidiaTest(SimpleTestCase):
    def _rodar(self, script: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
        )

    def _rodar_com_sucesso(self, script: str) -> str:
        resultado = self._rodar(script)
        self.assertEqual(0, resultado.returncode, resultado.stderr)
        return resultado.stdout

    def test_com_credenciais_usa_s3storage(self):
        saida = self._rodar_com_sucesso(_SCRIPT_S3).splitlines()
        self.assertEqual("S3Storage", saida[0])
        self.assertEqual("bucket-de-teste", saida[1])

    def test_com_credenciais_expoe_o_host_para_a_csp(self):
        saida = self._rodar_com_sucesso(_SCRIPT_S3).splitlines()
        self.assertEqual("projeto-de-teste.storage.supabase.co", saida[2])

    def test_sem_credenciais_cai_para_disco_local(self):
        saida = self._rodar_com_sucesso(_SCRIPT_SEM_S3).splitlines()
        self.assertEqual("FileSystemStorage", saida[0])
        self.assertEqual("None", saida[1])

    def test_chaves_sem_endpoint_ou_bucket_recusa_subir(self):
        # É o próprio ponto da correção: sem isto, a aplicação subiria
        # silenciosamente apontando para o bucket de produção.
        resultado = self._rodar(_SCRIPT_S3_SEM_ENDPOINT)
        self.assertNotEqual(0, resultado.returncode)
        self.assertIn("ImproperlyConfigured", resultado.stderr)
        self.assertIn("DJANGO_STORAGE_S3_ENDPOINT_URL", resultado.stderr)

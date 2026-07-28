"""
Entrypoint WSGI para o runtime Python da Vercel (@vercel/python).

Django expõe `application` em ciclartech/wsgi.py; a Vercel espera
encontrar um objeto chamado `app` no arquivo apontado por `vercel.json`.
Este arquivo só faz esse alias — nenhuma lógica adicional aqui.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ciclartech.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()

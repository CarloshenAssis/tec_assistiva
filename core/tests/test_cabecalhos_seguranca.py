"""
Cabeçalhos de segurança aplicados à resposta.

A CSP é a rede de proteção contra XSS armazenado: mesmo que uma injeção
escape da validação de entrada e da escapagem de template, o navegador se
recusa a executar o script.
"""

from django.test import TestCase
from django.urls import reverse

from contas.models import Papel, Usuario
from core.models import Tenant

SENHA = "senha-bem-longa-2026"


class CabecalhosTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Prefeitura Z", slug="pref-hdr")
        Usuario.objects.create_user(
            username="func_hdr",
            password=SENHA,
            tenant=self.tenant,
            papel=Papel.objects.get(codigo="funcionario"),
        )

    def test_csp_presente_na_tela_de_login(self):
        resposta = self.client.get(reverse("login"))
        self.assertIn("Content-Security-Policy", resposta)

    def test_csp_proibe_script_inline(self):
        """
        Sem `'unsafe-inline'` em script-src, `<script>` injetado em um campo
        de texto não executa. É o que transforma um XSS armazenado em um
        defeito visual em vez de um roubo de sessão.
        """
        resposta = self.client.get(reverse("login"))
        csp = resposta["Content-Security-Policy"]
        script_src = next(d for d in csp.split(";") if d.strip().startswith("script-src"))
        self.assertNotIn("unsafe-inline", script_src)
        self.assertNotIn("unsafe-eval", script_src)

    def test_csp_bloqueia_embutir_em_iframe_de_terceiro(self):
        resposta = self.client.get(reverse("login"))
        self.assertIn("frame-ancestors 'none'", resposta["Content-Security-Policy"])

    def test_csp_impede_envio_de_formulario_para_fora(self):
        resposta = self.client.get(reverse("login"))
        self.assertIn("form-action 'self'", resposta["Content-Security-Policy"])

    def test_csp_bloqueia_reescrita_de_base_href(self):
        resposta = self.client.get(reverse("login"))
        self.assertIn("base-uri 'self'", resposta["Content-Security-Policy"])

    def test_permissions_policy_desliga_microfone_e_geolocalizacao(self):
        resposta = self.client.get(reverse("login"))
        politica = resposta["Permissions-Policy"]
        self.assertIn("microphone=()", politica)
        self.assertIn("geolocation=()", politica)

    def test_nosniff_aplicado(self):
        resposta = self.client.get(reverse("login"))
        self.assertEqual("nosniff", resposta["X-Content-Type-Options"])

    def test_clickjacking_bloqueado(self):
        resposta = self.client.get(reverse("login"))
        self.assertEqual("DENY", resposta["X-Frame-Options"])

    def test_pagina_autenticada_nao_vai_para_cache(self):
        """
        Em terminal compartilhado, o botão "voltar" depois do logout não pode
        reexibir a ficha do paciente anterior.
        """
        self.client.login(username="func_hdr", password=SENHA)
        resposta = self.client.get(reverse("app:dashboard"))
        self.assertIn("no-store", resposta["Cache-Control"])


class CspImgSrcStorageExternoTest(TestCase):
    """
    `img-src` precisa liberar o host do storage de mídia quando configurado
    — senão a foto de equipamento (servida via URL assinada do Supabase,
    outra origem) seria bloqueada pelo próprio navegador.
    """

    def test_sem_storage_externo_configurado_nao_libera_host_nenhum(self):
        resposta = self.client.get(reverse("login"))
        csp = resposta["Content-Security-Policy"]
        img_src = next(d for d in csp.split(";") if d.strip().startswith("img-src"))
        self.assertEqual("img-src 'self' data:", img_src.strip())

    def test_com_storage_externo_configurado_libera_o_host(self):
        with self.settings(MEDIA_STORAGE_HOST="tuqecavtmbkriwhnqzfu.storage.supabase.co"):
            resposta = self.client.get(reverse("login"))
        csp = resposta["Content-Security-Policy"]
        img_src = next(d for d in csp.split(";") if d.strip().startswith("img-src"))
        self.assertIn("https://tuqecavtmbkriwhnqzfu.storage.supabase.co", img_src)
        self.assertIn("'self'", img_src)


class SaudeTest(TestCase):
    def test_endpoint_responde_sem_autenticacao(self):
        resposta = self.client.get(reverse("saude"))
        self.assertEqual(200, resposta.status_code)
        self.assertEqual("ok", resposta.json()["status"])

    def test_nao_expoe_detalhe_de_infraestrutura(self):
        """Health check verboso é presente de reconhecimento para quem mapeia o alvo."""
        corpo = self.client.get(reverse("saude")).content.decode().lower()
        for termo in ("postgres", "django", "supabase", "version", "host", "traceback"):
            self.assertNotIn(termo, corpo)

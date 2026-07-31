"""
Endpoint de cron (core/views_cron.py) — chamado pelo Vercel Cron, não por
usuário logado, então a proteção é o segredo compartilhado `CRON_SECRET`.
"""

from django.test import TestCase, override_settings
from django.urls import reverse


class NotificacoesDiariasCronTest(TestCase):
    def setUp(self):
        self.url = reverse("cron_notificacoes_diarias")

    @override_settings(CRON_SECRET="")
    def test_sem_cron_secret_configurado_recusa_mesmo_sem_header(self):
        # Omissão de configuração nunca deve significar "endpoint aberto".
        response = self.client.get(self.url)
        self.assertEqual(403, response.status_code)

    @override_settings(CRON_SECRET="segredo-do-cron")
    def test_sem_header_de_autorizacao_e_recusado(self):
        response = self.client.get(self.url)
        self.assertEqual(403, response.status_code)

    @override_settings(CRON_SECRET="segredo-do-cron")
    def test_header_com_segredo_errado_e_recusado(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer errado")
        self.assertEqual(403, response.status_code)

    @override_settings(CRON_SECRET="segredo-do-cron")
    def test_header_com_segredo_correto_executa_o_job(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer segredo-do-cron")
        self.assertEqual(200, response.status_code)
        self.assertIn("notificacoes_enviadas", response.json())

    @override_settings(CRON_SECRET="segredo-do-cron")
    def test_metodo_post_nao_e_permitido(self):
        response = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer segredo-do-cron")
        self.assertEqual(405, response.status_code)

"""
A configuração de produção precisa recusar valores inseguros.

Estes testes existem porque a falha que eles cobrem é silenciosa por
natureza: um deploy com a SECRET_KEY de desenvolvimento *funciona
perfeitamente* — só permite que qualquer pessoa com acesso ao repositório
forje sessões e tokens de recuperação de senha.
"""

from django.conf import settings
from django.test import SimpleTestCase

from ciclartech.seguranca import (
    CHAVE_INSEGURA_PADRAO,
    avisos_de_configuracao,
    problemas_de_configuracao,
    sanear_allowed_hosts,
)

CHAVE_FORTE = "x" * 50


class ValidacaoDeConfiguracaoTest(SimpleTestCase):
    def test_em_debug_nada_e_bloqueante(self):
        problemas = problemas_de_configuracao(
            secret_key=CHAVE_INSEGURA_PADRAO, allowed_hosts=["*"], debug=True
        )
        self.assertEqual([], problemas)

    def test_chave_de_desenvolvimento_e_recusada_em_producao(self):
        problemas = problemas_de_configuracao(
            secret_key=CHAVE_INSEGURA_PADRAO, allowed_hosts=["app.exemplo.br"], debug=False
        )
        self.assertTrue(any("DJANGO_SECRET_KEY" in p for p in problemas))

    def test_chave_vazia_e_recusada(self):
        problemas = problemas_de_configuracao(
            secret_key="", allowed_hosts=["app.exemplo.br"], debug=False
        )
        self.assertTrue(any("DJANGO_SECRET_KEY" in p for p in problemas))

    def test_chave_curta_avisa_mas_nao_derruba(self):
        # Chave curta porém aleatória enfraquece a margem; a de
        # desenvolvimento a elimina. Só a segunda impede o sistema de subir.
        problemas = problemas_de_configuracao(
            secret_key="curta-demais", allowed_hosts=["app.exemplo.br"], debug=False
        )
        self.assertEqual([], problemas)

        avisos = avisos_de_configuracao(secret_key="curta-demais", debug=False)
        self.assertTrue(any("caracteres" in a for a in avisos))

    def test_chave_forte_nao_gera_aviso(self):
        self.assertEqual([], avisos_de_configuracao(secret_key=CHAVE_FORTE, debug=False))

    def test_allowed_hosts_curinga_e_recusado(self):
        problemas = problemas_de_configuracao(
            secret_key=CHAVE_FORTE, allowed_hosts=["*"], debug=False
        )
        self.assertTrue(any("ALLOWED_HOSTS" in p for p in problemas))

    def test_allowed_hosts_vazio_e_recusado_como_fatal(self):
        problemas = problemas_de_configuracao(
            secret_key=CHAVE_FORTE, allowed_hosts=[], debug=False
        )
        self.assertTrue(any("ALLOWED_HOSTS" in p for p in problemas))

    def test_configuracao_correta_passa(self):
        problemas = problemas_de_configuracao(
            secret_key=CHAVE_FORTE, allowed_hosts=["ciclartech.vercel.app"], debug=False
        )
        self.assertEqual([], problemas)


class SaneamentoDeHostsTest(SimpleTestCase):
    """
    O curinga é descartado, não motivo de queda: derrubar um sistema de
    atendimento não é necessário para eliminar o risco, já que remover o '*'
    por si só o elimina.
    """

    def test_curinga_e_removido_em_producao(self):
        hosts, avisos = sanear_allowed_hosts(["*", "app.exemplo.br"], debug=False)
        self.assertEqual(["app.exemplo.br"], hosts)
        self.assertEqual(1, len(avisos))

    def test_curinga_e_mantido_em_desenvolvimento(self):
        hosts, avisos = sanear_allowed_hosts(["*"], debug=True)
        self.assertEqual(["*"], hosts)
        self.assertEqual([], avisos)

    def test_lista_sem_curinga_passa_intacta(self):
        hosts, avisos = sanear_allowed_hosts(["app.exemplo.br"], debug=False)
        self.assertEqual(["app.exemplo.br"], hosts)
        self.assertEqual([], avisos)


class ConfiguracaoEfetivaTest(SimpleTestCase):
    """Confere as decisões de segurança que ficaram fixas no settings."""

    def test_argon2_e_o_hasher_primario(self):
        self.assertIn("Argon2", settings.PASSWORD_HASHERS[0])

    def test_senha_minima_de_12_caracteres(self):
        validador = next(
            v
            for v in settings.AUTH_PASSWORD_VALIDATORS
            if "MinimumLengthValidator" in v["NAME"]
        )
        self.assertGreaterEqual(validador["OPTIONS"]["min_length"], 12)

    def test_cookies_de_sessao_sao_inacessiveis_ao_javascript(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

    def test_cookies_nao_viajam_em_requisicao_cross_site(self):
        self.assertEqual("Lax", settings.SESSION_COOKIE_SAMESITE)
        self.assertEqual("Lax", settings.CSRF_COOKIE_SAMESITE)

    def test_sessao_expira_ao_fechar_o_navegador(self):
        # Terminal compartilhado é o cenário de uso real do produto.
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)

    def test_link_de_redefinicao_de_senha_expira_em_no_maximo_uma_hora(self):
        self.assertLessEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)

    def test_clickjacking_bloqueado(self):
        self.assertEqual("DENY", settings.X_FRAME_OPTIONS)

    def test_referrer_nao_vaza_para_terceiros(self):
        self.assertEqual("same-origin", settings.SECURE_REFERRER_POLICY)

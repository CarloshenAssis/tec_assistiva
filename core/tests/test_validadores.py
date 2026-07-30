"""
Validação de CPF e de arquivos enviados.

O caso do upload é o que realmente importa: um `.svg` contendo `<script>`,
renomeado para `.png` e servido na origem da aplicação, executa JavaScript
com a sessão de quem abrir. Por isso a checagem não para na extensão.
"""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from core.validadores import (
    cnpj_e_valido,
    cpf_e_valido,
    normalizar_cnpj,
    normalizar_cpf,
    validar_cnpj,
    validar_cpf,
    validar_documento,
    validar_upload,
    validar_upload_imagem,
)

# Cabeçalhos reais dos formatos aceitos.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"\x00" * 32
SVG_MALICIOSO = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


class CpfTest(SimpleTestCase):
    def test_aceita_cpf_com_digito_verificador_correto(self):
        self.assertTrue(cpf_e_valido("123.456.789-09"))

    def test_aceita_sem_mascara(self):
        self.assertTrue(cpf_e_valido("12345678909"))

    def test_recusa_digito_verificador_errado(self):
        self.assertFalse(cpf_e_valido("123.456.789-00"))

    def test_recusa_sequencia_de_digito_repetido(self):
        # Passam no cálculo do verificador, mas não são CPFs emitidos — e são
        # exatamente o que se digita para "preencher o campo".
        for sequencia in ("111.111.111-11", "000.000.000-00", "999.999.999-99"):
            self.assertFalse(cpf_e_valido(sequencia), sequencia)

    def test_recusa_quantidade_errada_de_digitos(self):
        self.assertFalse(cpf_e_valido("123.456.789"))
        self.assertFalse(cpf_e_valido("123.456.789-091"))

    def test_recusa_vazio(self):
        self.assertFalse(cpf_e_valido(""))
        self.assertFalse(cpf_e_valido(None))

    def test_validador_levanta_para_o_django(self):
        with self.assertRaises(ValidationError):
            validar_cpf("123.456.789-00")

    def test_normalizacao_remove_mascara(self):
        self.assertEqual("12345678909", normalizar_cpf("123.456.789-09"))


class CnpjTest(SimpleTestCase):
    def test_aceita_cnpj_com_digito_verificador_correto(self):
        self.assertTrue(cnpj_e_valido("11.222.333/0001-81"))

    def test_aceita_sem_mascara(self):
        self.assertTrue(cnpj_e_valido("11222333000181"))

    def test_recusa_digito_verificador_errado(self):
        self.assertFalse(cnpj_e_valido("11.222.333/0001-00"))

    def test_recusa_sequencia_de_digito_repetido(self):
        self.assertFalse(cnpj_e_valido("11.111.111/1111-11"))

    def test_recusa_quantidade_errada_de_digitos(self):
        self.assertFalse(cnpj_e_valido("11.222.333/0001-8"))

    def test_recusa_vazio(self):
        self.assertFalse(cnpj_e_valido(""))
        self.assertFalse(cnpj_e_valido(None))

    def test_validador_levanta_para_o_django(self):
        with self.assertRaises(ValidationError):
            validar_cnpj("11.222.333/0001-00")

    def test_normalizacao_remove_mascara(self):
        self.assertEqual("11222333000181", normalizar_cnpj("11.222.333/0001-81"))


class ValidarDocumentoTest(SimpleTestCase):
    """Dispatcher usado pelo cadastro de titular (docs/business-rules/modulos.md)."""

    def test_valida_como_cpf_por_padrao(self):
        validar_documento("123.456.789-09", "cpf")
        with self.assertRaises(ValidationError):
            validar_documento("123.456.789-00", "cpf")

    def test_valida_como_cnpj_quando_solicitado(self):
        validar_documento("11.222.333/0001-81", "cnpj")
        with self.assertRaises(ValidationError):
            validar_documento("11.222.333/0001-00", "cnpj")

    def test_cpf_valido_nao_passa_como_cnpj(self):
        """Confirma que os dois validadores realmente são independentes, não um fallback do outro."""
        with self.assertRaises(ValidationError):
            validar_documento("123.456.789-09", "cnpj")


class UploadTest(SimpleTestCase):
    def _arquivo(self, nome: str, conteudo: bytes) -> SimpleUploadedFile:
        return SimpleUploadedFile(nome, conteudo)

    def test_aceita_png_legitimo(self):
        validar_upload(self._arquivo("laudo.png", PNG))

    def test_aceita_pdf_legitimo(self):
        validar_upload(self._arquivo("laudo.pdf", PDF))

    def test_recusa_extensao_fora_da_allowlist(self):
        with self.assertRaises(ValidationError) as ctx:
            validar_upload(self._arquivo("payload.svg", SVG_MALICIOSO))
        self.assertEqual("extensao_nao_permitida", ctx.exception.code)

    def test_recusa_executavel_disfarcado_de_pdf(self):
        with self.assertRaises(ValidationError) as ctx:
            validar_upload(self._arquivo("laudo.pdf", b"MZ\x90\x00" + b"\x00" * 32))
        self.assertEqual("conteudo_invalido", ctx.exception.code)

    def test_recusa_svg_renomeado_para_png(self):
        """O ataque que a checagem de extensão sozinha não pega."""
        with self.assertRaises(ValidationError) as ctx:
            validar_upload(self._arquivo("laudo.png", SVG_MALICIOSO))
        self.assertEqual("conteudo_invalido", ctx.exception.code)

    def test_recusa_arquivo_acima_do_limite(self):
        grande = self._arquivo("laudo.png", PNG)
        grande.size = 20 * 1024 * 1024
        with self.assertRaises(ValidationError) as ctx:
            validar_upload(grande)
        self.assertEqual("arquivo_muito_grande", ctx.exception.code)

    def test_recusa_arquivo_sem_extensao(self):
        with self.assertRaises(ValidationError):
            validar_upload(self._arquivo("laudo", PNG))

    def test_validador_de_imagem_recusa_pdf(self):
        # Campo de foto não deve aceitar documento, mesmo sendo tipo seguro.
        with self.assertRaises(ValidationError) as ctx:
            validar_upload_imagem(self._arquivo("foto.pdf", PDF))
        self.assertEqual("extensao_nao_permitida", ctx.exception.code)

    def test_nao_consome_o_ponteiro_do_arquivo(self):
        """
        A validação lê o cabeçalho e precisa devolver o ponteiro ao início —
        senão o arquivo salvo em disco fica truncado.
        """
        arquivo = self._arquivo("laudo.png", PNG)
        arquivo.seek(0)
        validar_upload(arquivo)
        self.assertEqual(PNG, arquivo.read())

    def test_ignora_valor_nulo(self):
        validar_upload(None)  # campo opcional não deve explodir

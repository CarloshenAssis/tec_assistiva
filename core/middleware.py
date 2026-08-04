"""
Cabeçalhos de segurança da resposta HTTP.

O Django já cobre parte disso via settings (`SECURE_*`), mas duas coisas
ficam de fora e são justamente as que mais importam aqui: a Content Security
Policy e o controle de cache de páginas com dado pessoal.
"""

from __future__ import annotations

from django.conf import settings

#: Content Security Policy.
#:
#: `script-src 'self'` sem `'unsafe-inline'` é o ponto central: mesmo que
#: alguém consiga injetar `<script>` em um campo de texto (nome de
#: beneficiário, observação de manutenção), o navegador se recusa a executar.
#: Isso só é possível porque o projeto não tem nenhum script inline — os três
#: `onclick` que existiam foram removidos em favor de `name`/`value` no botão.
#:
#: `style-src` precisa de `'unsafe-inline'`: há ~215 atributos `style="..."`
#: nos templates, e atributo de estilo não aceita nonce nem hash (só
#: elemento `<style>` aceita). É uma concessão consciente e de impacto menor —
#: CSS injetado pode fazer exfiltração por seletor, mas não executa código.
#: Eliminá-la exige migrar os estilos inline para classes no CSS.
#:
#: `img-src` é sempre 'self' — nenhuma imagem é servida por link direto ao
#: storage externo. Fotos de ativo/movimentação e logotipo do tenant vivem
#: no bucket privado do Supabase e são servidas por view autenticada
#: (`core.arquivos.resposta_de_imagem`), nunca por `.url` direto no
#: `<img src>` — ver `ativos.views.foto_ativo_imagem` para a justificativa
#: (URL assinada mudava a cada render, o navegador nunca cacheava, e cada
#: visita à ficha rebaixava as fotos inteiras do Supabase de novo).
#: Deixar `img-src` restrito a 'self' é também um guard-rail: se alguém
#: reintroduzir um `.url` direto no futuro, a imagem simplesmente não
#: carrega (bug visível), em vez de a CSP liberar a origem silenciosamente
#: e o mesmo problema de cache voltar sem ninguém notar.
def _politica_csp() -> str:
    """Monta a Content Security Policy completa da aplicação.

    Returns:
        A string de política CSP, pronta para o cabeçalho
        `Content-Security-Policy`.
    """
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        # Impede que a aplicação seja embutida em iframe de terceiro
        # (clickjacking). Redundante com X-Frame-Options de propósito:
        # navegador antigo respeita um, navegador atual respeita o outro.
        "frame-ancestors 'none'; "
        # Bloqueia o roubo de formulário: um POST de dados de paciente não
        # pode ser redirecionado para um domínio externo por HTML injetado.
        "form-action 'self'; "
        # Sem isso, um `<base href="//atacante">` injetado reescreveria
        # todos os caminhos relativos da página, inclusive o do JavaScript.
        "base-uri 'self'; "
        "object-src 'none'"
    )

#: Desliga APIs de dispositivo que a aplicação não usa. `camera=(self)` fica
#: liberado só para a própria origem porque a leitura de QR Code por câmera
#: é incremento previsto sobre a rota de scan que já existe.
POLITICA_PERMISSOES = (
    "camera=(self), microphone=(), geolocation=(), "
    "payment=(), usb=(), magnetometer=(), gyroscope=()"
)


class CabecalhosDeSegurancaMiddleware:
    """Aplica CSP, Permissions-Policy e controle de cache de dado pessoal.

    Middleware de resposta — não interfere na requisição, só acrescenta
    cabeçalhos de segurança à resposta já processada pela view.
    """

    def __init__(self, get_response):
        """Inicializa o middleware.

        Args:
            get_response: Callable padrão do Django que processa a
                requisição e devolve a resposta.
        """
        self.get_response = get_response

    def __call__(self, request):
        """Processa a requisição, acrescentando os cabeçalhos de segurança.

        Args:
            request: A requisição HTTP corrente.

        Returns:
            A resposta HTTP, com `Content-Security-Policy`,
            `Permissions-Policy` e, para usuário autenticado,
            `Cache-Control: private, no-store, max-age=0` — página com
            dado pessoal não pode ficar no cache do navegador: em
            terminal compartilhado de posto de saúde, o botão "voltar"
            após o logout exibiria a ficha do paciente anterior.
        """
        resposta = self.get_response(request)

        resposta.setdefault("Content-Security-Policy", self._csp())
        resposta.setdefault("Permissions-Policy", POLITICA_PERMISSOES)

        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            resposta.setdefault("Cache-Control", "private, no-store, max-age=0")

        return resposta

    def _csp(self) -> str:
        """Monta a CSP final, reforçada em produção.

        Returns:
            A política CSP, com `upgrade-insecure-requests` acrescentado
            quando `settings.DEBUG` for `False` — força o navegador a
            promover para HTTPS qualquer sub-recurso que tenha escapado
            como `http://`.
        """
        csp = _politica_csp()
        if not settings.DEBUG:
            csp += "; upgrade-insecure-requests"
        return csp

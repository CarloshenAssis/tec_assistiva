from django.urls import path

from ativos import views

app_name = "ativos"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.criar, name="criar"),
    path("scan/", views.scan, name="scan"),
    path("qr/<str:token>/", views.resolver_qr, name="resolver_qr"),
    path("emprestimo/", views.wizard_emprestimo, name="wizard_emprestimo"),
    path("devolucao/", views.devolucao, name="devolucao"),
    path("manutencao/", views.manutencao_lista, name="manutencao_lista"),
    path("<int:pk>/", views.ficha, name="ficha"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/qrcode.png", views.qrcode_imagem, name="qrcode_imagem"),
    path("<int:pk>/acao/<str:codigo>/", views.executar_acao, name="executar_acao"),
]

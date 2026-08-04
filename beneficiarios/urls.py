from django.urls import path

from beneficiarios import views

app_name = "beneficiarios"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.criar, name="criar"),
    path("<int:pk>/", views.ficha, name="ficha"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/documentos/novo/", views.documento_novo, name="documento_novo"),
    path("<int:pk>/exportar/", views.exportar, name="exportar"),
    path("<int:pk>/anonimizar/", views.anonimizar_titular, name="anonimizar"),
    path("documento/<int:pk>/", views.baixar_documento, name="baixar_documento"),
]

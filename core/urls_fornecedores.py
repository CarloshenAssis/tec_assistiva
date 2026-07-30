from django.urls import path

from core import views_fornecedores as views

app_name = "fornecedores"

urlpatterns = [
    path("", views.fornecedores_lista, name="lista"),
    path("novo/", views.fornecedores_criar, name="criar"),
    path("<int:pk>/editar/", views.fornecedores_editar, name="editar"),
]

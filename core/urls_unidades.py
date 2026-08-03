"""Rotas de `/app/unidades/*`."""

from django.urls import path

from core import views_unidades as views

app_name = "unidades"

urlpatterns = [
    path("", views.unidades_lista, name="lista"),
    path("nova/", views.unidades_criar, name="criar"),
    path("<int:pk>/editar/", views.unidades_editar, name="editar"),
    path("<int:pk>/alternar-ativo/", views.unidades_alternar_ativo, name="alternar_ativo"),
]

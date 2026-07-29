from django.urls import path

from contas import views

app_name = "usuarios"

urlpatterns = [
    path("", views.usuarios_lista, name="lista"),
    path("novo/", views.usuarios_criar, name="criar"),
    path("<int:pk>/alternar-ativo/", views.usuarios_alternar_ativo, name="alternar_ativo"),
    path("auditoria/", views.auditoria_lista, name="auditoria"),
]

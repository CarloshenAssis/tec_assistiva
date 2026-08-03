"""Rotas de `/app/usuarios/*` (gestão de usuários e auditoria)."""

from django.urls import path

from contas import views

app_name = "usuarios"

urlpatterns = [
    path("", views.usuarios_lista, name="lista"),
    path("novo/", views.usuarios_criar, name="criar"),
    path("<int:pk>/editar/", views.usuarios_editar, name="editar"),
    path("<int:pk>/alternar-ativo/", views.usuarios_alternar_ativo, name="alternar_ativo"),
    path("<int:pk>/gerar-nova-senha/", views.usuarios_gerar_nova_senha, name="gerar_nova_senha"),
    path("auditoria/", views.auditoria_lista, name="auditoria"),
    path("auditoria/exportar/", views.auditoria_exportar, name="auditoria_exportar"),
]

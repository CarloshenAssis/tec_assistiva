from django.urls import path

from owner import views

app_name = "owner"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("contratos/novo/", views.criar_tenant, name="criar_tenant"),
    path("contratos/<int:pk>/", views.tenant_detalhe, name="tenant_detalhe"),
    path("contratos/<int:pk>/alternar-ativo/", views.alternar_tenant_ativo, name="alternar_tenant_ativo"),
    path(
        "contratos/<int:tenant_id>/administrador/novo/",
        views.criar_administrador,
        name="criar_administrador",
    ),
    path("auditoria/", views.auditoria, name="auditoria"),
]

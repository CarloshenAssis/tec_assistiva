from django.urls import include, path

from core import views

app_name = "app"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("relatorios/", views.relatorios, name="relatorios"),
    path("ativos/", include("ativos.urls")),
    path("beneficiarios/", include("beneficiarios.urls")),
    path("notificacoes/", include("notificacoes.urls")),
    path("usuarios/", include("contas.urls")),
]

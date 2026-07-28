from django.urls import include, path

from core import views

app_name = "app"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("ativos/", include("ativos.urls")),
    path("beneficiarios/", include("beneficiarios.urls")),
]

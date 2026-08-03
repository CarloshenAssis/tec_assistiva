from django.urls import include, path

from core import views, views_encarregado

app_name = "app"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("encarregado/", views_encarregado.encarregado_editar, name="encarregado"),
    path("relatorios/", views.relatorios, name="relatorios"),
    path("relatorios/exportar/ativos/", views.relatorios_exportar_ativos, name="relatorios_exportar_ativos"),
    path(
        "relatorios/exportar/beneficiarios/",
        views.relatorios_exportar_beneficiarios,
        name="relatorios_exportar_beneficiarios",
    ),
    path(
        "relatorios/exportar/movimentacoes/",
        views.relatorios_exportar_movimentacoes,
        name="relatorios_exportar_movimentacoes",
    ),
    path("ativos/", include("ativos.urls")),
    path("beneficiarios/", include("beneficiarios.urls")),
    path("notificacoes/", include("notificacoes.urls")),
    path("usuarios/", include("contas.urls")),
    path("unidades/", include("core.urls_unidades")),
    path("fornecedores/", include("core.urls_fornecedores")),
]

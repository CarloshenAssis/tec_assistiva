from django.urls import path

from beneficiarios import views

app_name = "beneficiarios"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.criar, name="criar"),
    path("<int:pk>/", views.ficha, name="ficha"),
]

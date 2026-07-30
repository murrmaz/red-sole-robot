from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("metrics/", views.metrics_data, name="metrics_data"),
]

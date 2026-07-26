from django.urls import path

from . import views

app_name = "moderation"

urlpatterns = [
    path("", views.queue_list, name="queue_list"),
    path("stats/", views.stats, name="stats"),
    path("<int:pk>/", views.record_detail, name="record_detail"),
    path("<int:pk>/review/", views.review_record, name="review_record"),
]

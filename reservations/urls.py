from django.urls import path

from . import views

app_name = "reservations"

urlpatterns = [
    path("restaurants/", views.restaurant_list, name="restaurant_list"),
    path("restaurants/<int:pk>/", views.restaurant_detail, name="restaurant_detail"),
    path("restaurants/<int:pk>/reserve/", views.reservation_create, name="reservation_create"),
    path("reservations/", views.reservation_list, name="reservation_list"),
    path("reservations/<int:pk>/cancel/", views.reservation_cancel, name="reservation_cancel"),
]

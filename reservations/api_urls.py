from django.urls import path

from .api_views import ReservationCancelAPIView, ReservationListCreateAPIView

app_name = "reservations_api"

urlpatterns = [
    path("reservations/", ReservationListCreateAPIView.as_view(), name="reservation_list_create"),
    path("reservations/<int:pk>/", ReservationCancelAPIView.as_view(), name="reservation_cancel"),
]

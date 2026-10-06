from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Reservation
from .serializers import ReservationSerializer


class ReservationListCreateAPIView(generics.ListCreateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ReservationSerializer

    def get_queryset(self):
        return Reservation.objects.filter(user=self.request.user).select_related("restaurant")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, status=Reservation.Status.CONFIRMED)


class ReservationCancelAPIView(generics.GenericAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ReservationSerializer

    def get_queryset(self):
        return Reservation.objects.filter(user=self.request.user).select_related("restaurant")

    def delete(self, request, *args, **kwargs):
        reservation = self.get_object()
        if not reservation.can_cancel:
            message = (
                "この予約はすでにキャンセル済みです。"
                if reservation.status == Reservation.Status.CANCELLED
                else "予約日時を過ぎているため、キャンセルできません。"
            )
            return Response({"detail": message}, status=status.HTTP_409_CONFLICT)
        reservation.status = Reservation.Status.CANCELLED
        reservation.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)

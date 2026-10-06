from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import ReservationForm
from .models import Reservation, Restaurant


def _restaurant_image_path(restaurant):
    if not restaurant.description.startswith("[seed_demo:v1]\n"):
        return ""
    return {
        "【デモ】まちの食堂": "reservations/images/demo-diner.jpg",
        "【デモ】駅前レストラン": "reservations/images/demo-restaurant.jpg",
    }.get(restaurant.name, "")


def restaurant_list(request):
    restaurants = Restaurant.objects.all()
    for restaurant in restaurants:
        restaurant.image_static_path = _restaurant_image_path(restaurant)
    return render(
        request,
        "reservations/restaurant_list.html",
        {"restaurants": restaurants},
    )


def restaurant_detail(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    return render(
        request,
        "reservations/restaurant_detail.html",
        {
            "restaurant": restaurant,
            "restaurant_description": restaurant.description.removeprefix("[seed_demo:v1]\n"),
            "restaurant_image": _restaurant_image_path(restaurant),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def reservation_create(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    form = ReservationForm(
        request.POST if request.method == "POST" else None, restaurant=restaurant
    )
    if request.method == "POST" and form.is_valid():
        reservation = form.save(commit=False)
        reservation.user = request.user
        reservation.restaurant = restaurant
        reservation.save()
        messages.success(request, "予約を受け付けました。")
        return redirect("reservations:reservation_list")
    return render(
        request,
        "reservations/reservation_form.html",
        {"restaurant": restaurant, "form": form},
    )


@login_required
@require_GET
def reservation_list(request):
    reservations = Reservation.objects.filter(user=request.user).select_related("restaurant")
    return render(
        request, "reservations/reservation_list.html", {"reservations": reservations}
    )


@login_required
@require_POST
def reservation_cancel(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, user=request.user)
    if reservation.can_cancel:
        reservation.status = Reservation.Status.CANCELLED
        reservation.save(update_fields=["status"])
        messages.success(request, "予約をキャンセルしました。")
    elif reservation.status == Reservation.Status.CANCELLED:
        messages.info(request, "この予約はすでにキャンセル済みです。")
    else:
        messages.error(request, "予約日時を過ぎているため、キャンセルできません。")
    return redirect("reservations:reservation_list")

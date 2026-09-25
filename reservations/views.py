from django.shortcuts import get_object_or_404, render

from .models import Restaurant


def restaurant_list(request):
    restaurants = Restaurant.objects.all()
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
        {"restaurant": restaurant},
    )

from django.contrib import admin

from .models import Restaurant


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = (
        "name", "address", "opening_time", "last_reservation_time",
        "closing_time", "max_party_size", "business_hours",
    )
    search_fields = ("name", "address")

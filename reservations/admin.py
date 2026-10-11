from django.contrib import admin

from .models import Restaurant


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = (
        "name", "address", "phone_number", "opening_time", "last_reservation_time",
        "closing_time", "max_party_size", "business_hours",
    )
    search_fields = ("name", "address")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "phone_number":
            # 標準CharFieldのstripで前後の空白を受理しない。
            kwargs["strip"] = False
        return super().formfield_for_dbfield(db_field, request, **kwargs)

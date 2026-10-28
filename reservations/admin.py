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
            kwargs["required"] = True
            kwargs["help_text"] = (
                "国内電話番号・半角数字10〜11桁。ハイフン任意。空白は使用できません。"
                "実際に使用権限のある電話番号を登録してください。"
                "適当な数字を入力すると、実在する番号への誤発信につながる可能性があります。"
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

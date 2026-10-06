from django import forms

from .models import Reservation
from .validators import (
    validate_reservation_datetime_format, validate_reservation_datetime,
    validate_reservation_party_size, validate_restaurant_accepts_reservations,
)


class ReservationDateTimeField(forms.DateTimeField):
    def to_python(self, value):
        # DjangoのISO日時解析より先に、秒・タイムゾーン・空白を拒否する。
        if value not in self.empty_values:
            validate_reservation_datetime_format(value, self.error_messages["invalid"])
        return super().to_python(value)


class ReservationForm(forms.ModelForm):
    reserved_at = ReservationDateTimeField(
        label="予約日時",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "step": "60"},
        ),
        error_messages={
            "required": "予約日時を入力してください。",
            "invalid": "予約日時は日本時間でYYYY-MM-DDTHH:MM形式の正しい日時を入力してください。",
        },
    )

    class Meta:
        model = Reservation
        fields = ["reserved_at", "party_size"]
        error_messages = {
            "party_size": {
                "required": "人数を入力してください。",
                "min_value": "人数は1人以上を指定してください。",
            },
        }

    def __init__(self, *args, restaurant, **kwargs):
        self.restaurant = restaurant
        super().__init__(*args, **kwargs)
        # PositiveSmallIntegerFieldが設定するmin=0を、予約人数の下限に合わせる。
        self.fields["party_size"].widget.attrs.update(
            {"min": 1, "max": restaurant.max_party_size}
        )

    def clean_reserved_at(self):
        reserved_at = self.cleaned_data["reserved_at"]
        validate_reservation_datetime(self.restaurant, reserved_at)
        return reserved_at

    def clean_party_size(self):
        party_size = self.cleaned_data["party_size"]
        validate_reservation_party_size(self.restaurant, party_size)
        return party_size

    def clean(self):
        cleaned_data = super().clean()
        validate_restaurant_accepts_reservations(self.restaurant)
        return cleaned_data

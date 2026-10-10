from datetime import datetime

from django import forms
from django.utils import timezone

from .models import Reservation
from .validators import (
    reservation_time_choices, validate_reservation_datetime_format,
    validate_reservation_datetime,
    validate_reservation_party_size, validate_restaurant_accepts_reservations,
)


HTML_DATETIME_INVALID_MESSAGE = "予約日はYYYY-MM-DD形式の正しい日付を入力し、時刻を選択してください。"


class ReservationDateTimeWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        super().__init__([
            forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "aria-label": "予約日"}),
            forms.Select(attrs={"aria-label": "予約時刻"}),
        ], attrs)

    def decompress(self, value):
        if value:
            value = timezone.localtime(value, timezone.get_default_timezone())
            return [value.date(), value.strftime("%H:%M")]
        return [None, None]


class ReservationDateTimeField(forms.MultiValueField):
    widget = ReservationDateTimeWidget

    def __init__(self, **kwargs):
        super().__init__(
            fields=[forms.CharField(strip=False), forms.CharField(strip=False)],
            error_messages={
                "required": "予約日時を入力してください。",
                "incomplete": "予約日と予約時刻を両方入力してください。",
                "invalid": HTML_DATETIME_INVALID_MESSAGE,
            }, **kwargs,
        )

    def compress(self, data_list):
        if not data_list:
            return None
        value = f"{data_list[0]}T{data_list[1]}"
        validate_reservation_datetime_format(value, HTML_DATETIME_INVALID_MESSAGE)
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except ValueError as error:
            raise forms.ValidationError(HTML_DATETIME_INVALID_MESSAGE, code="invalid") from error
        return timezone.make_aware(parsed, timezone.get_default_timezone())


class ReservationForm(forms.ModelForm):
    reserved_at = ReservationDateTimeField(label="予約日時")

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
        self.fields["reserved_at"].widget.widgets[1].choices = [
            ("", "時刻を選択してください"), *reservation_time_choices(restaurant)
        ]
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

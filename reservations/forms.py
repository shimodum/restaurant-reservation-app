import re

from django import forms
from django.utils import timezone

from .models import Reservation


class ReservationDateTimeField(forms.DateTimeField):
    def to_python(self, value):
        # DjangoのISO日時解析より先に、秒・タイムゾーン・空白を拒否する。
        if value not in self.empty_values and (
            not isinstance(value, str)
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}", value) is None
        ):
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
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
                "max_value": "人数は10人以下を指定してください。",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # PositiveSmallIntegerFieldが設定するmin=0を、予約人数の下限に合わせる。
        self.fields["party_size"].widget.attrs.update({"min": 1, "max": 10})

    def clean_reserved_at(self):
        reserved_at = self.cleaned_data["reserved_at"]
        if reserved_at <= timezone.now():
            raise forms.ValidationError("予約日時は未来の日時を指定してください。")
        return reserved_at

from django import forms
from django.utils import timezone

from .models import Reservation


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["reserved_at", "party_size"]
        error_messages = {
            "reserved_at": {
                "required": "予約日時を入力してください。",
            },
            "party_size": {
                "required": "人数を入力してください。",
                "min_value": "人数は1人以上を指定してください。",
                "max_value": "人数は10人以下を指定してください。",
            },
        }
        widgets = {
            "reserved_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "step": "60"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reserved_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        # PositiveSmallIntegerFieldが設定するmin=0を、予約人数の下限に合わせる。
        self.fields["party_size"].widget.attrs.update({"min": 1, "max": 10})

    def clean_reserved_at(self):
        reserved_at = self.cleaned_data["reserved_at"]
        if reserved_at <= timezone.now():
            raise forms.ValidationError("予約日時は未来の日時を指定してください。")
        return reserved_at

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Restaurant(models.Model):
    name = models.CharField("店名", max_length=100)
    description = models.TextField("説明")
    address = models.CharField("住所", max_length=255)
    business_hours = models.TextField(
        "営業時間の補足案内", help_text="L.O.などの案内文です。予約可否の判定には使用しません。"
    )
    opening_time = models.TimeField(
        "開店時刻", null=True, blank=True,
        help_text="日本時間・分単位。時刻3項目が未設定の場合は予約受付を停止します。",
    )
    last_reservation_time = models.TimeField(
        "最終予約可能時刻", null=True, blank=True,
        help_text="この時刻ちょうどの予約も可能です。開店より後、閉店より前に設定してください。",
    )
    closing_time = models.TimeField("閉店時刻", null=True, blank=True)
    max_party_size = models.PositiveSmallIntegerField(
        "最大予約人数", default=10,
        validators=[MinValueValidator(1), MaxValueValidator(32767)],
        help_text="1予約あたりの最大人数です。",
    )

    class Meta:
        ordering = ["pk"]
        verbose_name = "店舗"
        verbose_name_plural = "店舗"

    def __str__(self):
        return self.name

    @property
    def can_accept_reservations(self):
        times = (self.opening_time, self.last_reservation_time, self.closing_time)
        return (
            self.max_party_size >= 1
            and all(value is not None for value in times)
            and all(value.second == 0 and value.microsecond == 0 for value in times)
            and self.opening_time < self.last_reservation_time < self.closing_time
        )

    def clean(self):
        super().clean()
        times = (self.opening_time, self.last_reservation_time, self.closing_time)
        if all(value is None for value in times):
            return
        if not all(value is not None for value in times):
            raise ValidationError("開店・最終予約可能・閉店の時刻は3項目すべて設定してください。")
        if not (
            all(value.second == 0 and value.microsecond == 0 for value in times)
            and self.opening_time < self.last_reservation_time < self.closing_time
        ):
            raise ValidationError(
                "時刻は分単位で、開店時刻 < 最終予約可能時刻 < 閉店時刻に設定してください。"
            )


class Reservation(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "予約済み"
        CANCELLED = "cancelled", "キャンセル済み"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reservations"
    )
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.PROTECT, related_name="reservations"
    )
    reserved_at = models.DateTimeField("予約日時")
    party_size = models.PositiveSmallIntegerField(
        "人数", validators=[MinValueValidator(1)]
    )
    status = models.CharField(
        "状態", max_length=10, choices=Status.choices, default=Status.CONFIRMED
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        ordering = ["-reserved_at", "-pk"]
        verbose_name = "予約"
        verbose_name_plural = "予約"

    @property
    def can_cancel(self):
        return self.status == self.Status.CONFIRMED and self.reserved_at > timezone.now()

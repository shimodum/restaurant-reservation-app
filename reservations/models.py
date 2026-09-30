from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Restaurant(models.Model):
    name = models.CharField("店名", max_length=100)
    description = models.TextField("説明")
    address = models.CharField("住所", max_length=255)
    business_hours = models.TextField("営業時間")

    class Meta:
        ordering = ["pk"]
        verbose_name = "店舗"
        verbose_name_plural = "店舗"

    def __str__(self):
        return self.name


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
        "人数", validators=[MinValueValidator(1), MaxValueValidator(10)]
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

from django.db import models


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

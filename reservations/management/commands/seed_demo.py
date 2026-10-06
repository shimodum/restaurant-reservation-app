"""ローカル開発用データ。既存行は更新・削除しない。"""
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from reservations.models import Reservation, Restaurant
from reservations.validators import (
    validate_reservation_datetime,
    validate_reservation_party_size,
    validate_restaurant_accepts_reservations,
)


USERNAMES = ("demo_user1", "demo_user2")
RESTAURANT_NAMES = ("【デモ】まちの食堂", "【デモ】駅前レストラン")
MARKER = "seed_demo:v1"
PASSWORD = "demo1234"


class Command(BaseCommand):
    help = "ローカル専用のデモユーザー2名・店舗2件・予約4件を投入します。"

    def handle(self, *args, **options):
        if not settings.DEBUG or not settings.ALLOWED_HOSTS or not set(
            settings.ALLOWED_HOSTS
        ) <= {"localhost", "127.0.0.1"}:
            raise CommandError("DEBUG=True・localhost/127.0.0.1のみのローカル環境で実行してください。")

        User = get_user_model()
        with transaction.atomic():
            users = list(User.objects.filter(username__in=USERNAMES))
            restaurants = list(Restaurant.objects.filter(name__in=RESTAURANT_NAMES))
            if users or restaurants:
                # 名前だけで既存データをデモと判断しない。部分的な状態も補修しない。
                owned = (
                    len(users) == 2
                    and {user.username for user in users} == set(USERNAMES)
                    and all(user.email == f"{user.username}@seed-demo.invalid"
                            and not user.is_staff and not user.is_superuser for user in users)
                    and len(restaurants) == 2
                    and {restaurant.name for restaurant in restaurants} == set(RESTAURANT_NAMES)
                    and all(restaurant.description.startswith(f"[{MARKER}]\n")
                            for restaurant in restaurants)
                )
                if not owned:
                    raise CommandError("デモ識別子の衝突または不完全なデータを検出しました。既存データは変更していません。")
                self.stdout.write("デモデータは投入済みです。既存データは変更していません。")
                return

            users = [User.objects.create_user(
                username=username, email=f"{username}@seed-demo.invalid",
                password=PASSWORD, is_staff=False, is_superuser=False,
            ) for username in USERNAMES]
            restaurants = []
            for name, size, address in zip(
                RESTAURANT_NAMES, (10, 20),
                ("東京都渋谷区（架空の店舗）", "東京都新宿区（架空の店舗）"),
            ):
                restaurant = Restaurant(
                    name=name, description=f"[{MARKER}]\n動作確認用の架空の店舗です。",
                    address=address, business_hours="L.O. 21:30（補足案内）",
                    opening_time=time(11), last_reservation_time=time(21),
                    closing_time=time(22), max_party_size=size,
                )
                restaurant.full_clean()
                restaurant.save()
                restaurants.append(restaurant)

            tomorrow = timezone.localdate(timezone=timezone.get_default_timezone()) + timedelta(days=1)
            for user in users:
                for offset, restaurant in enumerate(restaurants):
                    reserved_at = timezone.make_aware(
                        datetime.combine(tomorrow + timedelta(days=offset), time(19)),
                        timezone.get_default_timezone(),
                    )
                    validate_restaurant_accepts_reservations(restaurant)
                    validate_reservation_datetime(restaurant, reserved_at)
                    validate_reservation_party_size(restaurant, 2)
                    reservation = Reservation(
                        user=user, restaurant=restaurant, reserved_at=reserved_at, party_size=2,
                        status=Reservation.Status.CONFIRMED if offset == 0 else Reservation.Status.CANCELLED,
                    )
                    reservation.full_clean()
                    reservation.save()

        self.stdout.write(self.style.SUCCESS("デモユーザー2名・店舗2件・予約4件を投入しました。"))

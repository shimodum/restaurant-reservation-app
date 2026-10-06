from datetime import datetime
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from .management.commands.seed_demo import RESTAURANT_NAMES
from .models import Reservation, Restaurant


@override_settings(DEBUG=True, ALLOWED_HOSTS=["localhost", "127.0.0.1"])
class SeedDemoTests(TestCase):
    def seed(self):
        call_command("seed_demo", stdout=StringIO())

    def snapshot(self):
        return tuple(list(model.objects.order_by("pk").values()) for model in (
            get_user_model(), Restaurant, Reservation,
        ))

    def test_creates_valid_data_and_owned_lists(self):
        now = datetime(2040, 12, 31, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
        with patch("django.utils.timezone.now", return_value=now):
            self.seed()
            self.assertEqual(get_user_model().objects.count(), 2)
            self.assertEqual(Restaurant.objects.count(), 2)
            self.assertEqual(Reservation.objects.count(), 4)
            self.assertEqual(dict(Restaurant.objects.values_list("name", "address")), {
                "【デモ】まちの食堂": "東京都渋谷区（架空の店舗）",
                "【デモ】駅前レストラン": "東京都新宿区（架空の店舗）",
            })
            for restaurant in Restaurant.objects.all():
                restaurant.full_clean()
                self.assertTrue(restaurant.can_accept_reservations)
            for username in ("demo_user1", "demo_user2"):
                user = get_user_model().objects.get(username=username)
                self.assertTrue(user.check_password("demo1234"))
                self.assertNotEqual(user.password, "demo1234")
                self.assertFalse(user.is_staff)
                self.assertFalse(user.is_superuser)
                self.assertTrue(self.client.login(username=username, password="demo1234"))
                response = self.client.get(reverse("reservations:reservation_list"), HTTP_HOST="localhost")
                rows = list(response.context["reservations"])
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(row.user_id == user.pk for row in rows))
                self.assertEqual({row.status for row in rows}, {"confirmed", "cancelled"})
                for row in rows:
                    self.assertGreater(row.reserved_at, now)
                    self.assertEqual(row.reserved_at.astimezone(ZoneInfo("Asia/Tokyo")).hour, 19)
                    self.assertLessEqual(row.party_size, row.restaurant.max_party_size)
                self.assertTrue(next(row for row in rows if row.status == "confirmed").can_cancel)

    def test_rerun_preserves_every_row_and_user_changes(self):
        self.seed()
        user = get_user_model().objects.get(username="demo_user1")
        user.set_password("changed-password")
        user.save()
        reservation = Reservation.objects.filter(status="confirmed").first()
        reservation.status = "cancelled"
        reservation.save()
        restaurant = Restaurant.objects.first()
        restaurant.max_party_size = 5
        restaurant.address = "東京都（デモ用の架空住所）"
        restaurant.save()
        before = self.snapshot()
        with patch("django.utils.timezone.now", return_value=datetime(2090, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo"))):
            self.seed()
        self.assertEqual(self.snapshot(), before)

    def test_username_collision_preserves_existing_data(self):
        get_user_model().objects.create_user(username="demo_user2", password="existing")
        before = self.snapshot()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(self.snapshot(), before)

    def test_restaurant_collision_preserves_existing_data(self):
        Restaurant.objects.create(name=RESTAURANT_NAMES[1], description="既存", address="東京", business_hours="既存")
        before = self.snapshot()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(self.snapshot(), before)

    def test_modified_marker_and_partial_data_stop_safely(self):
        self.seed()
        user = get_user_model().objects.get(username="demo_user1")
        user.email = "existing@example.com"
        user.save()
        before = self.snapshot()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(self.snapshot(), before)
        user.email = "demo_user1@seed-demo.invalid"
        user.save()
        Restaurant.objects.create(name=RESTAURANT_NAMES[0], description="既存", address="東京", business_hours="既存")
        before = self.snapshot()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(self.snapshot(), before)

    def test_unrelated_data_is_unchanged(self):
        user = get_user_model().objects.create_user(username="existing", password="existing")
        restaurant = Restaurant.objects.create(name="既存店舗", description="既存", address="東京", business_hours="既存")
        reservation = Reservation.objects.create(user=user, restaurant=restaurant,
            reserved_at=datetime(2020, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")), party_size=1)
        before = (get_user_model().objects.get(pk=user.pk).__dict__.copy(),
                  Restaurant.objects.get(pk=restaurant.pk).__dict__.copy(),
                  Reservation.objects.get(pk=reservation.pk).__dict__.copy())
        self.seed()
        for model, instance, original in zip((get_user_model(), Restaurant, Reservation),
                                            (user, restaurant, reservation), before):
            actual = model.objects.get(pk=instance.pk).__dict__
            self.assertEqual({key: value for key, value in actual.items() if key != "_state"},
                             {key: value for key, value in original.items() if key != "_state"})

    def test_failure_rolls_back_all_inserts(self):
        before = self.snapshot()
        with patch.object(Reservation, "save", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.seed()
        self.assertEqual(self.snapshot(), before)

    def test_nonlocal_settings_are_rejected_without_writes(self):
        for settings in (
            {"DEBUG": False}, {"ALLOWED_HOSTS": ["*"]},
            {"ALLOWED_HOSTS": ["localhost", "example.com"]}, {"ALLOWED_HOSTS": []},
        ):
            with self.subTest(settings=settings), override_settings(**settings):
                before = self.snapshot()
                with self.assertRaises(CommandError):
                    self.seed()
                self.assertEqual(self.snapshot(), before)

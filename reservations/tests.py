from datetime import datetime, time, timedelta
from itertools import product
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admin import RestaurantAdmin
from .forms import ReservationForm
from .models import Reservation, Restaurant


class RestaurantModelTests(TestCase):
    def test_string_representation_is_name(self):
        restaurant = Restaurant(name="サンプル食堂")

        self.assertEqual(str(restaurant), "サンプル食堂")


    def restaurant(self, **overrides):
        data = dict(name="設定食堂", description="説明", address="東京都", business_hours="L.O. 21:30")
        data.update(overrides)
        return Restaurant(**data)

    def test_booking_defaults_and_valid_settings(self):
        restaurant = self.restaurant()
        restaurant.full_clean()
        self.assertEqual(restaurant.max_party_size, 10)
        self.assertFalse(restaurant.can_accept_reservations)
        for size in (1, 20, 32767):
            restaurant = self.restaurant(opening_time=time(11), last_reservation_time=time(21),
                                         closing_time=time(22), max_party_size=size)
            restaurant.full_clean()
            self.assertTrue(restaurant.can_accept_reservations)

    def test_zero_maximum_blocks_acceptance_without_hours_error(self):
        restaurant = self.restaurant(opening_time=time(11), last_reservation_time=time(21),
                                     closing_time=time(22), max_party_size=0)
        self.assertFalse(restaurant.can_accept_reservations)
        with self.assertRaises(ValidationError) as caught:
            restaurant.full_clean()
        self.assertEqual(set(caught.exception.message_dict), {"max_party_size"})

    def test_partial_hours_are_invalid(self):
        for present in product((False, True), repeat=3):
            if all(present) or not any(present):
                continue
            with self.subTest(present=present):
                values = [value if exists else None for value, exists in zip(
                    (time(11), time(21), time(22)), present)]
                restaurant = self.restaurant(opening_time=values[0], last_reservation_time=values[1],
                                             closing_time=values[2])
                with self.assertRaises(ValidationError):
                    restaurant.full_clean()
                self.assertFalse(restaurant.can_accept_reservations)

    def test_invalid_order_precision_and_maximum(self):
        for opening, last, closing in (
            (time(11), time(11), time(22)), (time(11), time(22), time(22)),
            (time(12), time(11), time(22)), (time(11), time(23), time(22)),
            (time(23), time(0), time(1)), (time(11, 0, 1), time(21), time(22)),
            (time(11), time(21, 0, 1), time(22)), (time(11), time(21), time(22, 0, 1)),
            (time(11), time(21, 0, 0, 1), time(22)),
        ):
            with self.subTest(times=(opening, last, closing)):
                restaurant = self.restaurant(opening_time=opening, last_reservation_time=last,
                                             closing_time=closing)
                with self.assertRaises(ValidationError):
                    restaurant.full_clean()
                self.assertFalse(restaurant.can_accept_reservations)
        for size in (0, -1, 32768):
            with self.subTest(size=size), self.assertRaises(ValidationError):
                self.restaurant(max_party_size=size).full_clean()


class RestaurantViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.first_restaurant = Restaurant.objects.create(
            name="最初の食堂",
            description="家庭料理のお店です。",
            address="東京都渋谷区1-1-1",
            business_hours="11:00〜20:00",
            opening_time=time(11), last_reservation_time=time(19), closing_time=time(20),
        )
        cls.second_restaurant = Restaurant.objects.create(
            name="次のレストラン",
            description="1行目\n2行目",
            address="東京都新宿区2-2-2",
            business_hours="平日 17:00〜22:00\n土日 12:00〜22:00",
            opening_time=time(11), last_reservation_time=time(21), closing_time=time(22),
        )

    def test_restaurant_list_displays_restaurants_in_registration_order(self):
        response = self.client.get(reverse("reservations:restaurant_list"))

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(
            response.context["restaurants"],
            [self.first_restaurant, self.second_restaurant],
        )
        self.assertContains(response, self.first_restaurant.name)
        self.assertContains(response, self.second_restaurant.name)

    def test_restaurant_list_displays_empty_message(self):
        Restaurant.objects.all().delete()

        response = self.client.get(reverse("reservations:restaurant_list"))

        self.assertContains(response, "現在、掲載中の店舗はありません。")

    def test_restaurant_detail_displays_all_fields(self):
        response = self.client.get(
            reverse(
                "reservations:restaurant_detail",
                args=[self.second_restaurant.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.second_restaurant.name)
        self.assertContains(response, "<p>1行目<br>2行目</p>", html=True)
        self.assertContains(response, self.second_restaurant.address)
        self.assertContains(
            response,
            "<dd>平日 17:00〜22:00<br>土日 12:00〜22:00</dd>",
            html=True,
        )

    def test_detail_hides_only_leading_demo_marker_without_changing_database(self):
        description = "[seed_demo:v1]\n1行目\n2行目"
        self.second_restaurant.description = description
        self.second_restaurant.save()
        response = self.client.get(reverse("reservations:restaurant_detail", args=[self.second_restaurant.pk]))
        self.assertNotContains(response, "[seed_demo:v1]")
        self.assertContains(response, "<p>1行目<br>2行目</p>", html=True)
        self.assertEqual(response.context["restaurant"].description, description)
        self.second_restaurant.refresh_from_db()
        self.assertEqual(self.second_restaurant.description, description)

    def test_detail_preserves_ordinary_descriptions_and_nonleading_markers(self):
        for description in (
            "普通の説明\n2行目", "1行目\n[seed_demo:v1]\n2行目",
            " [seed_demo:v1]\n説明", "[seed_demo:v1]説明",
            "[seed_demo:v1]\r\n説明",
        ):
            with self.subTest(description=description):
                self.second_restaurant.description = description
                self.second_restaurant.save()
                response = self.client.get(reverse("reservations:restaurant_detail", args=[self.second_restaurant.pk]))
                self.assertEqual(response.context["restaurant_description"], description)
                if "[seed_demo:v1]" in description:
                    self.assertContains(response, "[seed_demo:v1]")

    def test_demo_photos_are_displayed_in_list_and_detail_without_database_changes(self):
        from django.contrib.staticfiles import finders

        for name, filename in (
            ("【デモ】まちの食堂", "demo-diner.jpg"),
            ("【デモ】駅前レストラン", "demo-restaurant.jpg"),
        ):
            with self.subTest(name=name):
                restaurant = Restaurant.objects.create(
                    name=name, description="[seed_demo:v1]\n説明", address="東京", business_hours="補足",
                )
                original = Restaurant.objects.filter(pk=restaurant.pk).values().get()
                self.assertIsNotNone(finders.find(f"reservations/images/{filename}"))
                for url in (reverse("reservations:restaurant_list"),
                            reverse("reservations:restaurant_detail", args=[restaurant.pk])):
                    response = self.client.get(url)
                    self.assertContains(response, f'/static/reservations/images/{filename}')
                    self.assertContains(response, "架空店舗のイメージ画像です。")
                self.assertEqual(Restaurant.objects.filter(pk=restaurant.pk).values().get(), original)

    def test_ordinary_or_unidentified_restaurants_display_placeholder(self):
        for name, description in (
            ("通常店舗", "説明"), ("【デモ】まちの食堂", "普通の説明"),
            ("【デモ】まちの食堂", "説明\n[seed_demo:v1]\n"),
            ("別の店舗", "[seed_demo:v1]\n説明"),
        ):
            with self.subTest(name=name, description=description):
                self.second_restaurant.name = name
                self.second_restaurant.description = description
                self.second_restaurant.save()
                for url in (reverse("reservations:restaurant_list"),
                            reverse("reservations:restaurant_detail", args=[self.second_restaurant.pk])):
                    response = self.client.get(url)
                    self.assertContains(response, "画像なし")
                    self.assertNotContains(response, "demo-diner.jpg")
                    self.assertNotContains(response, "demo-restaurant.jpg")

    def test_restaurant_detail_returns_404_for_unknown_restaurant(self):
        response = self.client.get(
            reverse("reservations:restaurant_detail", args=[999999])
        )

        self.assertEqual(response.status_code, 404)

    def test_home_links_to_restaurant_list(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("reservations:restaurant_list"))


    def test_booking_information_and_unconfigured_notice(self):
        for url in (reverse("reservations:restaurant_list"),
                    reverse("reservations:restaurant_detail", args=[self.second_restaurant.pk])):
            response = self.client.get(url)
            self.assertContains(response, "11:00〜22:00")
            self.assertContains(response, "最終予約可能時刻")
            self.assertContains(response, "21:00")
            self.assertContains(response, "1予約あたり10人まで")
            self.assertContains(response, "営業時間の補足案内")
        self.second_restaurant.opening_time = None
        self.second_restaurant.last_reservation_time = None
        self.second_restaurant.closing_time = None
        self.second_restaurant.save()
        detail = reverse("reservations:restaurant_detail", args=[self.second_restaurant.pk])
        response = self.client.get(detail)
        self.assertContains(response, "店舗の予約設定が未完了または不正のため、現在予約を受け付けていません。")
        self.assertNotContains(response, reverse("reservations:reservation_create", args=[self.second_restaurant.pk]))
        self.assertContains(self.client.get(reverse("reservations:restaurant_list")),
                            "店舗の予約設定が未完了または不正のため、現在予約を受け付けていません。")


class RestaurantAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )

    def test_restaurant_is_registered_with_expected_configuration(self):
        model_admin = admin.site._registry[Restaurant]

        self.assertIsInstance(model_admin, RestaurantAdmin)
        self.assertEqual(
            model_admin.list_display,
            ("name", "address", "opening_time", "last_reservation_time",
             "closing_time", "max_party_size", "business_hours"),
        )
        self.assertEqual(model_admin.search_fields, ("name", "address"))

    def test_superuser_can_open_restaurant_admin_pages(self):
        self.client.force_login(self.superuser)

        changelist_response = self.client.get(
            reverse("admin:reservations_restaurant_changelist")
        )
        add_response = self.client.get(reverse("admin:reservations_restaurant_add"))

        self.assertEqual(changelist_response.status_code, 200)
        self.assertEqual(add_response.status_code, 200)


    def test_admin_saves_rules_and_rejects_invalid_settings(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:reservations_restaurant_add")
        data = dict(name="管理食堂", description="説明", address="東京都", business_hours="L.O. 21:30",
                    opening_time="11:00", last_reservation_time="21:00", closing_time="22:00",
                    max_party_size="20", _save="保存")
        response = self.client.get(url)
        for field in ("opening_time", "last_reservation_time", "closing_time", "max_party_size"):
            self.assertContains(response, f'name="{field}"')
        for overrides in (dict(last_reservation_time="22:00"), dict(opening_time=""),
                          dict(max_party_size="0"), dict(max_party_size="32768")):
            with self.subTest(overrides=overrides):
                response = self.client.post(url, {**data, **overrides})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
                self.assertFalse(Restaurant.objects.exists())
        self.assertEqual(self.client.post(url, data).status_code, 302)
        restaurant = Restaurant.objects.get()
        self.assertEqual(restaurant.last_reservation_time, time(21))
        self.assertEqual(restaurant.max_party_size, 20)
        change = reverse("admin:reservations_restaurant_change", args=[restaurant.pk])
        self.assertEqual(self.client.post(change, {**data, "last_reservation_time": "20:30"}).status_code, 302)
        restaurant.refresh_from_db()
        self.assertEqual(restaurant.last_reservation_time, time(20, 30))
        self.assertContains(self.client.get(reverse("admin:reservations_restaurant_changelist")), "20:30")
        self.assertEqual(self.client.post(change, {**data, "opening_time": "", "last_reservation_time": "",
                                                "closing_time": ""}).status_code, 302)
        restaurant.refresh_from_db()
        self.assertFalse(restaurant.can_accept_reservations)


class ReservationTests(TestCase):
    # 予約日時の境界は固定時刻で検証する。
    now = datetime(2030, 1, 10, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="member")
        cls.other = get_user_model().objects.create_user(username="other")
        cls.restaurant = Restaurant.objects.create(
            name="予約食堂", description="説明", address="東京都", business_hours="L.O. 19:30",
            opening_time=time(11), last_reservation_time=time(19), closing_time=time(20),
        )
        cls.other_restaurant = Restaurant.objects.create(
            name="別の食堂", description="説明", address="大阪府", business_hours="L.O. 19:30",
            opening_time=time(11), last_reservation_time=time(19), closing_time=time(20),
        )

    def setUp(self):
        self.clock = patch("django.utils.timezone.now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client.force_login(self.user)
        self.create_url = reverse("reservations:reservation_create", args=[self.restaurant.pk])
        self.list_url = reverse("reservations:reservation_list")

    def data(self, **overrides):
        data = {"reserved_at": "2030-01-11T12:00", "party_size": "2"}
        data.update(overrides)
        date, separator, clock = data.pop("reserved_at").partition("T")
        data.update(reserved_at_0=date, reserved_at_1=clock if separator else date)
        return data

    def reserve(self, **overrides):
        data = {
            "user": self.user, "restaurant": self.restaurant,
            "reserved_at": self.now + timedelta(days=1), "party_size": 2,
        }
        data.update(overrides)
        return Reservation.objects.create(**data)

    def cancel_url(self, reservation):
        return reverse("reservations:reservation_cancel", args=[reservation.pk])

    def test_model_defaults_relations_and_delete_protection(self):
        reservation = self.reserve()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertEqual(reservation.get_status_display(), "予約済み")
        self.assertEqual(reservation.created_at, self.now)
        self.assertEqual(self.user.reservations.get(), reservation)
        self.assertEqual(self.restaurant.reservations.get(), reservation)
        for status in Reservation.Status.values:
            reservation.status = status
            reservation.save(update_fields=["status"])
            for owner in (self.user, self.restaurant):
                with self.subTest(status=status, owner=type(owner).__name__):
                    with self.assertRaises(ProtectedError):
                        owner.delete()
        self.assertEqual(reservation.get_status_display(), "キャンセル済み")

    def test_form_fields_and_valid_boundaries(self):
        self.assertEqual(list(ReservationForm(restaurant=self.restaurant).fields), ["reserved_at", "party_size"])
        for size in (1, 10):
            with self.subTest(size=size):
                form = ReservationForm(self.data(party_size=size), restaurant=self.restaurant)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["party_size"], size)
                self.assertEqual(form.cleaned_data["reserved_at"], self.now + timedelta(days=1))
                self.assertTrue(timezone.is_aware(form.cleaned_data["reserved_at"]))

    def test_invalid_form_values_do_not_create_reservations(self):
        cases = [("reserved_at", value) for value in
                 ("2030-01-09T12:00", "2030-01-10T12:00", "", "invalid")]
        cases += [("party_size", value) for value in ("0", "11", "-1", "1.5", "abc", "")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                response = self.client.post(self.create_url, self.data(**{field: value}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertContains(response, 'class="errorlist"')
                if field == "reserved_at":
                    expected = self.data(reserved_at=value)
                    self.assertEqual(response.context["form"][field].value(),
                                     [expected["reserved_at_0"], expected["reserved_at_1"]])
                else:
                    self.assertEqual(response.context["form"].data[field], value)
                self.assertFalse(Reservation.objects.exists())
        response = self.client.post(self.create_url, {})
        self.assertEqual(set(response.context["form"].errors), {"reserved_at", "party_size"})
        self.assertFalse(Reservation.objects.exists())

    def test_reservation_datetime_rejects_invalid_formats_and_dates(self):
        values = [
            "2030-01-11T12:00:00",
            "2030-01-11T12:00:30",
            "2030-01-11T12:00:00.123",
            "2030-01-11T12:00Z",
            "2030-01-11T12:00+09:00",
            "2030-01-11T12:00-09:00",
            "9999-12-31T23:59-09:00",
            "2030-01-11 12:00",
            "2030-1-11T12:00",
            "2030-01-11T2:00",
            " 2030-01-11T12:00",
            "2030-01-11T12:00 ",
            "2030-01-11T12:00\n",
            "２０３０-01-11T12:00",
            "2030-02-30T12:00",
            "2030-01-11T24:00",
        ]
        message = "予約日はYYYY-MM-DD形式の正しい日付を入力し、時刻を選択してください。"
        for value in values:
            with self.subTest(value=value):
                response = self.client.post(self.create_url, self.data(reserved_at=value))
                self.assertEqual(response.status_code, 200)
                form = response.context["form"]
                self.assertEqual(form.errors.as_data()["reserved_at"][0].code, "invalid")
                self.assertEqual(form.errors["reserved_at"], [message])
                self.assertContains(response, message)
                expected = self.data(reserved_at=value)
                self.assertEqual(form["reserved_at"].value(),
                                 [expected["reserved_at_0"], expected["reserved_at_1"]])
                self.assertFalse(Reservation.objects.exists())

    def test_reservation_errors_display_user_friendly_messages(self):
        cases = [
            ("party_size", "0", "人数は1人以上を指定してください。"),
            ("party_size", "11", "人数は10人以下を指定してください。"),
            ("party_size", "", "人数を入力してください。"),
            ("reserved_at", "", "予約日時を入力してください。"),
            ("reserved_at", "2030-01-09T12:00", "予約日時は未来の日時を指定してください。"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                response = self.client.post(self.create_url, self.data(**{field: value}))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["form"].errors[field], [message])
                self.assertContains(
                    response,
                    str(response.context["form"][field].errors),
                    html=True,
                )
                self.assertFalse(Reservation.objects.exists())

    def test_reservation_form_disables_browser_validation_on_get_and_invalid_post(self):
        responses = [
            self.client.get(self.create_url),
            self.client.post(self.create_url, self.data(party_size="0")),
            self.client.post(self.create_url, self.data(party_size="11")),
            self.client.post(self.create_url, self.data(reserved_at="", party_size="")),
        ]
        for response in responses:
            with self.subTest(data=response.context["form"].data):
                self.assertContains(
                    response,
                    f'<form class="auth-form" method="post" action="{self.create_url}" novalidate>',
                )
                self.assertContains(response, 'min="1"')
                self.assertContains(response, 'max="10"')
        empty_form = responses[-1].context["form"]
        for field in ("reserved_at", "party_size"):
            self.assertEqual(empty_form.errors.as_data()[field][0].code, "required")
            self.assertContains(responses[-1], str(empty_form[field].errors), html=True)
        self.assertFalse(Reservation.objects.exists())

    def test_create_get_and_post_ignore_protected_fields(self):
        response = self.client.get(self.create_url)
        self.assertTemplateUsed(response, "reservations/reservation_form.html")
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'min="1"')
        self.assertContains(response, 'max="10"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertFalse(Reservation.objects.exists())
        response = self.client.post(self.create_url, self.data(
            user=self.other.pk, restaurant=self.other_restaurant.pk, status="cancelled"
        ), follow=True)
        self.assertRedirects(response, self.list_url)
        self.assertContains(response, "予約を受け付けました。")
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.user, self.user)
        self.assertEqual(reservation.restaurant, self.restaurant)
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertEqual(reservation.party_size, 2)
        self.assertEqual(reservation.reserved_at, self.now + timedelta(days=1))

    def test_missing_restaurant_returns_404(self):
        url = reverse("reservations:reservation_create", args=[999999])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.data()).status_code, 404)
        self.assertFalse(Reservation.objects.exists())

    def test_login_required_for_all_reservation_views(self):
        reservation = self.reserve()
        self.client.logout()
        for method, url in [("get", self.create_url), ("post", self.create_url),
                            ("get", self.list_url), ("get", self.cancel_url(reservation)),
                            ("post", self.cancel_url(reservation))]:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)
                self.assertRedirects(response, reverse("accounts:login") + "?next=" + url)
        self.assertEqual(Reservation.objects.count(), 1)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)

    def test_list_is_owned_ordered_and_includes_history(self):
        past = self.reserve(reserved_at=self.now - timedelta(days=1))
        future = self.reserve()
        cancelled = self.reserve(status=Reservation.Status.CANCELLED)
        other = self.reserve(user=self.other, restaurant=self.other_restaurant)
        response = self.client.get(self.list_url)
        self.assertTemplateUsed(response, "reservations/reservation_list.html")
        self.assertQuerySetEqual(response.context["reservations"], [cancelled, future, past])
        self.assertContains(response, "予約食堂")
        self.assertContains(response, "2030年1月11日 12:00")
        self.assertContains(response, "2人")
        self.assertContains(response, "予約済み")
        self.assertContains(response, "キャンセル済み")
        self.assertNotContains(response, "別の食堂")
        self.assertContains(response, self.cancel_url(future))
        for reservation in (past, cancelled, other):
            self.assertNotContains(response, self.cancel_url(reservation))

    def test_empty_list(self):
        self.reserve(user=self.other)
        response = self.client.get(self.list_url)
        self.assertContains(response, "予約はまだありません。")
        self.assertContains(response, reverse("reservations:restaurant_list"))

    def test_cancel_changes_only_status_without_deleting(self):
        reservation = self.reserve()
        original = (reservation.user_id, reservation.restaurant_id, reservation.reserved_at,
                    reservation.party_size, reservation.created_at)
        response = self.client.post(self.cancel_url(reservation), follow=True)
        self.assertRedirects(response, self.list_url)
        self.assertContains(response, "予約をキャンセルしました。")
        self.assertEqual(Reservation.objects.count(), 1)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)
        self.assertEqual((reservation.user_id, reservation.restaurant_id, reservation.reserved_at,
                          reservation.party_size, reservation.created_at), original)

    def test_cancel_rejects_past_present_and_cancelled(self):
        for reserved_at, status, message in [
            (self.now - timedelta(seconds=1), Reservation.Status.CONFIRMED, "予約日時を過ぎているため"),
            (self.now, Reservation.Status.CONFIRMED, "予約日時を過ぎているため"),
            (self.now + timedelta(days=1), Reservation.Status.CANCELLED, "すでにキャンセル済み"),
        ]:
            with self.subTest(reserved_at=reserved_at, status=status):
                reservation = self.reserve(reserved_at=reserved_at, status=status)
                self.assertFalse(reservation.can_cancel)
                response = self.client.post(self.cancel_url(reservation), follow=True)
                self.assertRedirects(response, self.list_url)
                self.assertContains(response, message)
                reservation.refresh_from_db()
                self.assertEqual(reservation.status, status)
                self.assertNotContains(response, self.cancel_url(reservation))

    def test_cancel_other_user_or_unknown_returns_404(self):
        other = self.reserve(user=self.other)
        for pk in (other.pk, 999999):
            response = self.client.post(reverse("reservations:reservation_cancel", args=[pk]))
            self.assertEqual(response.status_code, 404)
        other.refresh_from_db()
        self.assertEqual(other.status, Reservation.Status.CONFIRMED)

    def test_http_method_restrictions(self):
        reservation = self.reserve()
        self.assertEqual(self.client.get(self.cancel_url(reservation)).status_code, 405)
        self.assertEqual(self.client.put(self.create_url).status_code, 405)
        self.assertEqual(self.client.post(self.list_url).status_code, 405)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_csrf_for_creation_and_cancellation(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(self.create_url)
        self.assertEqual(client.post(self.create_url, self.data()).status_code, 403)
        self.assertFalse(Reservation.objects.exists())
        data = self.data(csrfmiddlewaretoken=client.cookies["csrftoken"].value)
        self.assertRedirects(client.post(self.create_url, data), self.list_url)
        reservation = Reservation.objects.get()
        self.assertEqual(client.post(self.cancel_url(reservation)).status_code, 403)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertRedirects(client.post(self.cancel_url(reservation), {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }), self.list_url)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)

    def test_detail_navigation_in_both_auth_states(self):
        url = reverse("reservations:restaurant_detail", args=[self.restaurant.pk])
        response = self.client.get(url)
        self.assertContains(response, self.create_url)
        self.assertContains(response, f'href="{self.list_url}"')
        self.client.logout()
        response = self.client.get(url)
        self.assertContains(response, self.create_url)
        self.assertContains(response, "ログインして予約する")
        self.assertContains(response, "店舗一覧からこの店舗を選び直して")
        self.assertNotContains(response, f'href="{self.list_url}"')

    def test_reservation_time_boundaries_and_japan_timezone(self):
        self.restaurant.last_reservation_time = time(21)
        self.restaurant.closing_time = time(22)
        self.restaurant.save()
        for value, allowed in (("10:59", False), ("11:00", True), ("20:30", True),
                               ("21:00", True), ("21:01", False), ("21:59", False), ("22:00", False)):
            with self.subTest(time=value):
                before = Reservation.objects.count()
                response = self.client.post(self.create_url, self.data(reserved_at=f"2030-01-11T{value}"))
                if allowed:
                    self.assertRedirects(response, self.list_url)
                    reservation = Reservation.objects.latest("pk")
                    self.assertEqual(timezone.localtime(reservation.reserved_at).strftime("%H:%M"), value)
                    self.assertEqual(reservation.reserved_at.utcoffset(), timedelta(0))
                else:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("reserved_at", response.context["form"].errors)
                    self.assertContains(response, "11:00以上、21:00以下")
                self.assertEqual(Reservation.objects.count(), before + int(allowed))

    @override_settings(TIME_ZONE="UTC")
    def test_reservation_hours_follow_default_timezone_setting(self):
        form = ReservationForm(self.data(reserved_at="2030-01-11T11:00"),
                               restaurant=self.restaurant)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["reserved_at"].utcoffset(), timedelta(0))
        form = ReservationForm(self.data(reserved_at="2030-01-11T10:59"),
                               restaurant=self.restaurant)
        self.assertFalse(form.is_valid())
        self.assertIn("reserved_at", form.errors)

    def test_reservation_hours_use_default_instead_of_active_timezone(self):
        with timezone.override("UTC"):
            # 入力も判定も設定の日本時間。現在有効なタイムゾーンに依存しない。
            form = ReservationForm(self.data(reserved_at="2030-01-11T11:00"),
                                   restaurant=self.restaurant)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["reserved_at"].utcoffset(), timedelta(hours=9))
            form = ReservationForm(self.data(reserved_at="2030-01-11T10:59"),
                                   restaurant=self.restaurant)
            self.assertFalse(form.is_valid())
            self.assertIn("reserved_at", form.errors)

    def test_zero_maximum_in_database_blocks_get_and_post(self):
        Restaurant.objects.filter(pk=self.restaurant.pk).update(max_party_size=0)
        self.restaurant.refresh_from_db()
        self.assertFalse(self.restaurant.can_accept_reservations)
        notice = "店舗の予約設定が未完了または不正のため、現在予約を受け付けていません。"
        detail_url = reverse("reservations:restaurant_detail", args=[self.restaurant.pk])
        for url in (reverse("reservations:restaurant_list"), detail_url):
            response = self.client.get(url)
            self.assertContains(response, notice)
            self.assertNotContains(response, self.create_url)
        for response in (self.client.get(self.create_url),
                         self.client.post(self.create_url, self.data(party_size=1))):
            self.assertContains(response, notice)
            self.assertNotContains(response, "人数は1〜0人")
            self.assertNotContains(response, 'name="reserved_at"')
            self.assertNotContains(response, 'name="party_size"')
        self.assertIn(notice, response.context["form"].non_field_errors())
        self.assertFalse(Reservation.objects.exists())

    def test_party_size_uses_restaurant_limit_and_dynamic_display(self):
        for maximum, sizes in ((20, ((1, True), (20, True), (21, False))),
                               (1, ((1, True), (2, False)))):
            self.restaurant.max_party_size = maximum
            self.restaurant.save()
            response = self.client.get(self.create_url)
            self.assertContains(response, f'max="{maximum}"')
            self.assertContains(response, f"人数は1〜{maximum}人")
            for size, allowed in sizes:
                with self.subTest(maximum=maximum, size=size):
                    before = Reservation.objects.count()
                    response = self.client.post(self.create_url, self.data(party_size=size))
                    if allowed:
                        self.assertRedirects(response, self.list_url)
                        self.assertEqual(Reservation.objects.latest("pk").party_size, size)
                    else:
                        self.assertContains(response, f"人数は{maximum}人以下を指定してください。")
                        self.assertContains(response, f'max="{maximum}"')
                        self.assertEqual(response.context["form"].data["party_size"], str(size))
                    self.assertEqual(Reservation.objects.count(), before + int(allowed))

    def test_post_cannot_override_restaurant_rules(self):
        self.other_restaurant.max_party_size = 20
        self.other_restaurant.last_reservation_time = time(21)
        self.other_restaurant.closing_time = time(22)
        self.other_restaurant.save()
        forged = self.data(reserved_at="2030-01-11T21:00", party_size="20",
                           restaurant=self.other_restaurant.pk, opening_time="00:00",
                           last_reservation_time="23:59", closing_time="23:59", max_party_size="20")
        response = self.client.post(self.create_url, forged)
        self.assertEqual(set(response.context["form"].errors), {"reserved_at", "party_size"})
        self.assertFalse(Reservation.objects.exists())
        other_url = reverse("reservations:reservation_create", args=[self.other_restaurant.pk])
        self.assertRedirects(self.client.post(other_url, forged), self.list_url)
        self.assertEqual(Reservation.objects.get().restaurant, self.other_restaurant)

    def test_unconfigured_or_invalid_restaurant_blocks_get_and_post(self):
        for opening, last, closing in ((None, None, None), (time(11), None, time(22)),
                                       (time(11), time(22), time(22))):
            with self.subTest(times=(opening, last, closing)):
                self.restaurant.opening_time = opening
                self.restaurant.last_reservation_time = last
                self.restaurant.closing_time = closing
                self.restaurant.save()
                for response in (self.client.get(self.create_url),
                                 self.client.post(self.create_url, self.data())):
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "店舗の予約設定が未完了または不正のため、現在予約を受け付けていません。")
                    self.assertNotContains(response, 'name="reserved_at"')
                self.assertTrue(response.context["form"].non_field_errors())
                self.assertFalse(Reservation.objects.exists())

    def test_last_order_note_does_not_control_reservations(self):
        for note in ("L.O. 11:30", "L.O. 23:00", "曜日別の案内\n任意の補足"):
            with self.subTest(note=note):
                self.restaurant.business_hours = note
                self.restaurant.save()
                self.assertRedirects(self.client.post(self.create_url, self.data(reserved_at="2030-01-11T19:00")),
                                     self.list_url)
                before = Reservation.objects.count()
                response = self.client.post(self.create_url, self.data(reserved_at="2030-01-11T19:01"))
                self.assertIn("reserved_at", response.context["form"].errors)
                self.assertEqual(Reservation.objects.count(), before)

    def test_settings_changes_preserve_existing_reservation_and_cancellation(self):
        reservation = self.reserve(party_size=10)
        original = (reservation.reserved_at, reservation.party_size, reservation.created_at)
        self.restaurant.opening_time = time(15)
        self.restaurant.last_reservation_time = time(16)
        self.restaurant.closing_time = time(17)
        self.restaurant.max_party_size = 1
        self.restaurant.save()
        self.assertContains(self.client.get(self.list_url), "10人")
        self.assertRedirects(self.client.post(self.cancel_url(reservation)), self.list_url)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)
        self.assertEqual((reservation.reserved_at, reservation.party_size, reservation.created_at), original)

    def test_half_hour_creation_and_future_boundary(self):
        for clock in ("12:00", "12:30"):
            self.assertRedirects(self.client.post(self.create_url, self.data(
                reserved_at=f"2030-01-11T{clock}"
            )), self.list_url)
        self.assertEqual(Reservation.objects.count(), 2)
        for clock, allowed in (("11:30", False), ("12:00", False), ("12:30", True)):
            form = ReservationForm(self.data(reserved_at=f"2030-01-10T{clock}"), restaurant=self.restaurant)
            self.assertEqual(form.is_valid(), allowed)

    def test_half_hour_choices_and_invalid_minutes(self):
        for clock in ("12:00", "12:30", "12:01", "19:17"):
            with self.subTest(clock=clock):
                form = ReservationForm(self.data(reserved_at=f"2030-01-11T{clock}"), restaurant=self.restaurant)
                self.assertEqual(form.is_valid(), clock in ("12:00", "12:30"))
        self.restaurant.opening_time = time(11, 15)
        self.restaurant.last_reservation_time = time(19, 15)
        self.restaurant.save()
        response = self.client.get(self.create_url)
        choices = response.context["form"].fields["reserved_at"].widget.widgets[1].choices
        self.assertEqual(choices[1], ("11:30", "11:30"))
        self.assertEqual(choices[-1], ("19:00", "19:00"))
        expected = [
            (f"{hour:02d}:{minute:02d}", f"{hour:02d}:{minute:02d}")
            for hour in range(11, 20) for minute in (0, 30)
            if (hour, minute) >= (11, 30) and (hour, minute) <= (19, 0)
        ]
        self.assertEqual(list(choices), [("", "時刻を選択してください"), *expected])
        for clock, valid in (("11:00", False), ("11:15", False), ("11:30", True),
                             ("19:00", True), ("19:15", False), ("19:30", False)):
            form = ReservationForm(self.data(reserved_at=f"2030-01-11T{clock}"), restaurant=self.restaurant)
            self.assertEqual(form.is_valid(), valid)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.opening_time, time(11, 15))
        self.assertEqual(self.restaurant.last_reservation_time, time(19, 15))

    def test_no_choices_blocks_form_and_post(self):
        self.restaurant.opening_time = time(11, 5)
        self.restaurant.last_reservation_time = time(11, 20)
        self.restaurant.save()
        for response in (self.client.get(self.create_url), self.client.post(self.create_url, self.data())):
            self.assertContains(response, "この店舗には予約可能な時刻がありません。")
            self.assertNotContains(response, '<button class="button" type="submit">予約する</button>')
        self.assertFalse(Reservation.objects.exists())

    def test_single_choice_and_choices_are_isolated_per_form(self):
        self.restaurant.opening_time = time(11, 15)
        self.restaurant.last_reservation_time = time(11, 45)
        form = ReservationForm(restaurant=self.restaurant)
        choices = form.fields["reserved_at"].widget.widgets[1].choices
        self.assertEqual(list(choices), [("", "時刻を選択してください"), ("11:30", "11:30")])
        ReservationForm(restaurant=self.other_restaurant)
        self.assertEqual(list(form.fields["reserved_at"].widget.widgets[1].choices), list(choices))

    def test_future_validation_uses_japan_time_with_utc_active(self):
        with timezone.override("UTC"):
            for clock, valid in (("11:30", False), ("12:00", False), ("12:30", True)):
                with self.subTest(clock=clock):
                    form = ReservationForm(self.data(reserved_at=f"2030-01-10T{clock}"),
                                           restaurant=self.restaurant)
                    self.assertEqual(form.is_valid(), valid)
                    if valid:
                        self.assertEqual(form.cleaned_data["reserved_at"].utcoffset(), timedelta(hours=9))

    def test_split_input_redisplay_and_missing_parts(self):
        response = self.client.post(self.create_url, self.data(reserved_at="2030-01-11T12:30", party_size="0"))
        self.assertContains(response, 'value="2030-01-11"')
        self.assertContains(response, '<option value="12:30" selected>12:30</option>', html=True)
        self.assertContains(response, 'name="reserved_at_0"')
        self.assertContains(response, 'name="reserved_at_1"')
        for field in ("reserved_at_0", "reserved_at_1"):
            data = self.data()
            data[field] = ""
            form = ReservationForm(data, restaurant=self.restaurant)
            self.assertFalse(form.is_valid())
            self.assertIn("reserved_at", form.errors)

    def test_legacy_quarter_hour_reservation_keeps_data_on_cancel(self):
        reservation = self.reserve(reserved_at=self.now + timedelta(days=1, minutes=15))
        original = (reservation.reserved_at, reservation.user_id, reservation.restaurant_id,
                    reservation.party_size, reservation.created_at)
        self.assertContains(self.client.get(self.list_url), "12:15")
        self.assertRedirects(self.client.post(self.cancel_url(reservation)), self.list_url)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)
        self.assertEqual(original, (reservation.reserved_at, reservation.user_id, reservation.restaurant_id,
                                   reservation.party_size, reservation.created_at))


class BookingRulesMigrationTests(TransactionTestCase):
    def test_existing_restaurant_and_reservation_are_preserved(self):
        # Migrationの巻き戻しはDjangoが作成した専用テストDBだけで行う。
        previous = [("reservations", "0002_reservation")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(previous)
            old_apps = executor.loader.project_state(previous).apps
            User = old_apps.get_model("auth", "User")
            OldRestaurant = old_apps.get_model("reservations", "Restaurant")
            OldReservation = old_apps.get_model("reservations", "Reservation")
            user = User.objects.create(username="migration-member")
            restaurant = OldRestaurant.objects.create(name="既存食堂", description="既存説明",
                                                     address="東京都", business_hours="L.O. 21:30\n補足")
            reservation = OldReservation.objects.create(user=user, restaurant=restaurant,
                reserved_at=datetime(2030, 1, 11, 12, tzinfo=ZoneInfo("Asia/Tokyo")), party_size=10)
            OldReservation.objects.create(user=user, restaurant=restaurant,
                reserved_at=datetime(2020, 1, 11, 12, tzinfo=ZoneInfo("Asia/Tokyo")),
                party_size=2, status="cancelled")
            old_restaurants = list(OldRestaurant.objects.values("id", "name", "description", "address", "business_hours"))
            old_reservations = list(OldReservation.objects.values())
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            self.assertEqual(list(Restaurant.objects.values("id", "name", "description", "address", "business_hours")), old_restaurants)
            migrated = Restaurant.objects.get(pk=restaurant.pk)
            self.assertIsNone(migrated.opening_time)
            self.assertIsNone(migrated.last_reservation_time)
            self.assertIsNone(migrated.closing_time)
            self.assertEqual(migrated.max_party_size, 10)
            self.assertEqual(list(Reservation.objects.values()), old_reservations)
            self.assertEqual(Reservation.objects.get(pk=reservation.pk).restaurant_id, restaurant.pk)
        finally:
            MigrationExecutor(connection).migrate(latest)

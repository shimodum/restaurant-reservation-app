from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import RestaurantAdmin
from .forms import ReservationForm
from .models import Reservation, Restaurant


class RestaurantModelTests(TestCase):
    def test_string_representation_is_name(self):
        restaurant = Restaurant(name="サンプル食堂")

        self.assertEqual(str(restaurant), "サンプル食堂")


class RestaurantViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.first_restaurant = Restaurant.objects.create(
            name="最初の食堂",
            description="家庭料理のお店です。",
            address="東京都渋谷区1-1-1",
            business_hours="11:00〜20:00",
        )
        cls.second_restaurant = Restaurant.objects.create(
            name="次のレストラン",
            description="1行目\n2行目",
            address="東京都新宿区2-2-2",
            business_hours="平日 17:00〜22:00\n土日 12:00〜22:00",
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

    def test_restaurant_detail_returns_404_for_unknown_restaurant(self):
        response = self.client.get(
            reverse("reservations:restaurant_detail", args=[999999])
        )

        self.assertEqual(response.status_code, 404)

    def test_home_links_to_restaurant_list(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("reservations:restaurant_list"))


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
            ("name", "address", "business_hours"),
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


class ReservationTests(TestCase):
    # 予約日時の境界は固定時刻で検証する。
    now = datetime(2030, 1, 10, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="member")
        cls.other = get_user_model().objects.create_user(username="other")
        cls.restaurant = Restaurant.objects.create(
            name="予約食堂", description="説明", address="東京都", business_hours="11〜20時"
        )
        cls.other_restaurant = Restaurant.objects.create(
            name="別の食堂", description="説明", address="大阪府", business_hours="11〜20時"
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
        self.assertEqual(list(ReservationForm().fields), ["reserved_at", "party_size"])
        for size in (1, 10):
            with self.subTest(size=size):
                form = ReservationForm(self.data(party_size=size))
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
                self.assertEqual(response.context["form"].data[field], value)
                self.assertFalse(Reservation.objects.exists())
        response = self.client.post(self.create_url, {})
        self.assertEqual(set(response.context["form"].errors), {"reserved_at", "party_size"})
        self.assertFalse(Reservation.objects.exists())

    def test_create_get_and_post_ignore_protected_fields(self):
        response = self.client.get(self.create_url)
        self.assertTemplateUsed(response, "reservations/reservation_form.html")
        self.assertContains(response, 'type="datetime-local"')
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

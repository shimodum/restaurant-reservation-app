import json

from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Reservation, Restaurant


class ReservationAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="api-member", password="test-password")
        self.other = get_user_model().objects.create_user(username="other-member")
        self.restaurant = Restaurant.objects.create(
            name="食堂", description="説明", address="東京", business_hours="L.O. 11:30",
            opening_time=time(11), last_reservation_time=time(21), closing_time=time(22),
            max_party_size=10,
        )
        self.now = datetime(2030, 1, 10, 12, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.clock = patch("django.utils.timezone.now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client = APIClient()
        self.client.force_login(self.user)
        self.url = reverse("reservations_api:reservation_list_create")

    def data(self, **overrides):
        data = {"restaurant": self.restaurant.pk, "reserved_at": "2030-01-11T19:00", "party_size": 2}
        data.update(overrides)
        return data

    def reserve(self, **overrides):
        data = dict(user=self.user, restaurant=self.restaurant,
                    reserved_at=self.now + timedelta(days=1), party_size=2)
        data.update(overrides)
        return Reservation.objects.create(**data)

    def cancel_url(self, reservation):
        return reverse("reservations_api:reservation_cancel", args=[reservation.pk])

    def post(self, **overrides):
        return self.client.post(self.url, self.data(**overrides), format="json")

    def test_login_required_for_every_operation(self):
        reservation = self.reserve()
        self.client.logout()
        for method, url in (("get", self.url), ("post", self.url),
                            ("delete", self.cancel_url(reservation))):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(Reservation.objects.count(), 1)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)

    def test_list_is_owned_ordered_and_includes_history(self):
        past = self.reserve(reserved_at=self.now - timedelta(days=1))
        future = self.reserve()
        cancelled = self.reserve(status=Reservation.Status.CANCELLED)
        self.reserve(user=self.other)
        for staff in (False, True):
            self.user.is_staff = staff
            self.user.is_superuser = staff
            self.user.save()
            response = self.client.get(self.url, {"user": self.other.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row["id"] for row in response.json()],
                             [cancelled.pk, future.pk, past.pk])
            self.assertNotIn("user", response.json()[0])
            self.assertEqual(response.json()[0]["reserved_at"], "2030-01-11T12:00:00+09:00")

    def test_empty_list(self):
        self.reserve(user=self.other)
        self.assertEqual(self.client.get(self.url).json(), [])

    def test_create_ignores_protected_values_and_appears_in_html(self):
        response = self.post(user=self.other.pk, status="cancelled", id=999,
                             created_at="2000-01-01T00:00", max_party_size=100)
        self.assertEqual(response.status_code, 201)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.user, self.user)
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertNotEqual(reservation.pk, 999)
        self.assertEqual(reservation.created_at, self.now)
        self.assertEqual(reservation.restaurant, self.restaurant)
        self.assertEqual(response.json()["reserved_at"], "2030-01-11T19:00:00+09:00")
        self.assertContains(self.client.get(reverse("reservations:reservation_list")), "食堂")
        result = self.client.post(reverse("reservations:reservation_cancel", args=[reservation.pk]))
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.client.get(self.url).json()[0]["status"], "cancelled")

    def test_html_creation_can_be_listed_and_cancelled_by_api(self):
        response = self.client.post(reverse("reservations:reservation_create", args=[self.restaurant.pk]),
                                    {"reserved_at_0": "2030-01-11", "reserved_at_1": "19:00", "party_size": 2})
        self.assertEqual(response.status_code, 302)
        reservation = Reservation.objects.get()
        self.assertEqual(self.client.get(self.url).json()[0]["id"], reservation.pk)
        self.assertEqual(self.client.delete(self.cancel_url(reservation)).status_code, 204)
        self.assertContains(self.client.get(reverse("reservations:reservation_list")), "キャンセル済み")

    def test_required_and_invalid_fields(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"restaurant", "reserved_at", "party_size"})
        for overrides, field in (({"restaurant": 999999}, "restaurant"),
                                 ({"restaurant": None}, "restaurant"),
                                 ({"party_size": 0}, "party_size"),
                                 ({"party_size": -1}, "party_size"),
                                 ({"party_size": 1.5}, "party_size"),
                                 ({"party_size": True}, "party_size"),
                                 ({"party_size": "abc"}, "party_size"),
                                 ({"party_size": 32768}, "party_size")):
            with self.subTest(overrides=overrides):
                response = self.post(**overrides)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertFalse(Reservation.objects.exists())

    def test_restaurant_requires_json_integer_without_changing_reservations(self):
        self.reserve()
        original = list(Reservation.objects.values())
        # 生のJSONで指数表記と整数・小数・文字列の違いを検証する。
        for value in ("7.0", "1.5", '"7"', "true", "1e309",
                      str(float(self.restaurant.pk)), json.dumps(str(self.restaurant.pk))):
            with self.subTest(value=value):
                body = json.dumps(self.data()).replace(
                    f'"restaurant": {self.restaurant.pk}', f'"restaurant": {value}', 1
                )
                response = self.client.post(self.url, body, content_type="application/json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(set(response.json()), {"restaurant"})
                self.assertTrue(response.json()["restaurant"])
                self.assertEqual(Reservation.objects.count(), len(original))
                self.assertEqual(list(Reservation.objects.values()), original)
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["restaurant"], self.restaurant.pk)
        self.assertEqual(Reservation.objects.count(), len(original) + 1)

    def test_datetime_format_is_strict(self):
        for value in ("2030-01-11T19:00:00", "2030-01-11T19:00+09:00", "2030-01-11T19:00Z",
                      " 2030-01-11T19:00", "2030-01-11T19:00 ", "2030-1-11T19:00",
                      "2030-01-11 19:00", "2030-02-30T19:00", "2030-01-11T24:00",
                      "9999-12-31T23:59+23:59", 123, None, "", "２０３０-01-11T19:00"):
            with self.subTest(value=value):
                response = self.post(reserved_at=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn("reserved_at", response.json())
        self.assertFalse(Reservation.objects.exists())

    def test_future_present_and_past(self):
        for value in ("2030-01-10T11:59", "2030-01-10T12:00"):
            self.assertEqual(self.post(reserved_at=value).status_code, 400)
        self.assertEqual(self.post(reserved_at="2030-01-10T12:30").status_code, 201)

    def test_hours_boundaries_and_forged_settings(self):
        for value, allowed in (("10:59", False), ("11:00", True), ("20:30", True),
                               ("21:00", True), ("21:01", False), ("21:59", False), ("22:00", False)):
            with self.subTest(value=value):
                before = Reservation.objects.count()
                response = self.post(reserved_at=f"2030-01-11T{value}", opening_time="00:00",
                                     last_reservation_time="23:59", closing_time="23:59")
                self.assertEqual(response.status_code, 201 if allowed else 400)
                self.assertEqual(Reservation.objects.count(), before + int(allowed))

    def test_party_size_follows_selected_restaurant(self):
        other = Restaurant.objects.create(name="別店", description="説明", address="東京",
            business_hours="補足", opening_time=time(17), last_reservation_time=time(20),
            closing_time=time(22), max_party_size=20)
        for restaurant, maximum in ((self.restaurant, 10), (other, 20)):
            for size, expected in ((1, 201), (maximum, 201), (maximum + 1, 400)):
                with self.subTest(restaurant=restaurant.pk, size=size):
                    self.assertEqual(self.post(restaurant=restaurant.pk, party_size=size,
                                              max_party_size=100).status_code, expected)
        self.assertEqual(self.post(restaurant=other.pk, reserved_at="2030-01-11T11:00").status_code, 400)

    def test_unconfigured_and_invalid_restaurants_cannot_accept(self):
        for opening, last, closing, maximum in (
            (None, None, None, 10), (time(11), None, time(22), 10),
            (time(11), time(22), time(22), 10), (time(23), time(0), time(1), 10),
            (time(11, 0, 1), time(21), time(22), 10), (time(11), time(21), time(22), 0),
        ):
            with self.subTest(settings=(opening, last, closing, maximum)):
                Restaurant.objects.filter(pk=self.restaurant.pk).update(
                    opening_time=opening, last_reservation_time=last,
                    closing_time=closing, max_party_size=maximum)
                response = self.post()
                self.assertEqual(response.status_code, 400)
                self.assertIn("non_field_errors", response.json())
        self.assertFalse(Reservation.objects.exists())

    def test_validation_reports_both_business_field_errors(self):
        response = self.post(reserved_at="2030-01-11T22:00", party_size=11)
        self.assertEqual(set(response.json()), {"reserved_at", "party_size"})

    def test_api_interprets_and_outputs_default_timezone(self):
        with timezone.override("UTC"):
            response = self.post(reserved_at="2030-01-11T11:00")
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["reserved_at"], "2030-01-11T11:00:00+09:00")
            self.assertEqual(self.client.get(self.url).json()[0]["created_at"], "2030-01-10T12:00:00+09:00")

    def test_cancel_changes_only_status_without_deleting(self):
        reservation = self.reserve()
        original = Reservation.objects.values().get(pk=reservation.pk)
        response = self.client.delete(self.cancel_url(reservation), {"user": self.other.pk}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        original["status"] = Reservation.Status.CANCELLED
        self.assertEqual(Reservation.objects.values().get(pk=reservation.pk), original)

    def test_cancel_other_or_missing_is_404(self):
        other = self.reserve(user=self.other)
        for pk in (other.pk, 999999):
            url = reverse("reservations_api:reservation_cancel", args=[pk])
            self.assertEqual(self.client.delete(url).status_code, 404)
        other.refresh_from_db()
        self.assertEqual(other.status, Reservation.Status.CONFIRMED)

    def test_cancel_present_past_or_cancelled_is_conflict(self):
        for overrides in ({"reserved_at": self.now}, {"reserved_at": self.now - timedelta(seconds=1)},
                          {"status": Reservation.Status.CANCELLED}):
            reservation = self.reserve(**overrides)
            original = Reservation.objects.values().get(pk=reservation.pk)
            response = self.client.delete(self.cancel_url(reservation))
            self.assertEqual(response.status_code, 409)
            self.assertIn("detail", response.json())
            self.assertEqual(Reservation.objects.values().get(pk=reservation.pk), original)

    def test_settings_changes_do_not_prevent_list_or_cancellation(self):
        reservation = self.reserve(party_size=10)
        Restaurant.objects.filter(pk=self.restaurant.pk).update(
            opening_time=None, last_reservation_time=None, closing_time=None, max_party_size=1)
        self.assertEqual(self.client.get(self.url).json()[0]["party_size"], 10)
        self.assertEqual(self.client.delete(self.cancel_url(reservation)).status_code, 204)

    def test_method_restrictions_and_safe_methods(self):
        reservation = self.reserve()
        detail = self.cancel_url(reservation)
        for method, url in (("delete", self.url), ("put", self.url), ("patch", self.url),
                            ("get", detail), ("post", detail), ("put", detail), ("patch", detail)):
            self.assertEqual(getattr(self.client, method)(url).status_code, 405)
        self.assertEqual(self.client.head(self.url).status_code, 200)
        self.assertEqual(self.client.options(self.url).status_code, 200)
        self.assertEqual(self.client.options(detail).status_code, 200)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)

    def test_json_only_and_malformed_json(self):
        self.assertEqual(self.client.post(self.url, self.data()).status_code, 415)
        self.assertEqual(self.client.post(self.url, '{', content_type="application/json").status_code, 400)
        self.assertFalse(Reservation.objects.exists())

    def test_session_csrf_for_post_and_delete(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertTrue(client.login(username=self.user.username, password="test-password"))
        reservation = self.reserve()
        self.assertEqual(client.post(self.url, self.data(), format="json").status_code, 403)
        self.assertEqual(client.delete(self.cancel_url(reservation)).status_code, 403)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertEqual(Reservation.objects.count(), 1)
        client.get(reverse("reservations:reservation_create", args=[self.restaurant.pk]))
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.url, self.data(), format="json", HTTP_X_CSRFTOKEN="invalid").status_code, 403)
        self.assertEqual(client.post(self.url, self.data(), format="json", HTTP_X_CSRFTOKEN=token).status_code, 201)
        self.assertEqual(client.delete(self.cancel_url(reservation), HTTP_X_CSRFTOKEN=token).status_code, 204)

    def test_half_hour_and_fractional_restaurant_boundaries(self):
        self.restaurant.opening_time = time(11, 15)
        self.restaurant.last_reservation_time = time(19, 15)
        self.restaurant.save()
        for clock, expected in (("11:00", 400), ("11:15", 400), ("11:30", 201),
                                ("12:00", 201), ("12:30", 201), ("12:01", 400),
                                ("19:00", 201), ("19:15", 400), ("19:17", 400), ("19:30", 400)):
            with self.subTest(clock=clock):
                self.assertEqual(self.post(reserved_at=f"2030-01-11T{clock}").status_code, expected)

    def test_non_half_hour_within_hours_returns_field_error(self):
        for clock in ("12:01", "19:17"):
            with self.subTest(clock=clock):
                response = self.post(reserved_at=f"2030-01-11T{clock}")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["reserved_at"],
                                 ["予約時刻は毎時00分・30分を選択してください。"])
        self.assertFalse(Reservation.objects.exists())

    def test_no_choices_rejects_api_creation(self):
        self.restaurant.opening_time = time(11, 5)
        self.restaurant.last_reservation_time = time(11, 20)
        self.restaurant.save()
        response = self.post(reserved_at="2030-01-11T11:00")
        self.assertEqual(response.status_code, 400)
        self.assertIn("この店舗には予約可能な時刻がありません。", response.json()["non_field_errors"])
        self.assertFalse(Reservation.objects.exists())

    def test_future_validation_uses_japan_time_with_utc_active(self):
        with timezone.override("UTC"):
            for clock, expected in (("11:30", 400), ("12:00", 400), ("12:30", 201)):
                with self.subTest(clock=clock):
                    response = self.post(reserved_at=f"2030-01-10T{clock}")
                    self.assertEqual(response.status_code, expected)
                    if expected == 201:
                        self.assertEqual(response.json()["reserved_at"], "2030-01-10T12:30:00+09:00")

    def test_legacy_quarter_hour_can_be_listed_and_cancelled(self):
        reservation = self.reserve(reserved_at=self.now + timedelta(days=1, minutes=15))
        original = (reservation.reserved_at, reservation.user_id, reservation.restaurant_id,
                    reservation.party_size, reservation.created_at)
        self.assertIn("12:15:00+09:00", self.client.get(self.url).json()[0]["reserved_at"])
        self.assertEqual(self.client.delete(self.cancel_url(reservation)).status_code, 204)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)
        self.assertEqual(original, (reservation.reserved_at, reservation.user_id, reservation.restaurant_id,
                                   reservation.party_size, reservation.created_at))

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .admin import RestaurantAdmin
from .models import Restaurant


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

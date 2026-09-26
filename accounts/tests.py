from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from reservations.models import Restaurant


class AccountTests(TestCase):
    password = "Mvp-test!47-river"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="member", password=cls.password)
        cls.restaurant = Restaurant.objects.create(
            name="テスト食堂",
            description="家庭料理",
            address="東京都",
            business_hours="11:00〜20:00",
        )

    def signup_data(self, **overrides):
        data = {
            "username": "newmember",
            "password1": self.password,
            "password2": self.password,
        }
        data.update(overrides)
        return data

    def test_auth_pages_display_forms(self):
        for name, template, fields in [
            ("signup", "accounts/signup.html", ("username", "password1", "password2")),
            ("login", "accounts/login.html", ("username", "password")),
        ]:
            with self.subTest(page=name):
                response = self.client.get(reverse(f"accounts:{name}"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)
                for field in fields:
                    self.assertContains(response, f'name="{field}"')
                self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_signup_creates_regular_user_without_logging_in(self):
        response = self.client.post(reverse("accounts:signup"), self.signup_data())
        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get(username="newmember")
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_invalid_signup_does_not_create_user(self):
        cases = [
            ({}, "username", "required"),
            (self.signup_data(username="member"), "username", "unique"),
            (self.signup_data(password2="different"), "password2", "password_mismatch"),
            (self.signup_data(password1="123", password2="123"), "password2", "password_too_short"),
        ]
        for data, field, code in cases:
            with self.subTest(code=code):
                response = self.client.post(reverse("accounts:signup"), data)
                self.assertEqual(response.status_code, 200)
                errors = response.context["form"].errors.as_data()
                self.assertIn(code, [error.code for error in errors[field]])
                self.assertContains(response, 'class="errorlist"')
                self.assertEqual(User.objects.count(), 1)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_authenticates_and_redirects_home(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.username, "password": self.password},
        )
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_invalid_credentials_and_inactive_user_cannot_login(self):
        for username, password, active in [
            ("missing", self.password, True),
            ("member", "wrong", True),
            ("member", self.password, False),
        ]:
            with self.subTest(username=username, active=active):
                self.user.is_active = active
                self.user.save(update_fields=["is_active"])
                response = self.client.post(
                    reverse("accounts:login"),
                    {"username": username, "password": password},
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].non_field_errors())
                self.assertContains(response, "errorlist nonfield")
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_user_is_redirected_from_auth_pages(self):
        self.client.force_login(self.user)
        for name in ("signup", "login"):
            with self.subTest(page=name):
                self.assertRedirects(
                    self.client.get(reverse(f"accounts:{name}")), reverse("home")
                )
        response = self.client.post(reverse("accounts:signup"), self.signup_data())
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(User.objects.count(), 1)

    def test_logout_requires_post_and_clears_session(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertRedirects(
            self.client.post(reverse("accounts:logout")), reverse("home")
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_anonymous_logout_redirects_home(self):
        self.assertRedirects(
            self.client.post(reverse("accounts:logout")), reverse("home")
        )

    def test_next_never_overrides_home_redirect(self):
        for action in ("login", "logout"):
            for location in ("query", "body"):
                for target in ("/restaurants/", "https://example.com/"):
                    with self.subTest(action=action, location=location, target=target):
                        client = Client()
                        url = reverse(f"accounts:{action}")
                        data = {"username": self.user.username, "password": self.password}
                        if action == "logout":
                            client.force_login(self.user)
                        if location == "query":
                            url += f"?next={target}"
                        else:
                            data["next"] = target
                        self.assertRedirects(client.post(url, data), reverse("home"))

    def test_shared_navigation_and_restaurants_in_both_auth_states(self):
        urls = [
            reverse("home"),
            reverse("reservations:restaurant_list"),
            reverse("reservations:restaurant_detail", args=[self.restaurant.pk]),
        ]
        for authenticated in (False, True):
            if authenticated:
                self.client.force_login(self.user)
            for url in urls:
                with self.subTest(authenticated=authenticated, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    if url != reverse("home"):
                        self.assertContains(response, self.restaurant.name)
                    if authenticated:
                        self.assertContains(response, self.user.username)
                        self.assertContains(response, reverse("accounts:logout"))
                        self.assertNotContains(response, reverse("accounts:signup"))
                        self.assertNotContains(response, reverse("accounts:login"))
                    else:
                        self.assertContains(response, reverse("accounts:signup"))
                        self.assertContains(response, reverse("accounts:login"))
                        self.assertNotContains(response, reverse("accounts:logout"))

    def test_csrf_required_for_all_auth_posts(self):
        for action in ("signup", "login", "logout"):
            with self.subTest(action=action):
                client = Client(enforce_csrf_checks=True)
                url = reverse(f"accounts:{action}")
                data = (
                    self.signup_data() if action == "signup"
                    else {"username": self.user.username, "password": self.password}
                )
                if action == "logout":
                    client.force_login(self.user)
                client.get(reverse("home") if action == "logout" else url)
                count = User.objects.count()
                self.assertEqual(client.post(url, data).status_code, 403)
                self.assertEqual(User.objects.count(), count)
                if action == "logout":
                    self.assertIn("_auth_user_id", client.session)
                else:
                    self.assertNotIn("_auth_user_id", client.session)
                data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
                destination = reverse("accounts:login") if action == "signup" else reverse("home")
                self.assertRedirects(client.post(url, data), destination)
                if action == "login":
                    self.assertEqual(client.session["_auth_user_id"], str(self.user.pk))
                else:
                    self.assertNotIn("_auth_user_id", client.session)
                if action == "signup":
                    self.assertEqual(User.objects.count(), count + 1)

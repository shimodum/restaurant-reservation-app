from datetime import time

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from reservations.models import Reservation, Restaurant


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
            opening_time=time(11), last_reservation_time=time(19), closing_time=time(20),
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
                        self.assertContains(response, '<a href="/reservations/">自分の予約</a>', html=True)
                        self.assertContains(response, reverse("accounts:logout"))
                        self.assertNotContains(response, reverse("accounts:signup"))
                        self.assertNotContains(response, reverse("accounts:login"))
                    else:
                        self.assertContains(response, reverse("accounts:signup"))
                        self.assertContains(response, reverse("accounts:login"))
                        self.assertNotContains(response, reverse("accounts:logout"))
                        self.assertNotContains(response, 'href="/reservations/"')

    def test_admin_navigation_is_visible_only_to_staff(self):
        staff = User.objects.create_user(username="staff", is_staff=True)
        urls = [
            reverse("home"),
            reverse("reservations:restaurant_list"),
            reverse("reservations:restaurant_detail", args=[self.restaurant.pk]),
        ]
        admin_link = f'<a href="{reverse("admin:index")}">管理画面</a>'
        for user in (None, self.user, staff):
            client = Client()
            if user is not None:
                client.force_login(user)
            for url in urls:
                with self.subTest(user=user, url=url):
                    response = client.get(url)
                    if user is not None and user.is_staff:
                        self.assertContains(response, admin_link, html=True)
                    else:
                        self.assertNotContains(response, admin_link, html=True)

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


class MyPageTests(TestCase):
    password = "Mvp-test!47-river"
    new_password = "Changed!82-mountain"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="member", password=cls.password)
        cls.other = User.objects.create_user(
            username="other", password=cls.password, last_name="別", first_name="利用者",
            email="shared@example.com",
        )
        cls.restaurant = Restaurant.objects.create(
            name="食堂", description="料理", address="東京都", business_hours="11時から",
        )
        for user in (cls.user, cls.other):
            Reservation.objects.create(
                user=user, restaurant=cls.restaurant, reserved_at=timezone.now(), party_size=2,
            )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("accounts:mypage")
        self.password_url = reverse("accounts:password_change")

    def profile_data(self, **overrides):
        data = {"last_name": "山田", "first_name": "太郎", "email": "shared@example.com"}
        data.update(overrides)
        return data

    def password_data(self, **overrides):
        data = {
            "old_password": self.password,
            "new_password1": self.new_password,
            "new_password2": self.new_password,
        }
        data.update(overrides)
        return data

    def test_anonymous_get_and_post_require_login(self):
        self.client.logout()
        before = list(User.objects.order_by("pk").values())
        for url in (self.url, self.password_url):
            for method in (self.client.get, self.client.post):
                with self.subTest(url=url, method=method.__name__):
                    self.assertRedirects(method(url), reverse("accounts:login") + "?next=" + url)
        self.assertEqual(list(User.objects.order_by("pk").values()), before)

    def test_mypage_displays_profile_and_links(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "accounts/mypage.html")
        self.assertContains(response, "未設定", count=3)
        self.assertContains(response, self.user.username)
        self.assertContains(response, reverse("reservations:reservation_list"))
        self.assertContains(response, self.password_url)
        self.assertEqual(tuple(response.context["form"].fields), ("last_name", "first_name", "email"))
        self.assertNotContains(response, 'name="username"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_updates_optional_profile_and_accepts_duplicate_email(self):
        response = self.client.post(self.url, self.profile_data(), follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "プロフィールを更新しました。")
        self.user.refresh_from_db()
        self.assertEqual((self.user.last_name, self.user.first_name, self.user.email),
                         ("山田", "太郎", "shared@example.com"))
        for value in ("山田", "太郎", "shared@example.com"):
            self.assertContains(response, value)
        response = self.client.post(self.url, self.profile_data(last_name="", first_name="", email=""), follow=True)
        self.assertContains(response, "未設定", count=3)
        self.user.refresh_from_db()
        self.assertEqual((self.user.last_name, self.user.first_name, self.user.email), ("", "", ""))

    def test_invalid_profile_is_not_saved(self):
        before = list(User.objects.order_by("pk").values())
        for field, value in (("email", "invalid"), ("email", "a" * 255 + "@example.com"),
                             ("last_name", "姓" * 151), ("first_name", "名" * 151)):
            with self.subTest(field=field, value=value):
                response = self.client.post(self.url, self.profile_data(**{field: value}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertContains(response, "errorlist")
                self.assertEqual(response.context["form"][field].value(), value)
                self.assertEqual(list(User.objects.order_by("pk").values()), before)

    def test_profile_email_error_uses_server_validation_and_preserves_input(self):
        from django.contrib.auth.forms import PasswordChangeForm
        from django.forms import EmailField

        response = self.client.get(self.url)
        self.assertContains(
            response,
            f'<form class="auth-form" method="post" action="{self.url}" novalidate>',
        )
        self.assertIsInstance(response.context["form"].fields["email"], EmailField)
        self.assertFalse(response.context["form"].fields["email"].required)
        before = list(User.objects.order_by("pk").values())
        response = self.client.post(self.url, self.profile_data(email="invalid-address"))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.errors["email"], ["正しいメールアドレスの形式で入力してください。"])
        self.assertEqual(form.errors.as_data()["email"][0].code, "invalid")
        self.assertContains(response, str(form["email"].errors), html=True)
        self.assertContains(response, str(form["email"]), html=True)
        self.assertContains(response, 'value="invalid-address"')
        self.assertEqual(list(User.objects.order_by("pk").values()), before)
        self.assertIsInstance(self.client.get(self.password_url).context["form"], PasswordChangeForm)
        self.assertNotContains(self.client.get(self.password_url), "novalidate")
        self.client.logout()
        for name in ("signup", "login"):
            self.assertNotContains(self.client.get(reverse(f"accounts:{name}")), "novalidate")

    def test_extra_parameters_cannot_change_owner_credentials_or_permissions(self):
        before_other = User.objects.values().get(pk=self.other.pk)
        before_password = self.user.password
        reservations = list(Reservation.objects.order_by("pk").values())
        restaurants = list(Restaurant.objects.order_by("pk").values())
        data = self.profile_data(
            user_id=self.other.pk, pk=self.other.pk, id=self.other.pk, user=self.other.pk,
            username="hacked", password="plaintext", is_staff="true", is_superuser="true",
            is_active="false", groups="1", user_permissions="1",
        )
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "member")
        self.assertEqual(self.user.password, before_password)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.groups.exists())
        self.assertFalse(self.user.user_permissions.exists())
        self.assertEqual(User.objects.values().get(pk=self.other.pk), before_other)
        self.assertEqual(list(Reservation.objects.order_by("pk").values()), reservations)
        self.assertEqual(list(Restaurant.objects.order_by("pk").values()), restaurants)

    def test_password_form_is_standard(self):
        from django.contrib.auth.forms import PasswordChangeForm
        response = self.client.get(self.password_url)
        self.assertTemplateUsed(response, "accounts/password_change.html")
        self.assertIsInstance(response.context["form"], PasswordChangeForm)
        for field in ("old_password", "new_password1", "new_password2", "csrfmiddlewaretoken"):
            self.assertContains(response, f'name="{field}"')

    def test_invalid_password_change_does_not_save(self):
        before = list(User.objects.order_by("pk").values())
        cases = [
            ({"old_password": "wrong"}, "old_password"),
            ({"new_password2": "mismatch"}, "new_password2"),
            ({"new_password1": "123", "new_password2": "123"}, "new_password2"),
        ]
        for overrides, field in cases:
            with self.subTest(overrides=overrides):
                response = self.client.post(self.password_url, self.password_data(**overrides))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertEqual(list(User.objects.order_by("pk").values()), before)
                self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_password_change_preserves_session_and_existing_data(self):
        other = User.objects.values().get(pk=self.other.pk)
        profile = (self.user.username, self.user.last_name, self.user.first_name, self.user.email)
        reservations = list(Reservation.objects.order_by("pk").values())
        restaurants = list(Restaurant.objects.order_by("pk").values())
        response = self.client.post(
            self.password_url, self.password_data(user_id=self.other.pk, username="hacked"), follow=True,
        )
        self.assertRedirects(response, self.url)
        self.assertContains(response, "パスワードを変更しました。")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.password))
        self.assertNotEqual(self.user.password, self.new_password)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.get(reverse("reservations:reservation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["reservations"].values_list("user_id", flat=True)), [self.user.pk])
        self.assertEqual((self.user.username, self.user.last_name, self.user.first_name, self.user.email), profile)
        self.assertEqual(User.objects.values().get(pk=self.other.pk), other)
        self.assertEqual(list(Reservation.objects.order_by("pk").values()), reservations)
        self.assertEqual(list(Restaurant.objects.order_by("pk").values()), restaurants)
        client = Client()
        self.assertFalse(client.login(username="member", password=self.password))
        self.assertTrue(client.login(username="member", password=self.new_password))

    def test_profile_and_password_posts_require_valid_csrf(self):
        for url, data in ((self.url, self.profile_data()), (self.password_url, self.password_data())):
            with self.subTest(url=url):
                client = Client(enforce_csrf_checks=True)
                client.force_login(self.user)
                client.get(url)
                before = list(User.objects.order_by("pk").values())
                self.assertEqual(client.post(url, data).status_code, 403)
                self.assertEqual(client.post(url, dict(data, csrfmiddlewaretoken="invalid")).status_code, 403)
                self.assertEqual(list(User.objects.order_by("pk").values()), before)
                data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
                self.assertRedirects(client.post(url, data), self.url)

    def test_get_does_not_update_and_other_methods_are_rejected(self):
        before = list(User.objects.order_by("pk").values())
        for url in (self.url, self.password_url):
            self.assertEqual(self.client.get(url, self.profile_data()).status_code, 200)
            for method in (self.client.put, self.client.patch, self.client.delete):
                self.assertEqual(method(url).status_code, 405)
        self.assertEqual(list(User.objects.order_by("pk").values()), before)

    def test_header_mypage_link_only_for_authenticated_users(self):
        link = f'<a href="{self.url}">マイページ</a>'
        for url in (reverse("home"), reverse("reservations:restaurant_list")):
            self.assertContains(self.client.get(url), link, html=True)
        self.client.logout()
        for url in (reverse("home"), reverse("reservations:restaurant_list")):
            self.assertNotContains(self.client.get(url), link, html=True)

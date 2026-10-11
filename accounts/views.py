from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib.auth.views import PasswordChangeView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods

from .forms import AccountUpdateForm


@login_required
@require_http_methods(["GET", "POST"])
def mypage(request):
    form = AccountUpdateForm(
        request.POST if request.method == "POST" else None, instance=request.user
    )
    if request.method == "POST" and form.is_valid():
        # Persist only profile fields, preserving credentials and permissions.
        user = form.save(commit=False)
        user.save(update_fields=form.Meta.fields)
        messages.success(request, "プロフィールを更新しました。")
        return redirect("accounts:mypage")
    return render(request, "accounts/mypage.html", {"form": form})


class AccountPasswordChangeView(PasswordChangeView):
    form_class = PasswordChangeForm
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:mypage")
    http_method_names = ["get", "post"]

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "パスワードを変更しました。")
        return response


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = UserCreationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("accounts:login")
    return render(request, "accounts/signup.html", {"form": form})

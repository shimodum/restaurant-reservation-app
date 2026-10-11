from django.contrib.auth.models import User
from django.forms import ModelForm


class AccountUpdateForm(ModelForm):
    class Meta:
        model = User
        fields = ("last_name", "first_name", "email")
        labels = {"last_name": "姓", "first_name": "名", "email": "メールアドレス"}
        error_messages = {
            "email": {"invalid": "正しいメールアドレスの形式で入力してください。"},
        }
